from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from agent.events import EventBus
from agent.safety import ApprovalBroker
from agent.web_dashboard import create_app

class FakeRuntime:
    def __init__(self):
        self.local_ip = '192.168.1.50'
        self.token = 'test-only-token'
        self.settings = SimpleNamespace(tier=2)
        self.bus = EventBus()
        self.approvals = ApprovalBroker(self.bus)
        self.running = False
        self.goals, self.stops = [], 0
    def start(self, goal):
        if self.running:
            raise RuntimeError('An agent run is already active')
        self.goals.append(goal)
        self.running = True
        return 'run-test'
    def stop(self):
        self.running = False
        self.stops += 1
    def approve(self, request_id, approved):
        return bool(self.approvals.resolve(request_id))

@pytest.fixture
def pair():
    runtime = FakeRuntime()
    client = TestClient(create_app(runtime), base_url='http://127.0.0.1', client=('127.0.0.1', 12345))
    return runtime, client


def auth():
    return {'Authorization': 'Bearer test-only-token'}


def test_pair_page_never_contains_secret(pair):
    runtime, client = pair
    page = client.get('/')
    assert page.status_code == 200
    assert runtime.token not in page.text

@pytest.mark.parametrize('method,path,body', [('get', '/api/state', None),
    ('post', '/api/goals', {'goal': 'do work'}), ('post', '/api/stop', {}),
    ('post', '/api/approvals/abc', {'approved': True})])
def test_all_control_routes_require_pairing(pair, method, path, body):
    _, client = pair
    kwargs = {} if body is None else {'json': body}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_cross_origin_request_rejected_even_with_token(pair):
    _, client = pair
    assert client.get('/api/state', headers={**auth(), 'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/state', headers={**auth(), 'Origin': 'http://127.0.0.1'}).status_code == 200
    assert client.get('/api/state', headers={**auth(), 'Host': 'evil.example'}).status_code == 400


def test_goals_serialize_and_stop_is_immediate(pair):
    runtime, client = pair
    assert client.post('/api/goals', headers=auth(), json={'goal': 'first'}).status_code == 202
    assert client.post('/api/goals', headers=auth(), json={'goal': 'second'}).status_code == 409
    assert runtime.goals == ['first']
    assert client.post('/api/stop', headers=auth(), json={}).status_code == 200
    assert runtime.stops == 1
    assert not runtime.running


def test_approval_cannot_be_replayed(pair):
    runtime, client = pair
    runtime.approvals.create('once', {'kind': 'focus'})
    assert client.post('/api/approvals/once', headers=auth(), json={'approved': True}).status_code == 200
    assert client.post('/api/approvals/once', headers=auth(), json={'approved': True}).status_code == 409
    assert client.post('/api/approvals/other', headers=auth(), json={'approved': 'yes'}).status_code == 422


def test_ws_requires_auth_before_frame(pair):
    runtime, client = pair
    runtime.bus.publish('FRAME', image='not-private-until-authorized')
    with client.websocket_connect('ws://127.0.0.1/ws') as ws:
        ws.send_json({'token': runtime.token})
        data = ws.receive_json()
        assert data['frame']['image'] == 'not-private-until-authorized'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('ws://127.0.0.1/ws') as ws:
            ws.send_json({'token': 'wrong'})
            ws.receive_json()


def test_invalid_ws_payload_is_rejected(pair):
    _, client = pair
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('ws://127.0.0.1/ws') as ws:
            ws.send_json([])
            ws.receive_json()
