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
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(8000)

    def snapshot(self):
        if not self.page:
            return ''
        text = self.page.locator('body').inner_text(timeout=5000)[:5000]
        controls = self.page.locator('input,button,select,textarea,a').evaluate_all('''els => els.slice(0,80).map(e => ({
            tag:e.tagName, type:e.type || '', name:e.name || '', id:e.id || '',
            label:e.getAttribute('aria-label') || (e.innerText || '').slice(0,80)}))''')
        return json.dumps({'url': self.page.url, 'text': text, 'controls': controls})[:7000]

    def execute(self, action):
        self.start()
        a = action.args
        if action.kind == 'browser_navigate':
            self.page.goto(a['url'], wait_until='domcontentloaded', timeout=20000)
        elif action.kind == 'browser_fill':
            self.page.locator(a['selector']).fill(a['value'])
        elif action.kind == 'browser_click':
            self.page.locator(a['selector']).click()
        elif action.kind != 'browser_snapshot':
            raise ValueError('Unknown browser action')
        return self.snapshot()

    def close(self):
        # Disconnect only. Closing context/browser would destroy the user's completed task.
        if self.playwright:
            self.playwright.stop()
        self.playwright = self.browser = self.context = self.page = None
