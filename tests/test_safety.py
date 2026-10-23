import queue
import threading
import time
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from agent.models import Action, Decision
from agent.safety import requires_approval, WorkerSafety, ApprovalBroker
from agent.events import EventBus

@pytest.mark.parametrize('kind,args', [
    ('shell', {'script': 'Remove-Item example.txt'}),
    ('browser_fill', {'selector': 'input', 'value': 'hello'}),
    ('browser_click', {'selector': 'button'}),
    ('hotkey', {'keys': ['enter']}),
    ('hotkey', {'keys': ['delete']}),
    ('type_text', {'text': 'hello'}),
    ('click', {'x': 3, 'y': 4}),
    ('game_key', {'key': 'w'}),
])
def test_consequential_actions_require_balanced_approval(kind, args):
    action = Action(kind=kind, args=args)
    assert requires_approval(action, 1)
    assert requires_approval(action, 2)
    assert not requires_approval(action, 3)

@pytest.mark.parametrize('kind,args', [
    ('hotkey', {'keys': ['ctrl', 'l']}), ('browser_navigate', {'url': 'https://example.com'}),
    ('wait', {'seconds': 0.2}), ('focus', {}), ('open_app', {'name': 'notepad'}),
])
def test_navigation_tiers(kind, args):
    action = Action(kind=kind, args=args)
    assert requires_approval(action, 1)
    assert not requires_approval(action, 2)

@pytest.mark.parametrize('payload', [
    {'kind': 'eval', 'args': {'code': '1+1'}},
    {'kind': 'shell', 'args': {'script': 'whoami', 'risk': 'low'}},
    {'kind': 'wait', 'args': {'seconds': 20}},
    {'kind': 'game_key', 'args': {'key': 'w', 'duration': 5}},
    {'kind': 'template_click', 'args': {'name': '../secret.png'}},
    {'kind': 'browser_navigate', 'args': {'url': 'file:///C:/secret'}},
    {'kind': 'browser_navigate', 'args': {'url': 'javascript:alert(1)'}},
    {'kind': 'click', 'args': {'x': -1, 'y': 2}},
])
def test_untrusted_actions_fail_validation(payload):
    with pytest.raises(ValidationError):
        Action.model_validate(payload)


def make_safety(tier=1, timeout=1):
    stop, events, replies = threading.Event(), queue.Queue(), queue.Queue()
    return WorkerSafety(SimpleNamespace(tier=tier, approval_timeout=timeout), stop, events, replies)


def test_decline_does_not_authorize():
    safety = make_safety()
    result = []
    def authorize():
        try:
            safety.authorize(Action(kind='focus'))
        except PermissionError:
            result.append('denied')
    thread = threading.Thread(target=authorize)
    thread.start()
    request = safety.events.get(timeout=1)
    safety.answers.put({'id': request['request_id'], 'approved': False})
    thread.join(timeout=2)
    assert result == ['denied']


def test_stop_prevents_even_tier_three_action():
    safety = make_safety(tier=3)
    safety.stop.set()
    with pytest.raises(InterruptedError):
        safety.authorize(Action(kind='shell', args={'script': 'whoami'}))


def test_timeout_is_fail_closed():
    safety = make_safety(timeout=0)
    with pytest.raises(PermissionError, match='timed out'):
        safety.authorize(Action(kind='focus'))


def test_approval_is_one_time():
    broker = ApprovalBroker(EventBus())
    broker.create('random-id', {'kind': 'focus'})
    assert len(broker.pending()) == 1
    assert broker.resolve('random-id')
    assert broker.resolve('random-id') is None


def test_terminal_decisions_cannot_sneak_in_action():
    with pytest.raises(ValidationError):
        Decision(status='GOAL_SATISFIED', summary='done', action=Action(kind='focus'))
    with pytest.raises(ValidationError):
        Decision(status='CONTINUE', summary='continue')


def test_executing_event_is_emitted_only_after_authorization(tmp_path):
    from agent.controller import Controller
    safety = make_safety(tier=3)
    controller = Controller(SimpleNamespace(), safety, None, None)
    controller.execute(Action(kind='wait', args={'seconds':0.0}))
    assert safety.events.get_nowait()['kind'] == 'EXECUTING'
    safety.stop.set()
    with pytest.raises(InterruptedError):
        controller.execute(Action(kind='wait', args={'seconds':0.0}))
    assert safety.events.empty()
