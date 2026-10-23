import threading
import pytest
from agent.mouse import MouseDriver, BUTTONS


class Backend:
    def __init__(self):
        self.pos = (-40, 20)
        self.inputs = []
        self.positions = []
    def bounds(self):
        return (-100, 0, 1000, 800)
    def position(self):
        return self.pos
    def move(self, x, y):
        self.pos = x, y
        self.positions.append(self.pos)
    def input(self, flags, data):
        self.inputs.append((flags, data))


@pytest.mark.parametrize('button', BUTTONS)
def test_verified_smooth_click_supports_each_button(button):
    backend, events = Backend(), []
    mouse = MouseDriver(threading.Event(), lambda **e: events.append(e), backend)
    mouse.click(100, 100, button, clicks=2, duration=0.05)
    assert backend.pos == (100, 100)
    assert len(set(backend.positions)) > 2
    down, up, data = BUTTONS[button]
    assert backend.inputs == [(down, data), (up, data)] * 2
    assert events[-1]['phase'] == 'clicked'
    assert any(e['phase'] == 'arrived' for e in events)


def test_cancelled_drag_releases_button():
    stop, backend = threading.Event(), Backend()
    mouse = MouseDriver(stop, backend=backend)
    original = backend.input
    def press(flags, data):
        original(flags, data)
        if flags == BUTTONS['left'][0]:
            stop.set()
    backend.input = press
    with pytest.raises(InterruptedError):
        mouse.drag(10, 10, 200, 200)
    assert backend.inputs[-1] == (BUTTONS['left'][1], 0)


def test_mouse_rejects_clipped_cursor_and_out_of_bounds():
    backend = Backend()
    backend.move = lambda x, y: None
    mouse = MouseDriver(threading.Event(), backend=backend)
    with pytest.raises(RuntimeError, match='verification'):
        mouse.move(100, 100, 0.01)
    with pytest.raises(ValueError):
        mouse.move(5000, 5000)
