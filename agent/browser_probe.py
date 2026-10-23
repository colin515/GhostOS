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
            self.wfile.write(PAGE.replace(b'GhostOS browser verification', b'Netflix verification' if self.path == '/netflix' else b'YouTube verification'))
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            if self.path == '/api/show':
                result = {'capabilities':['vision','tools']}
            elif self.path == '/api/chat':
                if len(body['messages'][-1].get('images', [])) != 1:
                    raise RuntimeError('Windows-Use did not send exactly one latest image')
                result = {'model':'ghostos-local-probe', 'done':True, 'message':{'role':'assistant','content':'',
                          'tool_calls':[{'function':{'name':'browser_new_tab','arguments':{}}}]}}
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    web = reconnected = None
    try:
        with tempfile.TemporaryDirectory(prefix='GhostOS-CDP-check-', ignore_cleanup_errors=True) as root:
            settings = Settings(data_dir=Path(root), browser_channel='msedge')
            web = WebEngine(settings)
            base_url = f'http://127.0.0.1:{server.server_port}/'
            url = base_url + 'youtube'
            web.execute(Action(kind='browser_navigate', args={'url':url}))
            web.execute(Action(kind='browser_fill', args={'selector':'#q', 'value':'GhostOS CDP verified'}))
            web.execute(Action(kind='browser_click', args={'selector':'#go'}))
            if web.page.locator('#result').inner_text() != 'GhostOS CDP verified':
                raise RuntimeError('CDP form result did not match')
            result_page = web.page
            # Reproduce the reported wrong-site failure without external websites or a model.
            web.execute(Action(kind='browser_new_tab'))
            web.execute(Action(kind='browser_navigate', args={'url':base_url + 'netflix'}))
            netflix = web.page
            web.page = result_page
            result_page.bring_to_front()
            state = json.loads(web.execute(Action(kind='browser_open', args={'url':base_url + 'netflix'})))
            if web.page != netflix or not state.get('reused_tab') or len(web.context.pages) != 2:
                raise RuntimeError('Existing destination tab was not reused from the wrong current page')
            before = len(web.context.pages)
            state = json.loads(web.execute(Action(kind='browser_new_tab')))
            if not state.get('created_tab') or len(web.context.pages) != before + 1:
                raise RuntimeError('A new tab was not actually created')
            web.execute(Action(kind='browser_switch_tab', args={'tab_id':0}))
            if web.page != result_page:
                raise RuntimeError('Explicit tab activation selected the wrong page')
            # Native UIA reuse and Ctrl+T/address-bar fallback in the same disposable Edge window.
            from agent.native_browser import NativeBrowser
            from agent.controller import Controller
            from agent.ui_tree import uia_context
            from types import SimpleNamespace
            controller = Controller.__new__(Controller)
            controller.safety = SimpleNamespace(check=lambda: None)
            native = NativeBrowser(settings, threading.Event(), controller.type_unicode)
            with uia_context():
                state = json.loads(native.open(base_url + 'netflix', reuse_only=True) or '{}')
                if not state.get('verified') or not state.get('reused_tab'):
                    raise RuntimeError('Native UIA did not switch to the existing destination tab')
                state = json.loads(native.open(base_url + 'native', new_tab=True))
                if not state.get('created_tab') or not state.get('verified'):
                    raise RuntimeError('Native Ctrl+T/address-bar navigation was not verified')
            # Real vendored SDK observation plus its Ollama tool-call parser, using a
            # loopback fake model. Planning must not execute tools outside Controller.
            from agent.windows_use_engine import WindowsUseBrain
            from agent.vision import Vision
            planner = WindowsUseBrain(Settings(data_dir=Path(root), model='ghostos-local-probe',
                                      ollama_host=f'http://127.0.0.1:{server.server_port}'))
            try:
                with uia_context():
                    frame = Vision().capture()
                    observed = planner.observation(frame)
                    if observed.get('engine') != 'Windows-Use' or not observed.get('controls'):
                        raise RuntimeError('Windows-Use cached UIA observation did not expose controls')
                    decision = planner.next('Open a new tab', frame, [])
                    if decision.action.kind != 'browser_new_tab':
                        raise RuntimeError('Windows-Use tool-call response was not translated correctly')
            finally:
                planner.close()
            web.page = result_page
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
            # Tab order/activation can change after reconnect. Locate the original
            # unique result URL and prove navigation reuses it without reloading.
            before = len(reconnected.context.pages)
            restored = json.loads(reconnected.execute(Action(kind='browser_open', args={'url':url})))
            if not restored.get('reused_tab') or len(reconnected.context.pages) != before:
                raise RuntimeError('Original result tab was not reused after reconnect')
            if reconnected.page.locator('#result').inner_text() != 'GhostOS CDP verified':
                raise RuntimeError('Result state was lost on reconnect')
            print('Verified CDP launch/DOM, existing-tab reuse from a different site, new tabs, tab activation, native UIA/URL fallback, Windows-Use SDK/local tool calls and persistent results')
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
