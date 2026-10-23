from types import SimpleNamespace
import threading
import sys
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
    assert len(recovery.history) == 6
    assert [a.args['strategy'] for a in actions if a.kind == 'ensure_app'] == ['focus','launch','search']
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
    gui = SimpleNamespace(IsIconic=lambda hwnd: True,
                          ShowWindow=lambda hwnd, mode: calls.append((hwnd, mode)),
                          SetForegroundWindow=lambda hwnd: None, GetForegroundWindow=lambda: 123)
    monkeypatch.setitem(sys.modules, 'win32gui', gui)
    monkeypatch.setitem(sys.modules, 'win32con', SimpleNamespace(SW_RESTORE=9, SW_SHOW=5, SW_MAXIMIZE=3))
    assert 'focused' in app.focus('chrome')
    assert calls == [(123,9), (123,3)]
    gui.GetForegroundWindow = lambda: 999
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
