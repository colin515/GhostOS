"""Animated, non-activating ghost replaces the old bottom-right Stop panel.

Left-click the ghost to stop. All original emergency hotkeys remain available.
"""
from __future__ import annotations
import math
import sys
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QApplication
from ui.widgets import draw_ghost, AudioVisualizer


class ControlPanel(QWidget):
    def __init__(self, stop, browser_help):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet('ControlPanel { background: transparent; border: none; }')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('GhostOS working ghost — click to stop')
        self.setAccessibleName('GhostOS animated task indicator; click to stop')
        self.setFixedSize(112, 138)
        self.setToolTip('GhostOS is running. Click the ghost to stop (Ctrl+Alt+Esc also works).')
        self._stop = stop
        self.mode = 'working'
        self.phase = 0.0
        # Retain the public properties the desktop uses for voice/browser notices.
        self.label = QLabel('GhostOS is working', self)
        self.label.hide()
        self.wave = AudioVisualizer(self)
        self.wave.hide()
        self.help_button = QPushButton('Browser help', self)
        self.help_button.setGeometry(2, 109, 108, 25)
        self.help_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.help_button.clicked.connect(browser_help)
        self.help_button.hide()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(65)

    def set_activity(self, kind):
        modes = {'INFERENCE': 'thinking', 'PLAN': 'thinking', 'RECOVERY': 'recovering',
                 'ERROR': 'recovering', 'ACTION': 'working', 'EXECUTING': 'working',
                 'MOUSE': 'moving', 'TARGET': 'moving', 'APPROVAL': 'waiting',
                 'VOICE_APPROVAL': 'listening', 'AUDIO_LEVEL': 'listening'}
        self.mode = modes.get(kind, self.mode)
        self.update()

    def tick(self):
        if self.isVisible():
            self.phase += 0.19
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = {'thinking': '#a7a5ff', 'working': '#8cddf4',
                   'moving': '#85ecb5', 'listening': '#dda4ff',
                   'recovering': '#ffb58d', 'waiting': '#ffe09b'}
        color = QColor(palette.get(self.mode, '#a7a5ff'))
        pulse = 1 + 0.10 * math.sin(self.phase)
        halo = QColor(color)
        halo.setAlpha(36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(19 - 7*pulse, 10 - 6*pulse, 75 + 14*pulse, 75 + 12*pulse))
        bounce = 4 * math.sin(self.phase * (1.4 if self.mode == 'moving' else 0.7))
        blink = int(self.phase * 2) % 67 in (0, 1, 2)
        draw_ghost(p, QRectF(19, 9 + bounce, 74, 74), blink=blink)
        p.setPen(color)
        statuses = {'thinking':'THINKING', 'working':'WORKING', 'moving':'MOVING',
                    'listening':'LISTENING', 'recovering':'RETRYING', 'waiting':'APPROVE'}
        p.drawText(self.rect().adjusted(0, 92, 0, -26), Qt.AlignmentFlag.AlignCenter,
                   statuses.get(self.mode, 'WORKING'))
        p.setPen(QColor('#dddde7'))
        p.drawText(self.rect().adjusted(0, 112, 0, -6), Qt.AlignmentFlag.AlignCenter,
                   'Click to stop' if not self.help_button.isVisible() else '')
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 106:
            self._stop()
            event.accept()
        else:
            super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        from agent.window_focus import mark_ui
        mark_ui(int(self.winId()))
        if sys.platform == 'win32':
            import ctypes
            try:
                ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
            except (OSError, ValueError):
                pass
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 16,
                      area.bottom() - self.height() - 16)

    def closeEvent(self, event):
        from agent.window_focus import unmark_ui
        unmark_ui(int(self.winId()))
        super().closeEvent(event)
