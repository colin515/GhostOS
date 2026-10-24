"""Physical-pixel Windows cursor driver with verified motion and cancellable drags."""
import ctypes
from ctypes import wintypes
import math
import time

BUTTONS = {'left': (0x0002, 0x0004, 0), 'right': (0x0008, 0x0010, 0),
           'middle': (0x0020, 0x0040, 0), 'x1': (0x0080, 0x0100, 1),
           'x2': (0x0080, 0x0100, 2)}


class WinMouse:
    def __init__(self):
        self.user = ctypes.windll.user32
        self.user.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self.user.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)

    def position(self):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise OSError('GetCursorPos failed')
        return point.x, point.y

    def bounds(self):
        return tuple(self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79))

    def validate_target(self, x, y):
        import win32gui
        from agent.window_focus import is_agent_window
        hwnd = win32gui.WindowFromPoint((x, y))
        root = win32gui.GetAncestor(hwnd, 2) if hwnd else None
        if is_agent_window(root or hwnd):
            raise RuntimeError('Mouse target is covered by GhostOS controls; choose an unobscured target')

    def move(self, x, y):
        if not self.user.SetCursorPos(x, y):
            raise OSError('SetCursorPos rejected input; check the interactive desktop')

    def input(self, flags, data=0):
        from agent.gaming_engine import INPUT, MOUSEINPUT, send_input
        send_input([INPUT(type=0, mi=MOUSEINPUT(mouseData=data & 0xffffffff, dwFlags=flags))])


class MouseDriver:
    def __init__(self, stop, emit=lambda **event: None, backend=None, guard=None):
        self.stop, self.emit, self.backend = stop, emit, backend or WinMouse()
        self.guard = guard
        self.before_press = None

    def check(self):
        if self.stop.is_set():
            raise InterruptedError('Mouse action stopped')
        if self.guard:
            self.guard()

    def verify_endpoint(self, x, y):
        self.check()
        if self.before_press:
            self.before_press()
        if math.dist(self.backend.position(), (x,y)) > 3:
            raise RuntimeError('Cursor moved before button press; no click was sent')
        if hasattr(self.backend,'validate_target'):
            self.backend.validate_target(x,y)

    def move(self, x, y, duration=0.35):
        self.check()
        x, y = int(x), int(y)
        left, top, width, height = self.backend.bounds()
        if not (left <= x < left + width and top <= y < top + height):
            raise ValueError('Mouse target outside the virtual desktop')
        if hasattr(self.backend, 'validate_target'):
            self.backend.validate_target(x, y)
        start = self.backend.position()
        self.emit(kind='MOUSE', phase='start', start=list(start), target=[x, y])
        began, last_log = time.monotonic(), 0
        while True:
            self.check()
            elapsed = time.monotonic() - began
            ratio = min(1.0, elapsed / max(0.01, duration))
            eased = ratio * ratio * (3 - 2 * ratio)
            self.backend.move(round(start[0] + (x - start[0]) * eased), round(start[1] + (y - start[1]) * eased))
            if elapsed - last_log >= 0.1:
                self.emit(kind='MOUSE', phase='moving', position=list(self.backend.position()))
                last_log = elapsed
            if ratio >= 1:
                break
            if self.stop.wait(0.01):
                self.check()
        actual = self.backend.position()
        if math.dist(actual, (x, y)) > 3:
            raise RuntimeError(f'Cursor verification failed: requested {(x, y)}, observed {actual}')
        self.emit(kind='MOUSE', phase='arrived', position=list(actual))
        return actual

    def click(self, x, y, button='left', clicks=1, duration=0.35):
        self.move(x, y, duration)
        down, up, data = BUTTONS[button]
        for index in range(clicks):
            self.verify_endpoint(x,y)
            try:
                self.backend.input(down, data)
                self.stop.wait(0.04)
            finally:
                self.backend.input(up, data)
            self.check()
            if index + 1 < clicks:
                self.stop.wait(0.1)
        self.emit(kind='MOUSE', phase='clicked', button=button, clicks=clicks, position=[x, y])

    def drag(self, x, y, to_x, to_y, button='left', duration=0.8):
        self.move(x, y)
        down, up, data = BUTTONS[button]
        self.check()
        try:
            self.verify_endpoint(x,y)
            self.backend.input(down, data)
            self.move(to_x, to_y, duration)
        finally:
            self.backend.input(up, data)
        self.emit(kind='MOUSE', phase='dragged', button=button, position=[to_x, to_y])

    def scroll(self, ticks, horizontal=False):
        self.check()
        self.backend.input(0x1000 if horizontal else 0x0800, ticks * 120)
        if self.stop.wait(0.04):
            self.check()
        self.emit(kind='MOUSE', phase='scrolled', ticks=ticks, horizontal=horizontal)
