"""Local streaming speech endpoint detection, cached Whisper and cancellable SAPI speech."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import queue
import tempfile
import threading
import time
import wave

class SpeechEndpoint:
    """20 ms WebRTC decisions: preserve pre-roll, tolerate brief pauses, bound silence and duration."""
    def __init__(self, silence=0.9, max_seconds=45, start_timeout=8):
        self.silence_frames = round(silence / 0.02)
        self.max_frames = round(max_seconds / 0.02)
        self.start_frames = round(start_timeout / 0.02)
        self.pre_roll = deque(maxlen=15)
        self.votes = deque(maxlen=5)
        self.audio = []
        self.started = False
        self.frames = self.quiet = 0
        self.reason = ''

    def feed(self, pcm, voiced):
        self.frames += 1
        if not self.started:
            self.pre_roll.append(pcm)
            self.votes.append(bool(voiced))
            if sum(self.votes) >= 3:
                self.started = True
                self.audio.extend(self.pre_roll)
            elif self.frames >= self.start_frames:
                self.reason = 'no_speech'
                return True
        else:
            self.audio.append(pcm)
            self.quiet = 0 if voiced else self.quiet + 1
            if self.quiet >= self.silence_frames:
                self.reason = 'silence'
                return True
        if self.frames >= self.max_frames:
            self.reason = 'limit'
            return True
        return False

_model = None
_model_path = None
_model_lock = threading.Lock()

def whisper_model(settings):
    global _model, _model_path
    from faster_whisper import WhisperModel
    model_dir = settings.data_dir / 'voice-model'
    if not model_dir.is_dir():
        raise RuntimeError('Download the voice model in Settings → Model and voice setup first')
    with _model_lock:
        if _model is None or _model_path != str(model_dir):
            _model = WhisperModel(str(model_dir), device='cpu', compute_type='int8', local_files_only=True)
            _model_path = str(model_dir)
        return _model


def record_and_transcribe(settings, progress=print, level=lambda value: None, cancel=None):
    import numpy as np
    import sounddevice as sd
    import webrtcvad
    cancel = cancel or threading.Event()
    if not (settings.data_dir / 'voice-model').is_dir():
        raise RuntimeError('Download the voice model in Settings → Model and voice setup first')
    endpoint = SpeechEndpoint(settings.vad_silence, settings.voice_max_seconds)
    vad = webrtcvad.Vad(2)
    chunks = queue.Queue(maxsize=100)
    overflow = threading.Event()
    def capture(indata, frames, timing, status):
        if status:
            overflow.set()
        try:
            chunks.put_nowait(bytes(indata))
        except queue.Full:
            overflow.set()
    progress('Listening… speak naturally, then pause to send.')
    last_level = 0.0
    last_received = time.monotonic()
    with sd.RawInputStream(samplerate=16000, channels=1, dtype='int16', blocksize=320, callback=capture):
        while not cancel.is_set():
            if overflow.is_set():
                raise RuntimeError('Microphone audio overflowed. Close other audio apps and try again.')
            try:
                pcm = chunks.get(timeout=0.2)
            except queue.Empty:
                # A disconnected device must not leave the UI stuck listening forever.
                if time.monotonic() - last_received > 5:
                    raise RuntimeError('Microphone stopped delivering audio')
                continue
            last_received = time.monotonic()
            if len(pcm) != 640:
                raise RuntimeError('Microphone returned an unexpected frame size')
            now = time.monotonic()
            if now - last_level >= 0.05:
                samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
                rms = float(np.sqrt(np.mean(samples * samples)))
                level(min(1.0, rms * 8))
                last_level = now
            if endpoint.feed(pcm, vad.is_speech(pcm, 16000)):
                break
    level(0.0)
    if cancel.is_set():
        raise InterruptedError('Voice input cancelled')
    if not endpoint.started:
        return ''
    if endpoint.reason == 'limit':
        raise RuntimeError('Voice command reached the recording limit. Please use a shorter command.')
    progress('Transcribing locally…')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'recording.wav'
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b''.join(endpoint.audio))
        segments, _ = whisper_model(settings).transcribe(str(path), vad_filter=True, beam_size=1,
                                                        condition_on_previous_text=False)
        words = []
        for segment in segments:
            if cancel.is_set():
                raise InterruptedError('Voice input cancelled')
            words.append(segment.text.strip())
        return ' '.join(words).strip()


def _init_speech():
    import os
    if os.name == 'nt':
        import pythoncom
        pythoncom.CoInitialize()
    from pyttsx3.engine import Engine
    # pyttsx3.init caches engines globally; separate COM owners must not share that cache.
    return Engine(driverName='sapi5' if os.name == 'nt' else None)


def _close_speech(engine):
    import os
    if engine:
        engine.stop()
    if os.name == 'nt':
        import pythoncom
        pythoncom.CoUninitialize()


def list_voices():
    engine = None
    try:
        engine = _init_speech()
        return [{'id': voice.id, 'name': voice.name} for voice in engine.getProperty('voices')]
    finally:
        _close_speech(engine)


def configure_voice(engine, settings):
    voices = engine.getProperty('voices')
    selected = next((v for v in voices if v.id == settings.speech_voice), None)
    if selected is None and not settings.speech_voice:
        selected = next((v for v in voices if 'zira' in v.name.lower()), None)
    if selected:
        engine.setProperty('voice', selected.id)
    engine.setProperty('rate', settings.speech_rate)
    engine.setProperty('volume', settings.speech_volume)


class SpeechService:
    """One COM owner; bounded queue, generation-based cancellation, no speech on the UI thread."""
    def __init__(self, settings, on_error=lambda message: None):
        self.settings, self.on_error = settings, on_error
        self.messages = queue.Queue(maxsize=4)
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.generation = 0
        self.thread = None

    def say(self, text, priority=False, settings=None):
        if self.closed.is_set() or not text.strip():
            return
        if priority:
            self.cancel()
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, daemon=True, name='GhostOS-speech')
                self.thread.start()
            item = (self.generation, text[:400], settings)
            try:
                self.messages.put_nowait(item)
            except queue.Full:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    pass
                self.messages.put_nowait(item)

    def cancel(self):
        with self.lock:
            self.generation += 1
            while True:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    break

    def _run(self):
        engine = None
        try:
            engine = _init_speech()
            while not self.closed.is_set():
                try:
                    generation, text, override = self.messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                if generation != self.generation:
                    continue
                configure_voice(engine, override or self.settings())
                engine.say(text)
                engine.startLoop(False)
                try:
                    while not self.closed.is_set():
                        engine.iterate()  # Pumps SAPI/COM events on its owning thread.
                        if generation != self.generation:
                            engine.stop()
                            break
                        if not engine.isBusy():
                            break
                        self.closed.wait(0.015)
                finally:
                    engine.endLoop()
        except Exception as exc:
            self.on_error(f'Local speech unavailable: {exc}')
        finally:
            _close_speech(engine)

    def close(self):
        self.cancel()
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=1)


def action_narration(action):
    """Narrate intent without reading typed text, passwords or shell content aloud."""
    kind, args = action.get('kind'), action.get('args', {})
    if kind == 'ensure_app':
        verb = {'focus': 'Switching to ', 'launch': 'Opening ', 'search': 'Looking for '}.get(args.get('strategy'), 'Opening ')
        return verb + args.get('name', 'the application') + '.'
    return {'hotkey': 'Using keyboard navigation.', 'type_text': 'Entering text.',
            'click': 'Selecting a control.', 'ui_click': 'Selecting a control.',
            'browser_navigate': 'Opening the website.', 'browser_fill': 'Filling in the field.',
            'browser_click': 'Selecting the page control.', 'shell': 'Running the approved command.',
            'focus': 'Restoring the application window.', 'open_app': 'Opening the application.',
            'template_click': 'Selecting the visual target.', 'game_move': 'Adjusting the camera.',
            'game_key': 'Moving in the game.', 'game_click': 'Using the game control.'}.get(kind, '')


def speak(text):
    """Compatibility helper for external callers; desktop uses SpeechService."""
    from config import Settings
    engine = None
    try:
        engine = _init_speech()
        configure_voice(engine, Settings())
        engine.say(text[:1500])
        engine.runAndWait()
    finally:
        _close_speech(engine)
