"""Bounded game input; no injection, anti-cheat bypass or background game control."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
import threading

ULONG_PTR = ctypes.c_size_t
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]
class INPUTUNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', INPUTUNION)]


def send_input(events):
    if os.name != 'nt':
        raise OSError('Windows input is unavailable')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    batch = (INPUT * len(events))(*events)
    count = user32.SendInput(len(events), batch, ctypes.sizeof(INPUT))
    if count != len(events):
        raise OSError(ctypes.get_last_error(), 'SendInput failed (focus, integrity or protected game)')


def release_inputs():
    """Supervisor fallback after worker termination: release pressed keys and mouse buttons."""
    if os.name != 'nt':
        return
    try:
        events = []
        for vk in range(8, 256):
            if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=2)))
        events.append(INPUT(type=0, mi=MOUSEINPUT(dwFlags=0x0004 | 0x0010 | 0x0040)))
        events.extend(INPUT(type=0, mi=MOUSEINPUT(mouseData=button, dwFlags=0x0100)) for button in (1, 2))
        send_input(events)
    except OSError:
        pass


class GamingEngine:
    def __init__(self, stop, target=None):
        import pydirectinput
        self.driver = pydirectinput
        self.driver.PAUSE = 0.01
        self.driver.FAILSAFE = True
        self.stop, self.held = stop, set()
        import win32gui
        self.windows = win32gui
        self.target = target or self.windows.GetForegroundWindow()
        from agent.window_focus import is_agent_window
        if not self.target or is_agent_window(self.target):
            raise RuntimeError('Select an external game window before sending game input')

    def check_focus(self):
        if self.stop.is_set():
            raise InterruptedError('Stopped')
        if self.windows.GetForegroundWindow() != self.target:
            raise RuntimeError('Game lost focus; no game input sent. Start a new run with the game focused.')

    def move(self, dx, dy):
        self.check_focus()
        send_input([INPUT(type=0, mi=MOUSEINPUT(dx=dx, dy=dy, dwFlags=0x0001))])

    def key(self, key, duration):
        self.check_focus()
        self.held.add(key)
        try:
            self.driver.keyDown(key)
            remaining = duration
            while remaining > 0:
                interval = min(remaining, 0.05)
                if self.stop.wait(interval):
                    raise InterruptedError('Stopped')
                self.check_focus()
                remaining -= interval
        finally:
            self.driver.keyUp(key)
            self.held.discard(key)

    def click(self, button='left'):
        self.check_focus()
        if button == 'left':
            self.driver.click()
        else:
            self.driver.click(button=button)

    def action(self, keys=(), buttons=(), dx=0, dy=0, duration=.2):
        """Hold movement chords and mouse buttons together; always release on stop/focus loss."""
        self.check_focus()
        allowed = getattr(self.driver,'KEYBOARD_MAPPING',{})
        keys = list(dict.fromkeys(key.lower() for key in keys))
        if not isinstance(allowed,dict) or any(key not in allowed for key in keys):
            raise ValueError('Unsupported game key name')
        from agent.mouse import BUTTONS
        pressed = []
        try:
            for key in keys:
                self.check_focus()
                self.driver.keyDown(key)
                self.held.add(key)
            for button in dict.fromkeys(buttons):
                self.check_focus()
                down,up,data = BUTTONS[button]
                send_input([INPUT(type=0,mi=MOUSEINPUT(mouseData=data,dwFlags=down))])
                pressed.append((up,data))
            if dx or dy:
                self.move(dx,dy)
            remaining = duration
            while remaining > 0:
                interval = min(.02,remaining)
                if self.stop.wait(interval):
                    raise InterruptedError('Stopped')
                self.check_focus()
                remaining -= interval
        finally:
            errors = []
            for up,data in reversed(pressed):
                try:
                    send_input([INPUT(type=0,mi=MOUSEINPUT(mouseData=data,dwFlags=up))])
                except Exception as exc:
                    errors.append(exc)
            for key in reversed(keys):
                if key in self.held:
                    try:
                        self.driver.keyUp(key)
                    except Exception as exc:
                        errors.append(exc)
                    finally:
                        self.held.discard(key)
            if errors:
                raise RuntimeError('Could not release all game input; emergency release is required') from errors[0]

    def close(self):
        for key in list(self.held):
            self.driver.keyUp(key)
        self.held.clear()
