"""Verified native foreground transfer; never activate GhostOS-owned windows."""
import os
import time

PROPERTY = 'GhostOS.NonInteractiveUI'


def mark_ui(hwnd):
    if os.name == 'nt':
        import win32gui
        win32gui.SetProp(int(hwnd), PROPERTY, 1)


def is_agent_window(hwnd):
    if not hwnd or os.name != 'nt':
        return False
    import win32gui
    return bool(win32gui.GetProp(int(hwnd), PROPERTY))


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
