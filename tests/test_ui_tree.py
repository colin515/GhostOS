import os
from unittest.mock import MagicMock, patch
import pytest
from agent.ui_tree import UITree, uia_context


def test_uia_context_non_windows():
    with patch('os.name', 'posix'):
        with uia_context():
            pass


def test_ui_tree_init():
    tree = UITree()
    assert tree.controls == {}
    assert tree.window is None


def test_ui_tree_snapshot_non_windows():
    with patch('os.name', 'posix'):
        tree = UITree()
        result = tree.snapshot()
        assert result == []


def test_ui_tree_center_stale_element():
    tree = UITree()
    with pytest.raises(ValueError, match="Stale UIA element"):
        tree.center(999)


def test_ui_tree_center_valid():
    tree = UITree()
    mock_control = MagicMock()
    mock_control.Exists.return_value = True
    rect = MagicMock()
    rect.left = 100
    rect.right = 200
    rect.top = 50
    rect.bottom = 150
    mock_control.BoundingRectangle = rect
    tree.controls[1] = mock_control

    mock_window = MagicMock()
    mock_window.NativeWindowHandle = 12345
    tree.window = mock_window

    mock_auto = MagicMock()
    mock_fg = MagicMock()
    mock_fg.NativeWindowHandle = 12345
    mock_auto.GetForegroundControl.return_value = mock_fg

    with patch.dict('sys.modules', {'uiautomation': mock_auto}):
        coords = tree.center(1)
        assert coords == (150, 100)


def test_ui_tree_focus():
    tree = UITree()
    mock_window = MagicMock()
    mock_window.Exists.return_value = True
    tree.window = mock_window
    tree.focus()
    mock_window.SetActive.assert_called_once()
