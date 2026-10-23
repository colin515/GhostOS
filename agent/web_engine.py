"""One worker thread owns Playwright. Use an isolated profile unless CDP is explicit."""
from __future__ import annotations
from config import Settings

class WebEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright = self.browser = self.context = self.page = None
        self.attached = False

    def start(self):
        if self.page:
            return
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        if self.settings.cdp_url:
            self.browser = self.playwright.chromium.connect_over_cdp(self.settings.cdp_url, timeout=10000)
            self.attached = True
            if not self.browser.contexts:
                raise RuntimeError('CDP endpoint has no browser context')
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        else:
            # Microsoft Edge is provided by Windows; no bundled Chromium download required.
            self.context = self.playwright.chromium.launch_persistent_context(
                str(self.settings.data_dir / ('browser-profile-' + self.settings.browser_channel)), channel=self.settings.browser_channel, headless=False,
                viewport=None, accept_downloads=False, timeout=15000)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(8000)

    def snapshot(self):
        if not self.page:
            return ''
        # Read only; avoid password/value extraction and unbounded DOM dumps.
        text = self.page.locator('body').inner_text(timeout=5000)[:5000]
        controls = self.page.locator('input,button,select,textarea,a').evaluate_all('''els => els.slice(0,80).map(e => ({
            tag:e.tagName, type:e.type || '', name:e.name || '', id:e.id || '',
            label:e.getAttribute('aria-label') || (e.innerText || '').slice(0,80)}))''')
        import json
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
        if self.context and not self.attached:
            self.context.close()
        # Do not close the user's browser when attached by CDP.
        if self.playwright:
            self.playwright.stop()
