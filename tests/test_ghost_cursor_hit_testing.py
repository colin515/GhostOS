"""Ghost pointer overlays must not block real Windows mouse actions."""
import sys
from types import SimpleNamespace
import pytest
from agent.mouse import WinMouse
import agent.window_focus


def test_clickthrough_ghost_overlay_does_not_block_mouse(monkeypatch):
    style = [0x00000020]  # WS_EX_TRANSPARENT
    win32gui = SimpleNamespace(WindowFromPoint=lambda pt: 101,
                               GetAncestor=lambda hwnd, mode: hwnd,
                               GetWindowLong=lambda hwnd, index: style[0])
    monkeypatch.setitem(sys.modules, 'win32gui', win32gui)
    monkeypatch.setattr(agent.window_focus, 'is_agent_window', lambda hwnd: True)
    driver = WinMouse.__new__(WinMouse)
    driver.validate_target(60, 75)
    style[0] = 0
    with pytest.raises(RuntimeError, match='GhostOS controls'):
        driver.validate_target(60, 75)
