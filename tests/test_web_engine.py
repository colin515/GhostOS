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


class FakePage:
    def __init__(self, url, title):
        self.url, self.label = url, title
        self.visits, self.activations = [], 0
    def title(self):
        return self.label
    def is_closed(self):
        return False
    def goto(self, url, **kwargs):
        self.visits.append(url)
        self.url = url
    def bring_to_front(self):
        self.activations += 1
    def locator(self, selector):
        if selector == 'body':
            return SimpleNamespace(inner_text=lambda **kw: 'Page body')
        return SimpleNamespace(evaluate_all=lambda script: [])


def fake_web():
    youtube = FakePage('https://www.youtube.com/watch?v=1', 'YouTube')
    netflix = FakePage('https://www.netflix.com/browse', 'Netflix')
    web = WebEngine(Settings())
    web.page = youtube
    web.context = SimpleNamespace(pages=[youtube, netflix])
    def new_page():
        page = FakePage('about:blank', '')
        web.context.pages.append(page)
        return page
    web.context.new_page = new_page
    web.start = lambda: None
    return web, youtube, netflix


def test_netflix_existing_tab_is_activated_from_youtube_without_reload():
    import json
    web, youtube, netflix = fake_web()
    result = json.loads(web.execute(Action(kind='browser_open', args={'url':'https://www.netflix.com/'})))
    assert web.page is netflix
    assert netflix.activations == 1 and not netflix.visits
    assert not youtube.visits
    assert result['verified'] and result['reused_tab']
    assert len(result['tabs']) == 2


def test_new_tab_really_creates_an_additional_page():
    import json
    web, youtube, _ = fake_web()
    result = json.loads(web.execute(Action(kind='browser_new_tab')))
    assert len(web.context.pages) == 3 and web.page is not youtube
    assert result['created_tab'] and result['verified']


def test_site_not_present_is_navigated_to_even_when_youtube_visible():
    import json
    web, youtube, _ = fake_web()
    result = json.loads(web.execute(Action(kind='browser_open', args={'url':'https://example.com/homework'})))
    assert youtube.visits == ['https://example.com/homework']
    assert result['verified'] and not result['reused_tab']


def test_tab_inventory_and_explicit_selection():
    import json
    web, youtube, netflix = fake_web()
    result = json.loads(web.execute(Action(kind='browser_tabs')))
    assert result['tabs'][1]['title'] == 'Netflix'
    web.execute(Action(kind='browser_switch_tab', args={'tab_id':1}))
    assert web.page is netflix and netflix.activations == 1
    import pytest
    with pytest.raises(ValueError, match='Stale tab'):
        web.execute(Action(kind='browser_switch_tab', args={'tab_id':100}))


def test_native_profile_reuse_does_not_launch_a_different_cdp_profile(monkeypatch):
    import json
    controller = Controller.__new__(Controller)
    controller.settings = Settings()
    controller.web = SimpleNamespace(page=None, native_fallback=False,
        execute=lambda a: (_ for _ in ()).throw(AssertionError('Must keep the existing personal tab')))
    controller.native_browser = lambda: SimpleNamespace(open=lambda *a, **kw: json.dumps({
        'verified':True, 'url':'https://www.netflix.com/browse', 'reused_tab':True}))
    result = json.loads(controller.browser_action(Action(kind='browser_open', args={'url':'https://www.netflix.com/'})))
    assert controller.web.native_fallback and result['reused_tab']


def test_snapshot_json_is_not_truncated_mid_object():
    import json
    web, page, _ = fake_web()
    web.context.pages.extend(FakePage('https://example.com/' + 'x' * 400, 'title' * 40) for _ in range(30))
    result = web.snapshot(verified=True)
    assert len(result) > 7000
    assert json.loads(result)['verified']



def test_reconnect_observes_visible_tab_not_cdp_list_order():
    youtube, netflix = FakePage('https://youtube.com/','YouTube'), FakePage('https://netflix.com/','Netflix')
    youtube.evaluate = lambda script:'hidden'
    netflix.evaluate = lambda script:'visible'
    assert WebEngine.select_active_page([youtube,netflix]) is netflix



def test_multistep_youtube_must_start_with_cdp_not_reuse_personal_tab():
    controller=Controller.__new__(Controller)
    controller.settings=Settings()
    controller.original_goal='Open YouTube, search for lo-fi music and click the first video'
    invoked=[]
    controller.web=SimpleNamespace(page=None,native_fallback=False,
        execute=lambda action:(invoked.append(action.kind) or '{"verified":true,"transport":"cdp"}'))
    controller.native_browser=lambda:(_ for _ in ()).throw(
        AssertionError('Multistep workflows may not silently switch to non-CDP personal tabs'))
    assert 'cdp' in controller.browser_action(Action(kind='browser_open',args={
        'url':'https://www.youtube.com/','backend':'auto'}))
    assert invoked==['browser_open']
    assert not controller.web.native_fallback
