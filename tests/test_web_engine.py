from types import SimpleNamespace
import queue
import threading
from agent.web_engine import WebEngine
from agent.models import Action
from agent.controller import Controller
from config import Settings


def test_disconnect_preserves_browser_and_result_tabs():
    web = WebEngine(Settings())
    calls = []
    web.context = SimpleNamespace(close=lambda: calls.append('context closed'))
    web.browser = SimpleNamespace(close=lambda: calls.append('browser closed'))
    web.playwright = SimpleNamespace(stop=lambda: calls.append('disconnected'))
    web.close()
    assert calls == ['disconnected']
    assert web.page is None


def test_cdp_failure_never_replays_uncertain_form_action():
    controller = Controller.__new__(Controller)
    events, calls = queue.Queue(), []
    controller.settings = Settings()
    controller.safety = SimpleNamespace(authorize=lambda action: None, check=lambda: None, events=events, stop=threading.Event())
    def fail(action):
        calls.append(action.kind)
        raise TimeoutError('page changed during click')
    controller.web = SimpleNamespace(execute=fail, close=lambda: None, native_fallback=False)
    result = controller.execute(Action(kind='browser_click', args={'selector':'#submit'}))
    assert calls == ['browser_click']
    assert controller.web.native_fallback
    assert 'outcome uncertain' in result
    assert 'Do not replay' in result
    assert [events.get()['kind'] for _ in range(events.qsize())] == ['EXECUTING', 'BROWSER_FALLBACK']
