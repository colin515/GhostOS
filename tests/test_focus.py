from types import SimpleNamespace
import threading
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


def test_completion_does_not_restore_or_focus_main_window(tmp_path):
    from test_desktop import fake_runtime
    from ui.app import MainWindow
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    runtime = fake_runtime(tmp_path)
    window = MainWindow(runtime)
    window.show()
    runtime.bus.publish('STARTED', goal='work')
    window.poll()
    assert not window.isVisible()
    runtime.bus.publish('FINISHED', status='GOAL_SATISFIED')
    window.poll()
    assert not window.isVisible()
    assert not window.panel.isVisible()
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
