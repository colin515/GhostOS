from types import SimpleNamespace
import threading
import pytest
from agent.window_focus import FocusGuard


def test_focus_guard_restores_target_before_input_and_never_targets_agent(monkeypatch):
    import agent.window_focus as focus
    import sys
    foreground = [50]
    monkeypatch.setattr(focus, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(focus, 'is_agent_window', lambda hwnd: hwnd == 99)
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(GetForegroundWindow=lambda: foreground[0]))
    calls = []
    monkeypatch.setattr(focus, 'focus_window', lambda hwnd, stop: calls.append(hwnd))
    guard = FocusGuard(threading.Event())
    guard.observe()
    foreground[0] = 99
    guard.ensure_external()
    assert calls == [50]
    assert guard.last == 50


@pytest.mark.parametrize('status', ['GOAL_SATISFIED', 'STOPPED', 'ERROR'])
def test_completion_reopens_chat_only_after_worker_cleanup(tmp_path, monkeypatch, status):
    from test_desktop import fake_runtime
    from ui.app import MainWindow
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    runtime = fake_runtime(tmp_path)
    window = MainWindow(runtime)
    activations = []
    monkeypatch.setattr(window, 'activateWindow', lambda: activations.append(True))
    window.show()
    runtime.running = True
    runtime.bus.publish('STARTED', goal='work')
    window.poll()
    assert not window.isVisible()
    assert not activations
    runtime.running = False
    runtime.bus.publish('FINISHED', status=status)
    window.poll()
    assert window.isVisible()
    assert not window.panel.isVisible()
    assert activations == [True]
    assert window.send.isEnabled()
    assert window.voice_button.isEnabled()
    assert 'Ready for your next command' in window.voice_status.text()
    window.poll()
    assert activations == [True]  # No repeated focus stealing on later timer ticks.
    window.submit_goal('Open Microsoft Store')
    assert runtime.goals == ['Open Microsoft Store']
    assert not window.isVisible()
    window.close()
    app.processEvents()


def test_delayed_completion_never_interrupts_an_active_run_or_shutdown(tmp_path, monkeypatch):
    from test_desktop import fake_runtime
    from ui.app import MainWindow
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    runtime = fake_runtime(tmp_path)
    window = MainWindow(runtime)
    monkeypatch.setattr(window, 'activateWindow', lambda: pytest.fail('Unexpected focus transfer'))
    runtime.running = True
    runtime.bus.publish('FINISHED', status='GOAL_SATISFIED')
    runtime.bus.publish('STARTED', goal='next task')
    window.poll()
    assert not window.isVisible()
    # A delayed old event must not reactivate the UI over the new worker either.
    runtime.bus.publish('FINISHED', status='GOAL_SATISFIED')
    window.poll()
    assert not window.isVisible()
    runtime.running = False
    window.closing_requested = True
    runtime.bus.publish('FINISHED', status='STOPPED')
    window.poll()
    assert not window.isVisible()
    window.close()
    app.processEvents()


def test_native_windows_properties_tag_and_untag_without_pywin32_wrappers():
    import os
    import pytest
    if os.name != 'nt':
        pytest.skip('Native Windows property API')
    import win32gui
    from agent.window_focus import mark_ui, unmark_ui, property_api, PROPERTY
    hwnd = win32gui.CreateWindowEx(0, 'STATIC', 'GhostOS property test', 0, 0, 0, 10, 10, 0, 0, 0, None)
    try:
        mark_ui(hwnd)
        assert property_api().GetPropW(hwnd, PROPERTY) == 1
        unmark_ui(hwnd)
        assert not property_api().GetPropW(hwnd, PROPERTY)
    finally:
        win32gui.DestroyWindow(hwnd)
