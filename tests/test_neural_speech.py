from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from agent.neural_speech import PiperSpeech
from config import Settings


def test_piper_speech_missing_model():
    mock_onnx = MagicMock()
    mock_piper = MagicMock()
    with patch.dict('sys.modules', {
        'onnxruntime': mock_onnx,
        'piper': mock_piper
    }), patch('pathlib.Path.is_file', return_value=False):
        with pytest.raises(RuntimeError, match="Bundled neural voice is missing"):
            PiperSpeech()


def test_piper_speech_chunks():
    mock_onnx = MagicMock()
    mock_piper = MagicMock()
    mock_voice = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.sample_rate = 22050
    mock_chunk.audio_int16_bytes = b'\x00\x00' * 100
    mock_voice.synthesize.return_value = [mock_chunk]
    mock_piper.PiperVoice.load.return_value = mock_voice

    with patch.dict('sys.modules', {
        'onnxruntime': mock_onnx,
        'piper': mock_piper
    }), patch('pathlib.Path.is_file', return_value=True):
        speech = PiperSpeech(model_path='/fake/model.onnx')
        settings = Settings()
        chunks = list(speech.chunks('On it.', settings))
        assert len(chunks) == 1
        assert chunks[0] == (22050, b'\x00\x00' * 100)

        # Test caching
        chunks_cached = list(speech.chunks('On it.', settings))
        assert chunks_cached == chunks


def test_piper_speech_play():
    mock_onnx = MagicMock()
    mock_piper = MagicMock()
    mock_voice = MagicMock()
    mock_sd = MagicMock()

    mock_chunk = MagicMock()
    mock_chunk.sample_rate = 22050
    mock_chunk.audio_int16_bytes = b'\x00\x00' * 1000
    mock_voice.synthesize.return_value = [mock_chunk]
    mock_piper.PiperVoice.load.return_value = mock_voice

    with patch.dict('sys.modules', {
        'onnxruntime': mock_onnx,
        'piper': mock_piper,
        'sounddevice': mock_sd
    }), patch('pathlib.Path.is_file', return_value=True):
        speech = PiperSpeech(model_path='/fake/model.onnx')
        settings = Settings()

        # Normal playback
        speech.play('Hello world', settings, cancelled=lambda: False)

        # Cancelled playback
        speech.play('Hello world', settings, cancelled=lambda: True)
