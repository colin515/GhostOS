"""Offline Piper synthesis; the Windows installer contains the voice and phonemizer."""
from pathlib import Path
from config import RESOURCE_DIR

MODEL = 'en_US-ljspeech-medium.onnx'


class PiperSpeech:
    def __init__(self, model_path=None):
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from piper import PiperVoice
        path = Path(model_path or RESOURCE_DIR / 'assets' / 'voice' / MODEL)
        if not path.is_file():
            raise RuntimeError('Bundled neural voice is missing; source users run python build_tools/fetch_voice.py')
        self.voice = PiperVoice.load(str(path), use_cuda=False)
        self.cached = {}

    def chunks(self, text, settings):
        from piper import SynthesisConfig
        config = SynthesisConfig(volume=settings.speech_volume, length_scale=160 / settings.speech_rate,
                                 noise_scale=0.5, noise_w_scale=0.6)
        key = (text, settings.speech_rate, settings.speech_volume)
        if key in self.cached:
            yield from self.cached[key]
            return
        saved = []
        for chunk in self.voice.synthesize(text, syn_config=config):
            item = (chunk.sample_rate, chunk.audio_int16_bytes)
            if text == 'On it.':
                saved.append(item)
            yield item
        if saved:
            self.cached[key] = saved

    def play(self, text, settings, cancelled):
        import sounddevice as sd
        for rate, pcm in self.chunks(text, settings):
            if cancelled():
                return
            with sd.RawOutputStream(samplerate=rate, channels=1, dtype='int16') as stream:
                # Small writes bound cancellation latency and avoid microphone/TTS overlap.
                size = max(2, round(rate * 0.02) * 2)
                for offset in range(0, len(pcm), size):
                    if cancelled():
                        stream.abort()
                        return
                    stream.write(pcm[offset:offset + size])


def smoke_test():
    import wave
    import tempfile
    from config import Settings
    engine = PiperSpeech()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'voice.wav'
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            for rate, pcm in engine.chunks('On it.', Settings()):
                output.setframerate(rate)
                output.writeframes(pcm)
        with wave.open(str(path), 'rb') as result:
            if result.getnframes() < 1000:
                raise RuntimeError('Neural voice produced no audio')
    print('Offline neural voice synthesis passed')
