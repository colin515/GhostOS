"""CDP first using a dedicated loopback-only browser profile; preserve results after exit."""
from __future__ import annotations
import json
import subprocess
import time
from config import Settings


class WebEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright = self.browser = self.context = self.page = None
        self.attached = False
        self.native_fallback = False

    def start(self):
        if self.native_fallback:
            raise RuntimeError('CDP disabled after failure; use native controls')
        if self.page:
            return
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        endpoint = self.settings.cdp_url
        if not endpoint:
            from agent.windows_apps import WindowsApps
            import threading
            apps = WindowsApps(threading.Event())
            path = apps.installed_path('chrome' if self.settings.browser_channel == 'chrome' else 'edge')
            if path is None:
                raise FileNotFoundError('Selected browser is not installed')
            profile = self.settings.data_dir / ('cdp-profile-' + self.settings.browser_channel)
            profile.mkdir(parents=True, exist_ok=True)
            port_file = profile / 'DevToolsActivePort'
            # A stale port is harmless: try attaching first, then launch only when necessary.
            if port_file.exists():
                try:
                    port = int(port_file.read_text().splitlines()[0])
                    self.browser = self.playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}', timeout=2000)
                except Exception:
                    port_file.unlink(missing_ok=True)
            if self.browser is None:
                subprocess.Popen([str(path), '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
                                  '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check',
                                  'about:blank'], shell=False)
                until = time.monotonic() + 10
                while not port_file.exists() and time.monotonic() < until:
                    time.sleep(0.1)
                if not port_file.exists():
                    raise RuntimeError('Browser did not expose a CDP endpoint')
                port = int(port_file.read_text().splitlines()[0])
                if not 1 <= port <= 65535:
                    raise ValueError('Invalid CDP port')
                endpoint = f'http://127.0.0.1:{port}'
        if self.browser is None:
            self.browser = self.playwright.chromium.connect_over_cdp(endpoint, timeout=8000)
        self.attached = True
        if not self.browser.contexts:
            raise RuntimeError('CDP endpoint has no browser context')
        self.context = self.browser.contexts[0]
        self.page = self.select_active_page(self.context.pages) if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(8000)

    @staticmethod
    def select_active_page(pages):
        """CDP page order changes across reconnects; prefer the actually visible tab."""
        visible = []
        for page in pages:
            try:
                if not page.is_closed() and page.evaluate('document.visibilityState') == 'visible':
                    visible.append(page)
            except Exception:
                continue
        if len(visible) > 1:
            # Several browser windows can each have a visible tab. Match the foreground
            # title when available; never change focus just to perform this observation.
            import os
            if os.name == 'nt':
                import win32gui
                foreground = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                for page in visible:
                    try:
                        title = page.title()
                        if title and foreground.startswith(title):
                            return page
                    except Exception:
                        continue
        return visible[0] if visible else pages[0]

    def tabs(self):
        output = []
        for i, page in enumerate(self.context.pages[:100]):
            try:
                if not page.is_closed():
                    output.append({'id': i, 'title': page.title()[:200], 'url': page.url, 'active': page == self.page})
            except Exception:
                continue  # An unrelated tab can close while the inventory is read.
        return output

    def snapshot(self, **evidence):
        if not self.page:
            return ''
        # Metadata survives blank pages, loading pages and missing body elements.
        data = {'transport': 'cdp', 'url': self.page.url, 'tabs': self.tabs(), **evidence}
        try:
            data['text'] = self.page.locator('body').inner_text(timeout=2000)[:5000]
            data['controls'] = self.page.locator('input,button,select,textarea,a').evaluate_all('''els => els.slice(0,80).map(e => ({
                tag:e.tagName, type:e.type || '', name:e.name || '', id:e.id || '',
                label:e.getAttribute('aria-label') || (e.innerText || '').slice(0,80)}))''')
        except Exception as exc:
            data['observation_warning'] = str(exc)[:300]
        # Truncate fields, never serialized JSON (callers verify this evidence).
        return json.dumps(data, ensure_ascii=False)

    def execute(self, action):
        self.start()
        a, evidence = action.args, {}
        if action.kind in ('browser_navigate', 'browser_open'):
            from agent.navigation import same_destination
            reused, created = False, False
            if action.kind == 'browser_open':
                if a['new_tab']:
                    self.page = self.context.new_page()
                    created = True
                else:
                    for page in self.context.pages:
                        if not page.is_closed() and same_destination(page.url, a['url']):
                            self.page, reused = page, True
                            break
            if not reused:
                self.page.goto(a['url'], wait_until='domcontentloaded', timeout=20000)
            self.page.bring_to_front()
            evidence = {'verified': same_destination(self.page.url, a['url']),
                        'created_tab': created, 'reused_tab': reused}
        elif action.kind == 'browser_new_tab':
            before = len(self.context.pages)
            self.page = self.context.new_page()
            self.page.bring_to_front()
            evidence = {'created_tab': len(self.context.pages) > before, 'verified': True}
        elif action.kind == 'browser_switch_tab':
            pages = self.context.pages
            if a['tab_id'] >= len(pages) or pages[a['tab_id']].is_closed():
                raise ValueError('Stale tab ID; refresh browser_tabs')
            self.page = pages[a['tab_id']]
            self.page.bring_to_front()
        elif action.kind == 'browser_fill':
            self.page.locator(a['selector']).fill(a['value'])
        elif action.kind == 'browser_media':
            from agent.browser_media import cdp_media
            try:
                evidence = cdp_media(self.page, a['operation'])
            except Exception as exc:
                evidence = {'operation':a['operation'], 'verified':False,
                            'message':'Playback could not be verified. Inspect the current player controls: ' + str(exc)[:600]}
        elif action.kind == 'browser_click':
            # A click may open a new tab. Track it instead of continuing on the old page.
            before = set(self.context.pages)
            self.page.locator(a['selector']).click()
            self.page.wait_for_timeout(150)
            opened = [page for page in self.context.pages if page not in before and not page.is_closed()]
            if opened:
                self.page = opened[-1]
                self.page.bring_to_front()
        elif action.kind not in ('browser_snapshot', 'browser_tabs'):
            raise ValueError('Unknown browser action')
        return self.snapshot(**evidence)

    def close(self):
        # Disconnect only. Closing context/browser would destroy the user's completed task.
        if self.playwright:
            self.playwright.stop()
        self.playwright = self.browser = self.context = self.page = None
