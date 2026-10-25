"""GhostOS-only animated pointer *overlay* while the agent moves Windows' pointer.

Windows has one native pointer: the overlay cannot independently click through
ordinary applications. It is visual only and never intercepts user input.
"""
from __future__ import annotations
import math
import sys
import time
from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QPainter, QColor, QCursor
from PyQt6.QtWidgets import QWidget
from ui.widgets import draw_ghost


class GhostCursor(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet('GhostCursor { background: transparent; border: none; }')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(46, 48)
        self.setAccessibleName('GhostOS cursor animation (non-interactive)')
        self.phase = 0
        self.expires = 0.0
        self.pressed = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        self.hide()

    def note_mouse(self, event):
        phase = event.get('phase', '')
        self.pressed = phase in ('start', 'moving', 'arrived')
        self.expires = time.monotonic() + 1.3
        if not self.isVisible():
            self.show()

    def tick(self):
        if time.monotonic() >= self.expires:
            if self.isVisible():
                self.hide()
            return
        pointer = QCursor.pos()  # Qt logical coordinates, not raw Windows physical pixels.
        self.move(pointer.x() - 8, pointer.y() - 8)
        self.phase += 0.19
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QColor('#8de6fa')
        glow.setAlpha(65 if self.pressed else 35)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(1, 1, 40, 40))
        bounce = 1.6 * math.sin(self.phase * 1.2)
        blink = int(self.phase * 2) % 55 in (0, 1, 2)
        draw_ghost(painter, QRectF(3, 3 + bounce, 34, 36), blink=blink)
        painter.end()

    def showEvent(self, event):
        super().showEvent(event)
        from agent.window_focus import mark_ui
        mark_ui(int(self.winId()))
        if sys.platform == 'win32':
            import ctypes
            try:
                # Do not feed our animated pointer back to the vision model.
                ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
            except (OSError, ValueError):
                pass

    def closeEvent(self, event):
        from agent.window_focus import unmark_ui
        unmark_ui(int(self.winId()))
        super().closeEvent(event)
