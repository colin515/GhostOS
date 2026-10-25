"""Animated, non-activating ghost replaces the old bottom-right Stop panel.

Left-click the ghost to stop. All original emergency hotkeys remain available.
"""
from __future__ import annotations
import math
import sys
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QRadialGradient
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
        self.setFixedSize(132, 160)
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
        self.help_button.setGeometry(7, 129, 118, 26)
        self.help_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.help_button.clicked.connect(browser_help)
        self.help_button.hide()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def set_activity(self, kind):
        modes = {'INFERENCE': 'thinking', 'PLAN': 'thinking', 'RECOVERY': 'recovering',
                 'ERROR': 'recovering', 'ACTION': 'working', 'EXECUTING': 'working',
                 'MOUSE': 'moving', 'TARGET': 'moving', 'APPROVAL': 'waiting',
                 'VOICE_APPROVAL': 'listening', 'AUDIO_LEVEL': 'listening'}
        self.mode = modes.get(kind, self.mode)
        self.update()

    def tick(self):
        if self.isVisible():
            self.phase += 0.13
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shades = {'thinking': '#a89bff', 'working': '#73d3f5',
                  'moving': '#75f4c2', 'listening': '#dca7ff',
                  'recovering': '#ffa778', 'waiting': '#ffda86'}
        colour = QColor(shades.get(self.mode, '#a89bff'))
        t = self.phase
        cx, cy = 66.0, 55.0
        pulse = 1.0 + 0.045*math.sin(t*2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        # Triple-layer soft glow, colour-coded to the task state.
        for radius, alpha in ((56,9),(45,17),(34,30)):
            glow = QRadialGradient(cx,cy,radius)
            inside=QColor(colour)
            inside.setAlpha(alpha*3)
            outside=QColor(colour)
            outside.setAlpha(0)
            glow.setColorAt(0,inside)
            glow.setColorAt(1,outside)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(cx-radius*pulse,cy-radius*pulse,
                                       radius*2*pulse,radius*2*pulse))
        # Animated orbiting motes. Thinking rotates slowly; moving leaves a trail.
        speed = {'thinking':0.5,'moving':2.3,'recovering':-0.7,
                 'listening':1.4,'waiting':0.35}.get(self.mode,1.0)
        for index in range(9):
            angle = index*math.tau/9 + t*speed
            radius = 49 + 3*math.sin(2*t + index*1.9)
            x = cx+radius*math.cos(angle)
            y = cy+radius*.75*math.sin(angle)
            mote=QColor(colour)
            mote.setAlpha(60+int(120*abs(math.sin(t+index*.7))))
            painter.setBrush(mote)
            painter.drawEllipse(QRectF(x-1.5,y-1.5,3,3))
        ring=QColor(colour)
        ring.setAlpha(105)
        painter.setPen(QPen(ring,1.7))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        opening = int((t*90)%360*16)
        painter.drawArc(QRectF(20,10,92,92),opening,
                        (250 if self.mode=='thinking' else 95)*16)
        painter.setPen(Qt.PenStyle.NoPen)
        bounce = (6*math.sin(t*2.2) if self.mode=='moving'
                  else 3.2*math.sin(t))
        lean = 8*math.sin(t*1.35) if self.mode in ('thinking','recovering') else 3*math.sin(t)
        painter.save()
        painter.translate(cx,cy+bounce)
        painter.rotate(lean)
        blink = math.sin(t*0.32)**24 > 0.7
        expression = {'thinking':'thinking','working':'excited',
                      'moving':'moving','listening':'excited',
                      'waiting':'waiting','recovering':'recovering'}.get(self.mode,'neutral')
        draw_ghost(painter,QRectF(-39,-39,78,78),blink=blink,expression=expression)
        painter.restore()
        painter.setPen(colour)
        statuses={'thinking':'✦ THINKING','working':'✦ WORKING','moving':'✦ MOVING',
                  'listening':'✦ LISTENING','recovering':'✦ RECOVERING','waiting':'✦ APPROVAL'}
        painter.drawText(QRectF(0,107,self.width(),20),Qt.AlignmentFlag.AlignCenter,
                         statuses.get(self.mode,'✦ WORKING'))
        if not self.help_button.isVisible():
            painter.setPen(QColor('#a5a9c3'))
            painter.drawText(QRectF(0,132,self.width(),18),Qt.AlignmentFlag.AlignCenter,
                             'Click ghost to stop')
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 125:
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
