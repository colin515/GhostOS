"""Known-app discovery and foreground recovery, without elevation or shell interpolation."""
from __future__ import annotations
from dataclasses import dataclass
import os
import json
from pathlib import Path
import re
import subprocess
import time

@dataclass(frozen=True)
class AppSpec:
    label: str
    executables: tuple[str, ...]
    locations: tuple[str, ...] = ()
    uri: str = ''

_APP_CATALOG = None

APPS = {
    'chrome': AppSpec('Google Chrome', ('chrome.exe',), (r'%ProgramFiles%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe', r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe')),
    'edge': AppSpec('Microsoft Edge', ('msedge.exe',), (r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe', r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe')),
    'firefox': AppSpec('Mozilla Firefox', ('firefox.exe',), (r'%ProgramFiles%\Mozilla Firefox\firefox.exe', r'%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe')),
    'notepad': AppSpec('Notepad', ('notepad.exe',), (r'%SystemRoot%\System32\notepad.exe',)),
    'calculator': AppSpec('Calculator', ('calc.exe', 'calculatorapp.exe'), (r'%SystemRoot%\System32\calc.exe',)),
    'explorer': AppSpec('File Explorer', ('explorer.exe',), (r'%SystemRoot%\explorer.exe',)),
    'store': AppSpec('Microsoft Store', ('winstore.app.exe', 'winstore.desktop.exe'), uri='ms-windows-store://home'),
    'paint': AppSpec('Paint', ('mspaint.exe',), (r'%SystemRoot%\System32\mspaint.exe',)),
}
ALIASES = {'google chrome': 'chrome', 'microsoft edge': 'edge', 'mozilla firefox': 'firefox',
           'file explorer': 'explorer', 'microsoft store': 'store', 'windows store': 'store', **{key: key for key in APPS}}


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
                found = psutil.Process(pid).name().lower() in spec.executables
                # Windows 10 UWP apps can have an ApplicationFrameHost top-level HWND.
                if not found and psutil.Process(pid).name().lower() == 'applicationframehost.exe':
                    def child_visit(child, _):
                        nonlocal found
                        try:
                            _, child_pid = win32process.GetWindowThreadProcessId(child)
                            found |= psutil.Process(child_pid).name().lower() in spec.executables
                        except (OSError, psutil.Error):
                            pass
                    win32gui.EnumChildWindows(hwnd, child_visit, None)
                if found:
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
                return json.dumps({'app': canonical_app(name), 'verified': True, 'foreground': True,
                                   'hwnd': hwnd, 'message': f'{name} is focused and maximized'})
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
        try:
            name = canonical_app(name)
        except ValueError:
            return self.ensure_registered(name, strategy)
        try:
            return self.focus(name)
        except (LookupError, RuntimeError):
            if strategy == 'focus':
                raise
        if strategy in ('launch', 'search'):
            # Do not launch duplicate processes when an existing app merely rejects focus.
            if self.windows(name):
                raise RuntimeError(f'{name} is running; try alternate window navigation')
            spec = APPS[name]
            if spec.uri:
                # Fixed, packaged URI; no command text or arbitrary protocols from the model.
                os.startfile(spec.uri)
                return self._wait_for_window(name, timeout=10)
            path = self.installed_path(name)
            if path is None:
                raise FileNotFoundError(f'{name} was not found in App Paths or standard installation locations')
            subprocess.Popen([str(path)], shell=False)
            return self._wait_for_window(name)
        raise ValueError('Unknown recovery strategy')


    def registered_apps(self):
        """Reuse Windows-Use's installed-app reader with a hidden, fixed read-only query."""
        self._check()
        global _APP_CATALOG
        if _APP_CATALOG is not None:
            return _APP_CATALOG
        from ghostos_vendor.windows_use.agent.desktop.service import Desktop
        class Catalog(Desktop):
            def execute_command(self, command, timeout=10):
                # Upstream uses PATH PowerShell without CREATE_NO_WINDOW. Do not allow
                # this read-only helper to become a general execution/approval bypass.
                if command != 'Get-StartApps | ConvertTo-Csv -NoTypeInformation':
                    raise ValueError('Only installed-app inventory is permitted here')
                import base64
                fixed = '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; ' + command
                executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
                process = subprocess.run([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive',
                    '-EncodedCommand', base64.b64encode(fixed.encode('utf-16-le')).decode()],
                    capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW, shell=False)
                return process.stdout.decode('utf-8', errors='replace'), process.returncode
        _APP_CATALOG = Catalog.__new__(Catalog).get_apps_from_start_menu()
        return _APP_CATALOG

    def ensure_registered(self, name, strategy):
        """Exact installed display names only; never interpolate model text into commands."""
        self._check()
        catalog = self.registered_apps()
        normalized = name.strip().casefold()
        matched = next((key for key in catalog if key.casefold() == normalized), None)
        if matched is None:
            raise FileNotFoundError(f'{name} is not an exact installed app name. Use app_list to discover it.')
        import win32gui
        from agent.window_focus import focus_window, is_agent_window
        def matching():
            windows = []
            def visit(hwnd, _):
                title = win32gui.GetWindowText(hwnd).casefold()
                if (win32gui.IsWindowVisible(hwnd) and not is_agent_window(hwnd)
                        and re.search(r'(?<!\w)' + re.escape(normalized) + r'(?!\w)', title)):
                    windows.append(hwnd)
            win32gui.EnumWindows(visit, None)
            return windows
        def focus():
            for hwnd in matching():
                focus_window(hwnd, self.stop, maximize=True)
                return json.dumps({'app':matched, 'verified':True, 'foreground':True, 'hwnd':hwnd})
            return None
        result = focus()
        if result:
            return result
        if strategy == 'focus':
            raise LookupError(f'{name} has no identifiable visible window')
        app_id = catalog[matched]
        if not app_id or any(char in app_id for char in '\r\n\x00'):
            raise ValueError('Invalid installed application ID')
        os.startfile('shell:AppsFolder\\' + app_id)
        until = time.monotonic() + 10
        while time.monotonic() < until:
            self._check()
            result = focus()
            if result:
                return result
            if self.stop.wait(0.2):
                self._check()
        raise RuntimeError(f'{name} activation was sent; its window could not yet be identified. Inspect the new desktop.')
