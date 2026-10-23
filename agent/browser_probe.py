"""Deterministic Windows CDP smoke test using a disposable profile and local form."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.request import build_opener, ProxyHandler
from config import Settings
from agent.models import Action
from agent.web_engine import WebEngine

PAGE = b'''<!doctype html><title>GhostOS browser verification</title>
<label for="q">Search</label><input id="q"><button id="go" onclick="document.querySelector('#result').textContent=document.querySelector('#q').value">Search</button><output id="result"></output>'''


def run_probe():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(PAGE)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    web = reconnected = None
    try:
        with tempfile.TemporaryDirectory(prefix='GhostOS-CDP-check-', ignore_cleanup_errors=True) as root:
            settings = Settings(data_dir=Path(root), browser_channel='msedge')
            web = WebEngine(settings)
            url = f'http://127.0.0.1:{server.server_port}/'
            web.execute(Action(kind='browser_navigate', args={'url':url}))
            web.execute(Action(kind='browser_fill', args={'selector':'#q', 'value':'GhostOS CDP verified'}))
            web.execute(Action(kind='browser_click', args={'selector':'#go'}))
            if web.page.locator('#result').inner_text() != 'GhostOS CDP verified':
                raise RuntimeError('CDP form result did not match')
            port_file = Path(root) / 'cdp-profile-msedge' / 'DevToolsActivePort'
            port = int(port_file.read_text().splitlines()[0])
            endpoint = f'http://127.0.0.1:{port}'
            web.close()
            # A disconnected worker must leave the user's result page intact.
            with build_opener(ProxyHandler({})).open(endpoint + '/json/list', timeout=5) as response:
                if not any(page.get('url') == url for page in json.load(response)):
                    raise RuntimeError('Result tab closed when CDP disconnected')
            reconnected = WebEngine(Settings(data_dir=Path(root), cdp_url=endpoint))
            reconnected.start()
            if reconnected.page.locator('#result').inner_text() != 'GhostOS CDP verified':
                raise RuntimeError('Result state was lost on reconnect')
            print('Verified CDP native browser launch, DOM navigation/fill/click, disconnect and persistent result tab')
    finally:
        # Only the disposable browser started by this explicit probe is closed.
        current = reconnected or web
        if current and current.browser:
            try:
                current.browser.new_browser_cdp_session().send('Browser.close')
            except Exception:
                pass
        for connection in (reconnected, web):
            if connection:
                connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
        time.sleep(0.2)
    return 0
