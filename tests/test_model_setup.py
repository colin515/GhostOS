import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
from agent.vision import Frame
from config import Settings
from agent import windows_use_engine as engine


def test_actual_sdk_repairs_missing_action_with_same_goal_and_one_image(monkeypatch, tmp_path):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/show':
                reply = {'capabilities':['vision']}
            else:
                received.append(data)
                content = ({'status':'CONTINUE','summary':'The volume control is visible','action':None} if len(received) == 1 else
                           {'status':'CONTINUE','summary':'Wait','plan':[], 'action':{'kind':'wait','args':{'seconds':0}}})
                reply = {'model':'local-test','done':True,'message':{'role':'assistant','content':json.dumps(content)}}
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())
        def log_message(self,*args):
            pass
    for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(engine, 'local_desktop', lambda:None)
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    brain = None
    try:
        brain = engine.WindowsUseBrain(Settings(data_dir=tmp_path, model='local-test',
            ollama_host=f'http://127.0.0.1:{server.server_port}'))
        result = brain.next('Set volume to 100', Frame(Image.new('RGB',(64,64)),(64,64)), [])
        assert result.action.kind == 'wait'
        assert len(received) == 2
        assert 'Set volume to 100' in received[1]['messages'][1]['content']
        assert sum(len(m.get('images',[])) for m in received[1]['messages']) == 1
        assert 'missing action' in received[1]['messages'][-1]['content']
        assert 'oneOf' in received[1]['format']
    finally:
        if brain:
            brain.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_setup_verifies_real_sdk_protocol_without_reading_or_controlling_desktop(monkeypatch, tmp_path):
    from agent.model_setup import verify_model
    import pytest
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/show':
                reply = {'capabilities':['vision','tools','thinking']}
            else:
                received.append(data)
                reply = {'model':'local-test','done':True,'message':{'role':'assistant','content':'',
                    'tool_calls':[{'function':{'name':'wait','arguments':{'seconds':0}}}]}}
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"models":[]}')
        def log_message(self,*args):
            pass
    for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(engine, 'local_desktop', lambda:pytest.fail('Setup must not read the desktop'))
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        report = verify_model(Settings(data_dir=tmp_path,ollama_host=f'http://127.0.0.1:{server.server_port}'),'local-test', lambda message:None)
        assert report['agent_protocol'] == 'passed'
        assert report['actions_executed'] == 0
        assert received[0]['think'] is False
        assert len(received[0]['messages'][1]['images']) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
