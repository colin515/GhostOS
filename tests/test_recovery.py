from types import SimpleNamespace
import threading
import pytest
from agent.recovery import Recovery
from agent.windows_apps import requested_app, canonical_app, WindowsApps
from agent.models import Action
from agent.safety import requires_approval


def test_only_explicit_user_app_names_are_used():
    assert requested_app('Open galaxus.ch in Google Chrome') == 'chrome'
    assert requested_app('https://example.com/chrome') is None
    assert requested_app('Search in Firefox') == 'firefox'
    with pytest.raises(ValueError):
        canonical_app('chrome.exe & whoami')


def test_chrome_ladder_exhausts_distinct_fallbacks_before_failure():
    recovery = Recovery('Use Chrome to search')
    actions, events = [], []
    controller = SimpleNamespace(execute=lambda action: actions.append(action) or 'done')
    while not recovery.exhausted:
        recovery.attempt(controller, lambda kind, **kw: events.append((kind, kw)), 'blocked')
    assert len(recovery.history) == 4
    assert [a.args['strategy'] for a in actions if a.kind == 'ensure_app'] == ['focus','launch']
    assert not any(a.kind == 'shell' for a in actions)
    count = len(actions)
    assert not recovery.attempt(controller, lambda *a, **kw: None, 'blocked')
    assert len(actions) == count


def test_recovery_search_requires_confirmation_in_balanced_mode():
    for strategy in ('focus','launch','search'):
        action = Action(kind='ensure_app', args={'name':'chrome','strategy':strategy})
        assert requires_approval(action, 1)
        assert requires_approval(action, 2) == (strategy == 'search')
        assert not requires_approval(action, 3)


def test_game_recovery_does_not_switch_to_unrelated_apps():
    recovery = Recovery('Play in Chrome', game_mode=True)
    assert all(action.kind == 'wait' for step in recovery.steps for action in step.actions)


def test_running_app_is_not_launched_again_when_windows_denies_focus(monkeypatch):
    app = WindowsApps(threading.Event())
    monkeypatch.setattr(app, '_check', lambda: None)
    monkeypatch.setattr(app, 'focus', lambda name: (_ for _ in ()).throw(RuntimeError('focus denied')))
    monkeypatch.setattr(app, 'windows', lambda name: [123])
    called = []
    monkeypatch.setattr('subprocess.Popen', lambda *a, **kw: called.append(a))
    with pytest.raises(RuntimeError, match='running'):
        app.ensure('chrome', 'launch')
    assert not called


def test_native_focus_checks_foreground_and_maximizes(monkeypatch):
    app = WindowsApps(threading.Event())
    monkeypatch.setattr(app, '_check', lambda: None)
    monkeypatch.setattr(app, 'windows', lambda name: [123])
    calls = []
    import agent.window_focus
    monkeypatch.setattr(agent.window_focus, 'focus_window', lambda hwnd, stop, maximize: calls.append((hwnd, maximize)))
    assert 'focused' in app.focus('chrome')
    assert calls == [(123, True)]
    monkeypatch.setattr(agent.window_focus, 'focus_window', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('denied')))
    with pytest.raises(RuntimeError, match='focus'):
        app.focus('chrome')


def test_installed_app_launch_uses_exact_path_without_shell(monkeypatch, tmp_path):
    app = WindowsApps(threading.Event())
    monkeypatch.setattr(app, '_check', lambda: None)
    monkeypatch.setattr(app, 'focus', lambda name: (_ for _ in ()).throw(LookupError('closed')))
    monkeypatch.setattr(app, 'windows', lambda name: [])
    executable = tmp_path / 'Program Files' / 'chrome.exe'
    monkeypatch.setattr(app, 'installed_path', lambda name: executable)
    monkeypatch.setattr(app, '_wait_for_window', lambda name: 'Chrome focused')
    calls = []
    monkeypatch.setattr('subprocess.Popen', lambda args, **kw: calls.append((args, kw)))
    assert app.ensure('chrome', 'launch') == 'Chrome focused'
    assert calls == [([str(executable)], {'shell':False})]


def test_microsoft_store_launch_uses_registered_uri_not_screen_search(monkeypatch):
    app = WindowsApps(threading.Event())
    monkeypatch.setattr(app, '_check', lambda: None)
    monkeypatch.setattr(app, 'focus', lambda name: (_ for _ in ()).throw(LookupError('not visible')))
    monkeypatch.setattr(app, 'windows', lambda name: [])
    monkeypatch.setattr(app, 'installed_path', lambda name: (_ for _ in ()).throw(AssertionError('Store is a packaged app')))
    monkeypatch.setattr(app, '_wait_for_window', lambda name, timeout: 'Store focus verified')
    calls = []
    import agent.windows_apps
    monkeypatch.setattr(agent.windows_apps.os, 'startfile', lambda uri: calls.append(uri), raising=False)
    assert app.ensure('Microsoft Store', 'launch') == 'Store focus verified'
    assert calls == ['ms-windows-store://home']
    assert canonical_app('Windows Store') == 'store'


def test_registered_apps_use_exact_installed_names_and_native_shell_activation(monkeypatch):
    import sys
    app = WindowsApps(threading.Event())
    monkeypatch.setattr(app, '_check', lambda: None)
    monkeypatch.setattr(app, 'registered_apps', lambda: {'sample editor':'Vendor.Sample_123!App'})
    visible = []
    gui = SimpleNamespace(EnumWindows=lambda callback, _: [callback(hwnd,None) for hwnd in visible],
        GetWindowText=lambda hwnd:'Document - Sample Editor', IsWindowVisible=lambda hwnd:True)
    monkeypatch.setitem(sys.modules, 'win32gui', gui)
    calls = []
    import agent.windows_apps
    import agent.window_focus
    monkeypatch.setattr(agent.windows_apps.os, 'startfile', lambda target:(calls.append(target), visible.append(42)), raising=False)
    monkeypatch.setattr(agent.window_focus, 'focus_window', lambda *a, **kw:42)
    monkeypatch.setattr(agent.window_focus, 'is_agent_window', lambda hwnd:False)
    assert 'verified' in app.ensure('Sample Editor', 'launch')
    assert calls == ['shell:AppsFolder\\Vendor.Sample_123!App']
    with pytest.raises(FileNotFoundError, match='exact installed'):
        app.ensure('sample editor; Remove-Item C:/', 'launch')
    assert len(calls) == 1
