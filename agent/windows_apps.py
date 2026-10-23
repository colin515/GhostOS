"""Known-app discovery and foreground recovery, without elevation or shell interpolation."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import time

@dataclass(frozen=True)
class AppSpec:
    label: str
    executables: tuple[str, ...]
    locations: tuple[str, ...] = ()

APPS = {
    'chrome': AppSpec('Google Chrome', ('chrome.exe',), (r'%ProgramFiles%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe', r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe')),
    'edge': AppSpec('Microsoft Edge', ('msedge.exe',), (r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe', r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe')),
    'firefox': AppSpec('Mozilla Firefox', ('firefox.exe',), (r'%ProgramFiles%\Mozilla Firefox\firefox.exe', r'%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe')),
    'notepad': AppSpec('Notepad', ('notepad.exe',), (r'%SystemRoot%\System32\notepad.exe',)),
    'calculator': AppSpec('Calculator', ('calc.exe', 'calculatorapp.exe'), (r'%SystemRoot%\System32\calc.exe',)),
    'explorer': AppSpec('File Explorer', ('explorer.exe',), (r'%SystemRoot%\explorer.exe',)),
    'paint': AppSpec('Paint', ('mspaint.exe',), (r'%SystemRoot%\System32\mspaint.exe',)),
}
ALIASES = {'google chrome': 'chrome', 'microsoft edge': 'edge', 'mozilla firefox': 'firefox',
           'file explorer': 'explorer', **{key: key for key in APPS}}


def canonical_app(name):
    key = ALIASES.get(name.strip().lower())
    if key is None:
        raise ValueError('Unknown application. Supported: ' + ', '.join(APPS))
    return key


def requested_app(goal):
    # Explicit app names in the user's goal only; never infer instructions from page text.
    for alias in sorted(ALIASES, key=len, reverse=True):
        if re.search(r'(?<![\w./])' + re.escape(alias) + r'(?![\w./])', goal or '', re.I):
            return ALIASES[alias]
    return None


class WindowsApps:
    def __init__(self, stop):
        self.stop = stop

    def _check(self):
        if self.stop.is_set():
            raise InterruptedError('Stopped')
        if os.name != 'nt':
            raise OSError('Windows application recovery requires Windows')

    def installed_path(self, name):
        """Read App Paths first, then standard installation locations; never execute registry arguments."""
        spec = APPS[canonical_app(name)]
        candidates = []
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                for executable in spec.executables:
                    try:
                        with winreg.OpenKey(hive, 'Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\' + executable,
                                            0, winreg.KEY_READ | view) as key:
                            value, _ = winreg.QueryValueEx(key, None)
                            if isinstance(value, str):
                                candidates.append(value.strip('"'))
                    except OSError:
                        pass
        candidates.extend(spec.locations)
        for candidate in candidates:
            path = Path(os.path.expandvars(candidate))
            if path.name.lower() in spec.executables and path.is_file():
                return path
        return None

    def windows(self, name):
        import psutil
        import win32gui
        import win32process
        spec = APPS[canonical_app(name)]
        matches = []
        foreground = win32gui.GetForegroundWindow()
        def visit(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if psutil.Process(pid).name().lower() in spec.executables:
                    matches.append(hwnd)
            except (OSError, psutil.Error):
                pass
        win32gui.EnumWindows(visit, None)
        return sorted(matches, key=lambda hwnd: hwnd != foreground)

    def focus(self, name):
        self._check()
        from agent.window_focus import focus_window
        windows = self.windows(name)
        if not windows:
            raise LookupError(f'{name} has no visible window')
        last_error = None
        for hwnd in windows:
            try:
                focus_window(hwnd, self.stop, maximize=True)
                return f'{name} is focused and maximized'
            except InterruptedError:
                raise
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f'Could not focus {name}: {last_error}')

    def _wait_for_window(self, name, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check()
            try:
                return self.focus(name)
            except (LookupError, RuntimeError):
                if self.stop.wait(0.2):
                    self._check()
        raise RuntimeError(f'{name} did not provide a focusable window within {timeout} seconds')

    def ensure(self, name, strategy='focus', type_text=None):
        self._check()
        name = canonical_app(name)
        try:
            return self.focus(name)
        except (LookupError, RuntimeError):
            if strategy == 'focus':
                raise
        if strategy in ('launch', 'search'):
            # Do not launch duplicate processes when an existing app merely rejects focus.
            if self.windows(name):
                raise RuntimeError(f'{name} is running; try alternate window navigation')
            path = self.installed_path(name)
            if path is None:
                raise FileNotFoundError(f'{name} was not found in App Paths or standard installation locations')
            subprocess.Popen([str(path)], shell=False)
            return self._wait_for_window(name)
        raise ValueError('Unknown recovery strategy')
