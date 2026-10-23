"""Optional microphone capture/transcription; uses only the predownloaded speech model."""
from pathlib import Path
import tempfile
import wave


def record_and_transcribe(settings, progress=print, seconds=5):
    import sounddevice as sd
    from faster_whisper import WhisperModel
    model_dir = settings.data_dir / 'voice-model'
    if not model_dir.exists():
        raise RuntimeError('Download the voice model in first-run setup before recording')
    progress('Listening for five seconds…')
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype='int16')
    sd.wait()
    progress('Transcribing locally…')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'recording.wav'
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio.tobytes())
        model = WhisperModel(str(model_dir), device='cpu', compute_type='int8', local_files_only=True)
        segments, _ = model.transcribe(str(path), vad_filter=True)
        return ' '.join(segment.text.strip() for segment in segments)


def speak(text):
    import os
    import pyttsx3
    engine = None
    if os.name == 'nt':
        import pythoncom
        pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init()
        engine.say(text[:1500])
        engine.runAndWait()
    finally:
        if engine:
            engine.stop()
        if os.name == 'nt':
            pythoncom.CoUninitialize()
