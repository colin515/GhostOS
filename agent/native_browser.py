"""Navigate an existing Chromium window without CDP, clipboard changes or blind page clicks."""
from __future__ import annotations
import json
import time
from agent.navigation import same_destination
from agent.windows_apps import WindowsApps


class NativeBrowser:
    def __init__(self, settings, stop, type_unicode):
        self.app = 'chrome' if settings.browser_channel == 'chrome' else 'edge'
        self.stop, self.type_unicode = stop, type_unicode
        self.apps = WindowsApps(stop)

    def check(self):
        if self.stop.is_set():
            raise InterruptedError('Stopped')

    def chrome(self, hwnd=None):
        """Read browser chrome only. Never treat a webpage input as the address bar."""
        import uiautomation as auto
        root = auto.ControlFromHandle(hwnd) if hwnd else auto.GetForegroundControl()
        tabs, address = [], ''
        visited = 0
        def visit(control, depth):
            nonlocal visited, address
            self.check()
            visited += 1
            if depth > 10 or visited > 350:
                return
            try:
                kind = control.ControlTypeName
                if kind == 'DocumentControl':
                    return  # excludes all web content, including forms
                if kind == 'TabItemControl':
                    try:
                        selected = control.GetSelectionItemPattern().IsSelected
                    except Exception:
                        selected = False
                    tabs.append((control, control.Name, selected))
                    return
                if kind == 'EditControl':
                    value = control.GetValuePattern().Value
                    # Only accept URL-shaped values outside web documents.
                    if value.startswith(('http://', 'https://', 'chrome://', 'edge://', 'about:')):
                        address = value
                    elif value and '.' in value and ' ' not in value and '/' not in value[:value.find('.')]:
                        address = 'https://' + value
                for child in control.GetChildren()[:80]:
                    visit(child, depth + 1)
            except (InterruptedError, PermissionError):
                raise
            except Exception:
                pass
        visit(root, 0)
        return tabs, address

    def snapshot(self):
        self.apps.focus(self.app)
        tabs, url = self.chrome()
        return json.dumps({'transport': 'native', 'url': url, 'verified': False,
                           'tabs': [{'title': title, 'selected': selected} for _, title, selected in tabs],
                           'message': 'Native browser controls: use the screenshot and UIA. DOM selectors require CDP.'})

    def reuse(self, url):
        """Look for an already-open site in all windows; verify the address after selection."""
        from urllib.parse import urlsplit
        from agent.window_focus import focus_window
        destination = urlsplit(url)
        host = (destination.hostname or '').removeprefix('www.').split('.')[0].casefold()
        hint = destination.path.rstrip('/').rsplit('/', 1)[-1].casefold()
        until_reuse = time.monotonic() + 8
        for hwnd in self.apps.windows(self.app):
            self.check()
            focus_window(hwnd, self.stop)
            tabs, current = self.chrome(hwnd)
            if same_destination(current, url):
                return self.result(current, reused=True)
            # A title is just a candidate. Only a matching actual URL counts as success.
            ordered = sorted(tabs, key=lambda tab: not (host in tab[1].casefold() or (hint and hint in tab[1].casefold())))
            for control, title, selected in ordered[:32]:
                if selected or time.monotonic() >= until_reuse:
                    continue
                try:
                    try:
                        control.GetSelectionItemPattern().Select()
                    except Exception:
                        # Some Chromium builds expose tabs without SelectionItem.
                        # A real smooth click on the UIA tab centre is a safe navigation fallback.
                        from agent.mouse import MouseDriver
                        rect = control.BoundingRectangle
                        MouseDriver(self.stop).click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                    until = min(until_reuse, time.monotonic() + 0.5)
                    while time.monotonic() < until:
                        self.check()
                        _, current = self.chrome(hwnd)
                        if same_destination(current, url):
                            return self.result(current, reused=True)
                        if self.stop.wait(0.1):
                            self.check()
                except (PermissionError, InterruptedError):
                    raise
                except Exception:
                    continue
        return None

    @staticmethod
    def result(url='', created=False, reused=False, verified=True):
        return json.dumps({'transport': 'native', 'url': url, 'verified': verified,
                           'created_tab': created, 'reused_tab': reused})

    def open(self, url='', new_tab=False, reuse_only=False):
        if not new_tab and url:
            result = self.reuse(url)
            if result or reuse_only:
                return result
        elif reuse_only:
            return None
        self.apps.ensure(self.app, 'launch')
        import pyautogui as pg
        import win32gui
        pg.PAUSE, pg.FAILSAFE = 0.05, True
        hwnd = win32gui.GetForegroundWindow()
        before, _ = self.chrome(hwnd)
        created = False
        if new_tab and not before:
            raise RuntimeError('Tab strip is not observable through UIA; no key was sent')
        if new_tab:
            self.check()
            pg.hotkey('ctrl', 't')
            until = time.monotonic() + 4
            while time.monotonic() < until:
                self.check()
                tabs, _ = self.chrome(hwnd)
                if len(tabs) > len(before):
                    created = True
                    break
                if self.stop.wait(0.1):
                    self.check()
            if not created:
                raise RuntimeError('Ctrl+T was sent but a new tab could not be verified; inspect the browser')
        if url:
            self.check()
            if win32gui.GetForegroundWindow() != hwnd:
                raise RuntimeError('Browser lost focus before address entry')
            pg.hotkey('ctrl', 'l')
            self.check()
            # Verify the focused editor belongs to browser chrome before typing.
            import uiautomation as auto
            focused = auto.GetFocusedControl()
            if focused.ControlTypeName != 'EditControl':
                raise RuntimeError('Address bar did not acquire focus')
            parent = focused
            for _ in range(16):
                if parent.ControlTypeName == 'DocumentControl':
                    raise RuntimeError('Refusing to enter a URL into webpage content')
                if parent.NativeWindowHandle == hwnd:
                    break
                parent = parent.GetParentControl()
                if not parent:
                    raise RuntimeError('Could not verify address bar ownership')
            else:
                raise RuntimeError('Could not verify browser address bar')
            if win32gui.GetForegroundWindow() != hwnd:
                raise RuntimeError('Browser lost focus during address entry')
            self.type_unicode(url)
            self.check()
            pg.press('enter')
            until = time.monotonic() + 8
            while time.monotonic() < until:
                self.check()
                _, current = self.chrome(hwnd)
                if same_destination(current, url):
                    return self.result(current, created=created)
                if self.stop.wait(0.15):
                    self.check()
            raise RuntimeError('Navigation was sent but the requested address could not be verified')
        return self.result(created=created, verified=created)
