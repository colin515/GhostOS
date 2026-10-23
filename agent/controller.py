"""All executable capabilities pass through authorize(), including recovery actions."""
from __future__ import annotations
import base64
import json
import os
import subprocess
from config import RESOURCE_DIR
from agent.models import Action
from agent.web_engine import WebEngine

class Controller:
    def __init__(self, settings, safety, tree, vision):
        self.settings, self.safety, self.tree, self.vision = settings, safety, tree, vision
        self.web = WebEngine(settings)
        self.game = None
        from agent.window_focus import FocusGuard
        self.focus_guard = FocusGuard(safety.stop)
        self.focus_guard.observe()
        self.mouse = None
        self.frame = None
        self.process = None

    def execute(self, action: Action):
        self.safety.authorize(action)
        self.safety.check()  # Stop may have arrived at the approval boundary.
        self.safety.events.put({'kind': 'EXECUTING', 'action': action.model_dump()}, timeout=0.2)
        kind, a = action.kind, action.args
        if kind in ('hotkey', 'type_text', 'click', 'mouse_move', 'drag', 'scroll', 'ui_click', 'template_click'):
            self.focus_guard.ensure_external()
        if kind == 'ensure_app':
            from agent.windows_apps import WindowsApps
            return WindowsApps(self.safety.stop).ensure(a['name'], a['strategy'], self.type_unicode)
        if kind.startswith('browser_'):
            try:
                return self.web.execute(action)
            except (InterruptedError, PermissionError):
                raise
            except Exception as exc:
                self.web.native_fallback = True
                self.web.close()
                self.safety.events.put({'kind': 'BROWSER_FALLBACK', 'message': f'CDP unavailable: {exc}. Using mouse and keyboard. Would you like setup instructions?', 'help_offer': True}, timeout=0.2)
                from agent.windows_apps import WindowsApps
                app = 'chrome' if self.settings.browser_channel == 'chrome' else 'edge'
                apps = WindowsApps(self.safety.stop)
                if kind == 'browser_navigate':
                    path = apps.installed_path(app)
                    if path is None:
                        raise FileNotFoundError(f'{app} is not installed')
                    subprocess.Popen([str(path), a['url']], shell=False)
                    apps._wait_for_window(app)
                    return 'Native browser opened the URL. CDP disabled for this run; use the visible mouse, UIA and keyboard. Inspect the new screenshot.'
                return 'CDP failed; outcome uncertain. Do not replay a form submission. Use fresh screenshot, mouse and keyboard controls. Browser selectors are unavailable.' 
        if kind == 'shell':
            return self.shell(a['script'], a['timeout'])
        if kind == 'wait':
            if self.safety.stop.wait(a['seconds']):
                self.safety.check()
            return 'Wait finished'
        if kind == 'focus':
            self.focus_guard.ensure_external()
            if self.focus_guard.last:
                from agent.window_focus import focus_window
                focus_window(self.focus_guard.last, self.safety.stop)
            return 'Requested foreground window focus'
        if kind == 'ui_click':
            x, y = self.tree.center(a['element_id'])
            self.mouse_driver().click(x, y)
            return 'UIA control clicked'
        if kind.startswith('game_'):
            if not self.settings.game_mode:
                raise PermissionError('Enable Game Mode first')
            if self.game is None:
                from agent.gaming_engine import GamingEngine
                self.game = GamingEngine(self.safety.stop)
            if kind == 'game_move':
                self.game.move(a['dx'], a['dy'])
            elif kind == 'game_key':
                self.game.key(a['key'], a['duration'])
            elif kind == 'game_click':
                self.game.click()
            return 'Game input sent'
        if kind in ('click', 'mouse_move', 'drag'):
            if self.frame is None:
                raise RuntimeError('A screenshot is required for coordinate input')
            x, y = self.frame.physical(a['x'], a['y'])
            mouse = self.mouse_driver()
            if kind == 'mouse_move':
                mouse.move(x, y, a['duration'])
            elif kind == 'drag':
                to_x, to_y = self.frame.physical(a['to_x'], a['to_y'])
                mouse.drag(x, y, to_x, to_y, a['button'], a['duration'])
            else:
                mouse.click(x, y, a['button'], a['clicks'], a['duration'])
            return f'{kind} verified at physical pixels {x}, {y}'
        if kind == 'scroll':
            self.mouse_driver().scroll(a['ticks'], a['horizontal'])
            return 'Wheel input sent'
        import pyautogui as pg
        pg.FAILSAFE, pg.PAUSE = True, 0.05
        if kind == 'hotkey':
            keys = a['keys']
            if any(key.lower() not in pg.KEYBOARD_KEYS for key in keys):
                raise ValueError('Unsupported key name')
            try:
                for key in keys:
                    self.safety.check()
                    pg.keyDown(key.lower())
            finally:
                for key in reversed(keys):
                    pg.keyUp(key.lower())
        elif kind == 'type_text':
            self.type_unicode(a['text'])
        elif kind == 'template_click':
            frame = self.vision.capture()
            match = self.vision.match(frame, a['name'], a['threshold'])
            if not match:
                raise RuntimeError('Template not visible')
            x, y = frame.physical(match['x'], match['y'])
            if self.settings.game_mode:
                if self.game is None:
                    from agent.gaming_engine import GamingEngine
                    self.game = GamingEngine(self.safety.stop)
                self.game.check_focus()
            self.mouse_driver().click(x, y)
        elif kind == 'open_app':
            shortcuts = json.loads((RESOURCE_DIR / 'shortcuts.json').read_text(encoding='utf-8'))
            target = shortcuts.get(a['name'].lower())
            if target is None:
                from agent.windows_apps import WindowsApps
                return WindowsApps(self.safety.stop).ensure(a['name'], 'launch', self.type_unicode)
            # Fixed packaged executable paths/arguments; never interpolate goal text.
            subprocess.Popen([os.path.expandvars(part) for part in target])
        else:
            raise ValueError('Unknown action')
        return f'{kind} executed'

    def mouse_driver(self):
        if self.mouse is None:
            from agent.mouse import MouseDriver
            self.mouse = MouseDriver(self.safety.stop, lambda **e: self.safety.events.put(e, timeout=0.2))
        return self.mouse

    def type_unicode(self, text):
        from agent.gaming_engine import INPUT, KEYBDINPUT, send_input
        # Unicode SendInput avoids clipboard mutation, keyboard layout problems and arbitrary paste contents.
        encoded = text.encode('utf-16-le')
        for offset in range(0, len(encoded), 2):
            self.safety.check()
            unit = int.from_bytes(encoded[offset:offset + 2], 'little')
            send_input([INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4)),
                        INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4 | 2))])

    def shell(self, script, timeout):
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        command = [os.path.join(os.environ['SystemRoot'], 'System32', 'WindowsPowerShell', 'v1.0',
                                'powershell.exe'), '-NoLogo', '-NoProfile', '-NonInteractive',
                   '-EncodedCommand', encoded]
        # No -ExecutionPolicy Bypass, runas, shell=True or inherited admin token.
        from agent.processes import ChildJob, kill_tree
        import tempfile
        import time
        with tempfile.TemporaryFile() as out:
            self.process = subprocess.Popen(command, cwd=self.settings.data_dir,
                                            stdout=out, stderr=subprocess.STDOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
            job = None
            deadline = time.monotonic() + timeout
            try:
                job = ChildJob(self.process)
                while self.process.poll() is None:
                    self.safety.check()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('PowerShell time budget exceeded')
                    self.safety.stop.wait(0.05)
                out.seek(0)
                content = out.read(24000).decode('utf-8', errors='replace')
                if self.process.returncode:
                    raise RuntimeError(f'PowerShell exit {self.process.returncode}: {content}')
                return content or 'PowerShell completed (no output)'
            finally:
                kill_tree(self.process.pid)
                if job:
                    job.close()
                self.process = None

    def close(self):
        if self.game:
            self.game.close()
        self.web.close()
