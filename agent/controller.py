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
        self.browser_explicit = False

    def execute(self, action: Action):
        self.safety.authorize(action)
        self.safety.check()  # Stop may have arrived at the approval boundary.
        self.safety.events.put({'kind': 'EXECUTING', 'action': action.model_dump()}, timeout=0.2)
        kind, a = action.kind, action.args
        if kind in ('hotkey', 'type_text', 'click', 'mouse_move', 'drag', 'scroll', 'ui_click', 'template_click'):
            self.focus_guard.ensure_external()
        if kind == 'app_list':
            from agent.windows_apps import WindowsApps
            apps = WindowsApps(self.safety.stop).registered_apps()
            from agent.installed_games import installed_games
            apps = dict(apps)
            apps.update({name:'steam://' + game.app_id for name,game in installed_games().items()})
            query = a['query'].casefold()
            return json.dumps({'installed_apps':[name for name in apps if query in name.casefold()][:100]})
        if kind == 'focus_window':
            from agent.window_focus import focus_window
            hwnd = focus_window(a['hwnd'], self.safety.stop)
            return json.dumps({'verified':True, 'foreground':True, 'hwnd':hwnd})
        if kind == 'ensure_app':
            from agent.windows_apps import WindowsApps
            return WindowsApps(self.safety.stop).ensure(a['name'], a['strategy'], self.type_unicode)
        if kind.startswith('browser_'):
            return self.browser_action(action)
        if kind == 'shell':
            return self.shell(a['script'], a['timeout'])
        if kind == 'wait':
            if self.safety.stop.wait(a['seconds']):
                self.safety.check()
            return 'Wait finished'
        if kind == 'focus':
            if self.game is not None:
                from agent.window_focus import focus_window
                focus_window(self.game.target,self.safety.stop)
                return 'Restored the pinned game window'
            if self.settings.game_mode:
                raise RuntimeError('No game window is pinned yet; focus the intended game before game input')
            self.focus_guard.ensure_external()
            if self.focus_guard.last:
                from agent.window_focus import focus_window
                focus_window(self.focus_guard.last, self.safety.stop)
            return 'Requested foreground window focus'
        if kind == 'ui_click':
            from agent.targeting import verify_window
            verify_window(self.frame,geometry=False)
            x, y = self.tree.center(a['element_id'])
            from agent.targeting import verify_live_center
            mouse = self.mouse_driver()
            mouse.before_press = lambda: verify_live_center((x,y),self.tree.center(a['element_id']))
            mouse.click(x, y)
            return 'UIA control clicked'
        if kind.startswith('game_'):
            if not self.settings.game_mode:
                raise PermissionError('Enable Game Mode first')
            if kind == 'game_bind':
                from agent.targeting import verify_window
                verify_window(self.frame,geometry=False)
                import win32gui
                if not self.frame or not self.frame.window or win32gui.GetWindowText(self.frame.window).casefold() != a['title'].casefold():
                    raise ValueError('Game binding requires the exact title of the currently captured foreground window')
                if self.game:
                    self.game.close()
                from agent.gaming_engine import GamingEngine
                self.game = GamingEngine(self.safety.stop,target=self.frame.window)
                return json.dumps({'verified':True,'game_window':self.game.target,'title':a['title']})
            if self.game is None:
                from agent.gaming_engine import GamingEngine
                self.game = GamingEngine(self.safety.stop,target=self.frame.window if self.frame else None)
            if kind == 'game_move':
                self.game.move(a['dx'], a['dy'])
            elif kind == 'game_key':
                self.game.key(a['key'], a['duration'])
            elif kind == 'game_click':
                self.game.click(a['button'])
            elif kind == 'game_action':
                self.game.action(**a)
            return 'Game input sent'
        if kind in ('click', 'mouse_move', 'drag'):
            from agent.targeting import resolve_point, verify_window, verify_patch
            if kind in ('drag','mouse_move'):
                verify_window(self.frame)
            if kind == 'mouse_move' and self.frame:
                x,y = self.frame.point(a['x'],a['y'],a.get('coordinate_space','screenshot'))
                source = 'vision'
            else:
                (x,y),source = resolve_point(self.frame,a,self.tree,self.vision,self.settings.game_mode)
            snapped_id = None
            if kind == 'click' and source.startswith('vision-') and not self.settings.game_mode:
                finder = getattr(self.tree, 'nearest_click_target', None)
                match = finder(x, y) if callable(finder) else None
                if match:
                    from agent.targeting import verify_patch
                    snapped_id, x, y = match
                    verify_patch(self.frame, self.vision.capture(), (x, y))
                    source = 'accessibility-snap'
            sx,sy = self.frame.model_point(x,y)
            self.safety.events.put({'kind':'TARGET','source':source,'physical':[x,y], 'screenshot':[sx,sy],
                                    'window':self.frame.window,'label':a.get('target','')},timeout=0.2)
            self.safety.events.put({'kind':'FRAME','image':self.frame.annotated(sx,sy,a.get('target') or kind).base64()},timeout=0.2)
            mouse = self.mouse_driver()
            if source in ('accessibility-label', 'accessibility-snap'):
                from agent.targeting import verify_live_center
                mouse.before_press = (lambda: (verify_window(self.frame),
                    verify_live_center((x,y), self.tree.center(snapped_id) if snapped_id is not None
                                       else self.tree.find(a['target']))))
            else:
                mouse.before_press = lambda: verify_window(self.frame)
            if kind == 'mouse_move':
                mouse.move(x, y, a['duration'])
            elif kind == 'drag':
                to_x, to_y = self.frame.point(a['to_x'], a['to_y'],a.get('coordinate_space','screenshot'))
                if not self.settings.game_mode:
                    verify_patch(self.frame,self.vision.capture(),(to_x,to_y))
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
                    self.game = GamingEngine(self.safety.stop,target=frame.window)
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

    def native_browser(self):
        from agent.native_browser import NativeBrowser
        browser = NativeBrowser(self.settings, self.safety.stop, self.type_unicode)
        if os.name == 'nt' and not self.browser_explicit and not self.settings.cdp_url:
            # "the current YouTube page" belongs to the foreground browser, which
            # can differ from the configured browser used to create new sessions.
            try:
                import psutil
                import win32gui
                import win32process
                hwnd = win32gui.GetForegroundWindow()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                executable = psutil.Process(pid).name().lower()
                if executable in ('chrome.exe', 'msedge.exe'):
                    browser.app = 'chrome' if executable == 'chrome.exe' else 'edge'
            except (OSError, psutil.Error):
                pass
        return browser

    def browser_action(self, action):
        if 'url' in action.args:
            from agent.navigation import canonical_destination
            canonical = canonical_destination(getattr(self,'original_goal',''),action.args['url'])
            if canonical != action.args['url']:
                self.safety.events.put({'kind':'BROWSER_TARGET_CORRECTED','message':'Using the canonical ChatGPT destination requested by the user.'},timeout=.2)
                action = Action(kind=action.kind,args={**action.args,'url':canonical})
        kind, a = action.kind, action.args
        navigation = kind in ('browser_open', 'browser_navigate', 'browser_new_tab')
        backend = a.get('backend', 'auto')
        if kind == 'browser_media' and not self.web.page and not getattr(self.settings, 'cdp_url', ''):
            native = self.native_browser()
            if native.apps.windows(native.app):
                from agent.browser_media import native_media
                self.web.native_fallback = True
                return native_media(native, a['operation'])
        if navigation and backend == 'native':
            result = self.native_browser().open(a.get('url', ''), a.get('new_tab', kind == 'browser_new_tab'))
            self.web.native_fallback = True
            return result
        if kind == 'browser_new_tab' and backend == 'auto' and not self.web.page and not getattr(self.settings, 'cdp_url', ''):
            try:
                native = self.native_browser()
                if native.apps.windows(native.app):
                    result = native.open(new_tab=True)
                    self.web.native_fallback = True
                    return result
            except (InterruptedError, PermissionError):
                raise
            except Exception:
                pass
        # Respect an existing personal Chrome/Edge tab before creating a managed profile.
        if kind == 'browser_open' and backend == 'auto' and not self.web.page and not a['new_tab'] and not getattr(self.settings, 'cdp_url', ''):
            try:
                reused = self.native_browser().open(a['url'], reuse_only=True)
                if reused:
                    self.web.native_fallback = True
                    return reused
            except (InterruptedError, PermissionError):
                raise
            except Exception:
                pass  # UIA unavailable: CDP still provides deterministic URL navigation.
        if self.web.native_fallback and backend != 'cdp':
            if kind == 'browser_media':
                from agent.browser_media import native_media
                return native_media(self.native_browser(), a['operation'])
            if navigation:
                return self.native_browser().open(a.get('url', ''), a.get('new_tab', kind == 'browser_new_tab'))
            if kind in ('browser_snapshot', 'browser_tabs'):
                return self.native_browser().snapshot()
            return 'Native browser mode. DOM selectors are unavailable; inspect fresh UIA/screenshot and use mouse controls. No form action was executed.'
        if backend == 'cdp':
            self.web.native_fallback = False
        try:
            return self.web.execute(action)
        except (InterruptedError, PermissionError):
            raise
        except Exception as exc:
            self.web.native_fallback = True
            self.web.close()
            self.safety.events.put({'kind': 'BROWSER_FALLBACK', 'message': f'CDP unavailable: {exc}. Using mouse and keyboard. Would you like setup instructions?', 'help_offer': True}, timeout=0.2)
            if navigation:
                return self.native_browser().open(a.get('url', ''), a.get('new_tab', kind == 'browser_new_tab'))
            # Never replay uncertain form writes/clicks through another transport.
            return 'CDP failed; outcome uncertain. Do not replay a form submission. Use fresh screenshot, mouse and keyboard controls. Browser selectors are unavailable.'

    def navigation_evidence(self, navigation):
        """Read-only completion check: never focus a window or send input from this path."""
        if navigation.url or navigation.new_tab:
            if self.web.page:
                return self.web.snapshot(verified=True)
            import win32gui
            native = self.native_browser()
            hwnd = win32gui.GetForegroundWindow()
            if hwnd in native.apps.windows(native.app):
                _, url = native.chrome(hwnd)
                return json.dumps({'verified': True, 'url': url})
        return None

    def mouse_driver(self):
        if self.mouse is None:
            from agent.mouse import MouseDriver
            self.mouse = MouseDriver(self.safety.stop, lambda **e: self.safety.events.put(e, timeout=0.2))
        from agent.targeting import verify_window
        self.mouse.guard = lambda: verify_window(self.frame,geometry=False)
        self.mouse.before_press = None
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
