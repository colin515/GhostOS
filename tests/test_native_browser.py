import json
import sys
import threading
from types import SimpleNamespace
import pytest
from agent.native_browser import NativeBrowser


@pytest.fixture
def native(monkeypatch):
    calls = []
    browser = NativeBrowser(SimpleNamespace(browser_channel='chrome'), threading.Event(), lambda text: calls.append(('type', text)))
    browser.apps = SimpleNamespace(ensure=lambda *a: None, windows=lambda app: [101], focus=lambda app: None)
    root = SimpleNamespace(ControlTypeName='PaneControl', NativeWindowHandle=101)
    editor = SimpleNamespace(ControlTypeName='EditControl', NativeWindowHandle=0, GetParentControl=lambda: root)
    state = {'url':'https://www.youtube.com/', 'tabs':1, 'editor':editor, 'foreground':101}
    def hotkey(*keys):
        calls.append(('keys', keys))
        if keys == ('ctrl', 't'):
            state['tabs'] += 1
    def press(key):
        calls.append(('press', key))
        typed = [value for kind, value in calls if kind == 'type']
        if typed:
            state['url'] = typed[-1]
    monkeypatch.setitem(sys.modules, 'pyautogui', SimpleNamespace(hotkey=hotkey, press=press))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(GetForegroundWindow=lambda: state['foreground']))
    monkeypatch.setitem(sys.modules, 'uiautomation', SimpleNamespace(GetFocusedControl=lambda: state['editor']))
    browser.chrome = lambda *a: ([(None, 'Tab', True)] * state['tabs'], state['url'])
    browser.reuse = lambda url: None
    return browser, state, calls


def test_native_url_entry_verifies_editor_and_actual_destination(native):
    browser, _, calls = native
    result = json.loads(browser.open('https://www.netflix.com/'))
    assert calls == [('keys', ('ctrl','l')), ('type','https://www.netflix.com/'), ('press','enter')]
    assert result['verified'] and result['url'] == 'https://www.netflix.com/'


def test_native_new_tab_checks_count_increase(native):
    browser, state, calls = native
    result = json.loads(browser.open(new_tab=True))
    assert state['tabs'] == 2 and result['created_tab'] and result['verified']
    assert calls == [('keys', ('ctrl','t'))]


def test_native_url_never_types_into_a_webpage_editor(native):
    browser, state, calls = native
    document = SimpleNamespace(ControlTypeName='DocumentControl', NativeWindowHandle=0)
    state['editor'] = SimpleNamespace(ControlTypeName='EditControl', NativeWindowHandle=0, GetParentControl=lambda: document)
    with pytest.raises(RuntimeError, match='webpage content'):
        browser.open('https://www.netflix.com/')
    assert not any(kind == 'type' for kind, _ in calls)


def test_native_focus_change_prevents_typing(native):
    browser, state, calls = native
    def focused():
        state['foreground'] = 202
        return state['editor']
    sys.modules['uiautomation'].GetFocusedControl = focused
    with pytest.raises(RuntimeError, match='lost focus'):
        browser.open('https://www.netflix.com/')
    assert not any(kind == 'type' for kind, _ in calls)


def test_unobservable_tab_strip_does_not_send_unverifiable_ctrl_t(native):
    browser, _, calls = native
    browser.chrome = lambda *a: ([], '')
    with pytest.raises(RuntimeError, match='no key was sent'):
        browser.open(new_tab=True)
    assert not calls


def test_native_stop_prevents_any_keyboard_input(native):
    browser, _, calls = native
    browser.stop.set()
    with pytest.raises(InterruptedError):
        browser.open('https://www.netflix.com/')
    assert not calls
