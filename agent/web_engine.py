"""CDP first using a dedicated loopback-only browser profile; preserve results after exit."""
from __future__ import annotations
import io
import json
from PIL import Image
from agent.vision import Frame
import subprocess
import time
from config import Settings


class WebEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright = self.browser = self.context = self.page = None
        self.attached = False
        self.native_fallback = False
        self._targets = {}
        self._targets_page = None

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

    # Unlike Windows screenshots, Playwright screenshots and mouse actions share
    # CSS viewport coordinates. Never convert these via the OS window rectangle.
    ACTIONABLE = 'a[href],button,input,select,textarea,[role="button"],[role="link"],[role="tab"],video'

    def capture_frame(self):
        if not self.page or self.native_fallback:
            raise RuntimeError('CDP page is not available for viewport capture')
        pixels = Image.open(io.BytesIO(self.page.screenshot(
            type='jpeg', quality=80, full_page=False, scale='css', timeout=8000))).convert('RGB')
        original = pixels.size
        if pixels.width > self.settings.screenshot_width:
            pixels.thumbnail((self.settings.screenshot_width, pixels.height * 2),
                             Image.Resampling.LANCZOS)
        return Frame(pixels, original, origin=(0, 0), window=None,
                     title=self.page.url[:200], source='browser')

    def _track_new_tabs(self, before):
        opened = [page for page in self.context.pages
                  if page not in before and not page.is_closed()]
        if opened:
            self.page = opened[-1]
            self.page.bring_to_front()
            self._targets.clear()
            self._targets_page = None

    def click_at(self, x, y, button='left', clicks=1):
        """Click the exact CSS pixel of the observed browser image, not the desktop.

        The element at that pixel must actually be interactive. An overlay wins
        hit-testing and is not silently replaced with an underlying video/card.
        """
        if not self.page or self.native_fallback:
            raise RuntimeError('Browser viewport is unavailable; refresh the target')
        if button not in ('left', 'right', 'middle'):
            raise ValueError('CDP browser mouse supports left/right/middle')
        hit = self.page.evaluate("""([x,y]) => {
          const w=innerWidth,h=innerHeight;
          if(x<0||y<0||x>=w||y>=h) return {error:'out_of_viewport',width:w,height:h};
          let e=document.elementFromPoint(x,y);
          if(!e) return {error:'empty',width:w,height:h};
          const interactive=e.closest('a[href],button,input,select,textarea,[role="button"],[role="link"],[role="tab"],video');
          if(!interactive) return {error:'not_interactive',tag:e.tagName,
                                  label:(e.innerText||'').slice(0,70)};
          return {tag:interactive.tagName,role:interactive.getAttribute('role')||'',
                  label:(interactive.getAttribute('aria-label')||interactive.innerText||'').trim().slice(0,100),
                  href:interactive.getAttribute('href')||''};
        }""", [x, y])
        if hit.get('error'):
            raise ValueError('CDP viewport did not hit a clickable page element: ' +
                             str(hit)[:300] + '. Use browser_click_target from snapshot.')
        before = set(self.context.pages)
        self.page.mouse.click(x, y, button=button, click_count=clicks)
        self._track_new_tabs(before)
        return json.dumps({'transport':'cdp','click_dispatched':True,'hit':hit,
                           'url':self.page.url,'message':'Inspect next browser snapshot to verify outcome'},
                          ensure_ascii=False)

    def click_target(self, target_id):
        """Re-find the visible DOM target by snapshot index + identity, then click."""
        if not self.page or self.native_fallback or self._targets_page is not self.page:
            raise ValueError('Stale browser target list; run browser_snapshot again')
        expected = self._targets.get(target_id)
        if expected is None:
            raise ValueError('Unknown browser target ID; use one from latest browser_snapshot')
        target = self.page.locator(self.ACTIONABLE).nth(expected['dom_index'])
        if target.count() != 1:
            raise ValueError('Browser target disappeared; refresh browser_snapshot')
        actual = target.evaluate("""e => ({
            tag:e.tagName,href:e.getAttribute('href')||'',
            id:e.id||'',name:e.getAttribute('aria-label')||'',
            text:(e.innerText||e.value||'').trim().slice(0,90)
        })""")
        # Text on dynamic widgets can change. Link destinations must never
        # change between observation and click; otherwise stale ID could
        # click an entirely different navigation target.
        if actual['tag'] != expected['tag'] or actual['href'] != expected['href']:
            raise ValueError('Browser target changed identity; refresh browser_snapshot')
        if not expected['href'] and actual['id'] != expected['id']:
            raise ValueError('Browser target ID changed; refresh browser_snapshot')
        before = set(self.context.pages)
        target.click()  # real Playwright actionability/scroll/overlay checks
        self._track_new_tabs(before)
        return self.snapshot(click_dispatched=True, clicked_target_id=target_id)

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
            discovered = self.page.locator(self.ACTIONABLE).evaluate_all("""els => {
                const w=innerWidth,h=innerHeight;
                const targets=[];
                for(let i=0;i<els.length&&targets.length<100;i++){
                    const e=els[i],r=e.getBoundingClientRect(),st=getComputedStyle(e);
                    if(r.width<4||r.height<4||st.visibility==='hidden'||st.display==='none')continue;
                    const x=Math.max(0,Math.min(w-1,r.left+r.width/2));
                    const y=Math.max(0,Math.min(h-1,r.top+r.height/2));
                    if(r.right<0||r.bottom<0||r.left>=w||r.top>=h)continue;
                    const name=(e.getAttribute('aria-label')||e.innerText||e.value||'').trim().slice(0,90);
                    targets.push({dom_index:i,tag:e.tagName,href:e.getAttribute('href')||'',
                      id:e.id||'',name,
                      x:Math.round(x),y:Math.round(y)});
                }
                return {viewport:{width:w,height:h},targets};
            }""")
            self._targets = {idx:item for idx,item in enumerate(discovered['targets'])}
            self._targets_page = self.page
            data['viewport'] = discovered['viewport']
            data['targets'] = [
                {**{k:v for k,v in item.items() if k!='dom_index'}, 'target_id':idx}
                for idx,item in self._targets.items()]
            data['visible_video_links'] = sum(
                '/watch?' in item['href'] or '/shorts/' in item['href']
                for item in self._targets.values())
            data['controls'] = [{'tag':t['tag'], 'label':t['name'],
                                 'href':t['href'], 'target_id':t['target_id']}
                                for t in data['targets'][:45]]
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
        elif action.kind == 'browser_click_target':
            return self.click_target(a['target_id'])
        elif action.kind == 'browser_fill':
            target = self.page.locator(a['selector'])
            count = target.count()
            if count != 1:
                raise ValueError(f'Browser selector matched {count} fields; no text entered. '
                                 'Inspect browser_snapshot and choose an exact unique selector.')
            target.fill(a['value'])
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
            target = self.page.locator(a['selector'])
            count = target.count()
            if count != 1:
                raise ValueError(f'Browser selector matched {count} elements; no click sent. '
                                 'Inspect browser_snapshot and choose an exact unique selector.')
            target.click()  # Playwright checks visibility, actionability and scroll.
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
        self._targets.clear()
        self._targets_page = None
