import threading
import time
from types import SimpleNamespace
import pytest
from agent.voice import SpeechEndpoint, SpeechService, action_narration, configure_voice
from config import Settings


def test_vad_preserves_brief_pause_and_stops_on_silence():
    endpoint = SpeechEndpoint(silence=0.9)
    for _ in range(10):
        assert not endpoint.feed(b'silent', False)
    for _ in range(10):
        assert not endpoint.feed(b'voice', True)
    assert endpoint.started
    for _ in range(20):
        assert not endpoint.feed(b'pause', False)
    assert not endpoint.feed(b'voice', True)
    for _ in range(44):
        assert not endpoint.feed(b'silent', False)
    assert endpoint.feed(b'silent', False)
    assert endpoint.reason == 'silence'
    assert endpoint.audio[0] == b'silent'  # Pre-roll preserves the start of speech.


def test_vad_rejects_noise_spikes_and_bounds_waiting():
    endpoint = SpeechEndpoint(start_timeout=0.2)
    for i in range(9):
        assert not endpoint.feed(b'pcm', i == 3)
    assert endpoint.feed(b'pcm', False)
    assert endpoint.reason == 'no_speech'
    assert not endpoint.started


def test_vad_duration_is_bounded_even_for_continuous_speech():
    endpoint = SpeechEndpoint(max_seconds=0.2)
    for _ in range(9):
        assert not endpoint.feed(b'pcm', True)
    assert endpoint.feed(b'pcm', True)
    assert endpoint.reason == 'limit'


def test_narration_does_not_read_command_or_field_contents():
    assert 'secret' not in action_narration({'kind':'shell','args':{'script':'secret'}})
    assert 'password' not in action_narration({'kind':'browser_fill','args':{'value':'password'}})


def test_calm_voice_defaults_and_selection():
    properties = {}
    voices = [SimpleNamespace(id='david',name='Microsoft David'), SimpleNamespace(id='zira',name='Microsoft Zira')]
    engine = SimpleNamespace(getProperty=lambda key: voices, setProperty=lambda key,value: properties.__setitem__(key,value))
    configure_voice(engine, Settings())
    assert properties == {'voice':'zira','rate':160,'volume':0.85}
    configure_voice(engine, Settings(speech_voice='david',speech_rate=150))
    assert properties['voice'] == 'david'


def test_speech_cancellation_stops_active_and_discards_queued_messages(monkeypatch):
    import agent.voice as voice
    spoken, stopped, owners = [], threading.Event(), []
    started = threading.Event()
    class Engine:
        def getProperty(self, name):
            return []
        def setProperty(self, *args):
            pass
        def say(self, text):
            spoken.append(text)
            started.set()
        def startLoop(self, external):
            pass
        def iterate(self):
            owners.append(threading.get_ident())
        def isBusy(self):
            return True
        def stop(self):
            stopped.set()
        def endLoop(self):
            pass
    monkeypatch.setattr(voice, '_init_speech', lambda: Engine())
    monkeypatch.setattr(voice, '_close_speech', lambda engine: engine.stop())
    speech = SpeechService(lambda: Settings())
    speech.say('On it.')
    assert started.wait(2)
    speech.say('Old queued narration')
    speech.cancel()
    assert stopped.wait(2)
    speech.close()
    assert spoken == ['On it.']
    assert owners and all(owner != threading.get_ident() for owner in owners)


def test_whisper_is_cached_and_never_downloads_during_recording(monkeypatch, tmp_path):
    import sys
    import agent.voice as voice
    (tmp_path / 'voice-model').mkdir()
    constructed = []
    def model(path, **kwargs):
        constructed.append((path, kwargs))
        return object()
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=model))
    monkeypatch.setattr(voice, '_model', None)
    monkeypatch.setattr(voice, '_model_path', None)
    settings = Settings(data_dir=tmp_path)
    assert voice.whisper_model(settings) is voice.whisper_model(settings)
    assert len(constructed) == 1
    assert constructed[0][1]['local_files_only'] is True
