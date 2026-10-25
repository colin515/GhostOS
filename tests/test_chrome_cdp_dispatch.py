"""Browser dispatch should use CDP/Playwright for precise Chrome selectors."""
import queue
from types import SimpleNamespace
from agent.controller import Controller
from agent.models import Action


def controller():
    c=Controller.__new__(Controller)
    c.original_goal=''
    c.browser_explicit=True
    c.settings=SimpleNamespace(cdp_url='',browser_channel='chrome')
    c.safety=SimpleNamespace(events=queue.Queue())
    c.web=SimpleNamespace(page=None,native_fallback=False,execute=lambda action:'CDP-OK')
    def reject_native():
        raise AssertionError('Auto Chrome path unexpectedly switched to native')
    c.native_browser=reject_native
    return c


def test_auto_browser_open_prefers_cdp_over_native():
    c=controller()
    assert c.browser_action(Action(kind='browser_open',
        args={'url':'https://example.com/'})) == 'CDP-OK'
    assert not c.web.native_fallback


def test_auto_new_tab_prefers_cdp_over_native():
    c=controller()
    assert c.browser_action(Action(kind='browser_new_tab',args={})) == 'CDP-OK'


def test_backend_native_explicitly_uses_personal_browser():
    c=controller()
    c.native_browser=lambda:SimpleNamespace(open=lambda *a,**kw:'NATIVE-OK')
    assert c.browser_action(Action(kind='browser_open',args={
        'url':'https://example.com/','backend':'native'})) == 'NATIVE-OK'
