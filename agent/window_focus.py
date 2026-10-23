"""Verified native foreground transfer; never activate GhostOS-owned windows."""
import os
import ctypes
from ctypes import wintypes
from functools import lru_cache
import time

PROPERTY = 'GhostOS.NonInteractiveUI'
UI_PROCESSES = set()


def register_ui_process(pid):
    UI_PROCESSES.add(int(pid))


@lru_cache(maxsize=1)
def property_api():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.IsWindow.argtypes = (wintypes.HWND,)
    user.IsWindow.restype = wintypes.BOOL
    user.SetPropW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE)
    user.SetPropW.restype = wintypes.BOOL
    user.GetPropW.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
    user.GetPropW.restype = wintypes.HANDLE
    user.RemovePropW.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
    user.RemovePropW.restype = wintypes.HANDLE
    return user


def mark_ui(hwnd):
    if os.name == 'nt':
        register_ui_process(os.getpid())
        user = property_api()
        if user.IsWindow(int(hwnd)):
            # pywin32 does not expose SetProp/GetProp. Use the pointer-sized native API.
            if not user.SetPropW(int(hwnd), PROPERTY, 1):
                from agent.startup import log_startup
                log_startup(f'Window property unavailable (error {ctypes.get_last_error()}); PID guard remains active')


def unmark_ui(hwnd):
    if os.name == 'nt' and property_api().IsWindow(int(hwnd)):
        property_api().RemovePropW(int(hwnd), PROPERTY)


def is_agent_window(hwnd):
    if not hwnd or os.name != 'nt':
        return False
    try:
        if property_api().GetPropW(int(hwnd), PROPERTY):
            return True
        import win32process
        _, pid = win32process.GetWindowThreadProcessId(int(hwnd))
        return pid in UI_PROCESSES
    except Exception:
        return False


def focus_window(hwnd, stop=None, maximize=False):
    import win32con
    import win32gui
    import win32process
    import win32api
    import ctypes
    if not win32gui.IsWindow(hwnd) or is_agent_window(hwnd):
        raise RuntimeError('Target is unavailable or belongs to GhostOS')
    user = ctypes.windll.user32
    current = win32api.GetCurrentThreadId()
    target, _ = win32process.GetWindowThreadProcessId(hwnd)
    for _ in range(3):
        if stop and stop.is_set():
            raise InterruptedError('Stopped')
        attached = []
        try:
            foreground = win32gui.GetForegroundWindow()
            other, _ = win32process.GetWindowThreadProcessId(foreground) if foreground else (0, 0)
            for thread in set((target, other)) - {0, current}:
                if user.AttachThreadInput(current, thread, True):
                    attached.append(thread)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE if maximize else (win32con.SW_RESTORE if win32gui.IsIconic(hwnd) else win32con.SW_SHOW))
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            if win32gui.GetForegroundWindow() == hwnd:
                return hwnd
        except Exception:
            pass
        finally:
            for thread in reversed(attached):
                user.AttachThreadInput(current, thread, False)
        if stop:
            if stop.wait(0.1):
                raise InterruptedError('Stopped')
        else:
            time.sleep(0.1)
    raise RuntimeError('Windows refused foreground transfer. Unlock the desktop or dismiss UAC manually.')


class FocusGuard:
    def __init__(self, stop):
        self.stop, self.last = stop, None

    def observe(self):
        if os.name != 'nt':
            return None
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        if hwnd and not is_agent_window(hwnd):
            self.last = hwnd
        return hwnd

    def ensure_external(self):
        hwnd = self.observe()
        if hwnd and is_agent_window(hwnd):
            if not self.last:
                raise RuntimeError('GhostOS is foreground; waiting for an external application target')
            focus_window(self.last, self.stop)
        return self.last
