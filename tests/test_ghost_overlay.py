"""Qt offscreen checks for the animated ghost and the visual-only pointer."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PyQt6')
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtWidgets import QApplication


def test_ghost_panel_animates_and_click_stops():
    from ui.control_panel import ControlPanel
    app = QApplication.instance() or QApplication([])
    stops = []
    panel = ControlPanel(lambda: stops.append(True), lambda: None)
    panel.show()
    app.processEvents()
    panel.set_activity('INFERENCE')
    assert panel.mode == 'thinking'
    panel.set_activity('RECOVERY')
    assert panel.mode == 'recovering'
    assert panel.help_button.isHidden()
    event = type('FakeMouse', (), {
        'button': lambda self: Qt.MouseButton.LeftButton,
        'position': lambda self: QPointF(45, 40),
        'accept': lambda self: None,
    })()
    panel.mousePressEvent(event)
    assert stops == [True]
    panel.close()


def test_cursor_is_noninteractive_and_expires():
    from ui.ghost_cursor import GhostCursor
    app = QApplication.instance() or QApplication([])
    cursor = GhostCursor()
    cursor.note_mouse({'phase': 'moving'})
    app.processEvents()
    assert cursor.isVisible()
    assert cursor.windowFlags() & Qt.WindowType.WindowTransparentForInput
    cursor.expires = 0
    cursor.tick()
    assert cursor.isHidden()
    cursor.close()
