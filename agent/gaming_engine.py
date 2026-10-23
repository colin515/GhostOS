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
        send_input(events)
    except OSError:
        pass


class GamingEngine:
    def __init__(self, stop):
        import pydirectinput
        self.driver = pydirectinput
        self.driver.PAUSE = 0.01
        self.driver.FAILSAFE = True
        self.stop, self.held = stop, set()
        import win32gui
        self.windows = win32gui
        self.target = self.windows.GetForegroundWindow()

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

    def click(self):
        self.check_focus()
        self.driver.click()

    def close(self):
        for key in list(self.held):
            self.driver.keyUp(key)
        self.held.clear()
