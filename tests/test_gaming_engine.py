import threading
from unittest.mock import MagicMock, patch
import pytest
from agent.gaming_engine import GamingEngine, send_input, release_inputs


def test_send_input_non_windows():
    with patch('os.name', 'posix'):
        with pytest.raises(OSError, match="Windows input is unavailable"):
            send_input([])


def test_release_inputs_non_windows():
    with patch('os.name', 'posix'):
        # Should return silently on non-Windows
        release_inputs()


def test_gaming_engine_init_and_check_focus():
    stop_event = threading.Event()
    mock_pydirectinput = MagicMock()
    mock_win32gui = MagicMock()
    mock_win32gui.GetForegroundWindow.return_value = 1001

    with patch.dict('sys.modules', {
        'pydirectinput': mock_pydirectinput,
        'win32gui': mock_win32gui
    }):
        engine = GamingEngine(stop=stop_event)
        assert engine.target == 1001

        # Check focus passes when foreground window matches target
        engine.check_focus()

        # Check focus raises InterruptedError when stopped
        stop_event.set()
        with pytest.raises(InterruptedError, match="Stopped"):
            engine.check_focus()

        stop_event.clear()
        # Check focus raises RuntimeError when window changes
        mock_win32gui.GetForegroundWindow.return_value = 2002
        with pytest.raises(RuntimeError, match="Game lost focus"):
            engine.check_focus()


def test_gaming_engine_key_click_close():
    stop_event = threading.Event()
    mock_pydirectinput = MagicMock()
    mock_win32gui = MagicMock()
    mock_win32gui.GetForegroundWindow.return_value = 1001

    with patch.dict('sys.modules', {
        'pydirectinput': mock_pydirectinput,
        'win32gui': mock_win32gui
    }):
        engine = GamingEngine(stop=stop_event)
        engine.click()
        mock_pydirectinput.click.assert_called_once()

        engine.key('w', duration=0.01)
        mock_pydirectinput.keyDown.assert_called_with('w')
        mock_pydirectinput.keyUp.assert_called_with('w')

        engine.held.add('a')
        engine.close()
        mock_pydirectinput.keyUp.assert_called_with('a')
        assert len(engine.held) == 0
