"""Small vector widgets: a crisp GhostOS mark and a microphone-driven waveform."""
import math
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QIcon, QPixmap
from PyQt6.QtWidgets import QWidget


def draw_ghost(painter, rect):
    painter.save()
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 64, rect.height() / 64)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(8, 0, 56, 64)
    gradient.setColorAt(0, QColor('#ffffff'))
    gradient.setColorAt(1, QColor('#b7b5ff'))
    shape = QPainterPath()
    shape.moveTo(10, 52)
    shape.lineTo(10, 30)
    shape.cubicTo(10, 1, 54, 1, 54, 30)
    shape.lineTo(54, 52)
    shape.quadTo(54, 57, 49, 54)
    shape.lineTo(43, 50)
    shape.lineTo(34, 56)
    shape.quadTo(32, 58, 30, 56)
    shape.lineTo(21, 50)
    shape.lineTo(15, 54)
    shape.quadTo(10, 57, 10, 52)
    painter.fillPath(shape, gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#252334'))
    painter.drawRoundedRect(QRectF(22, 27, 6, 10), 3, 3)
    painter.drawRoundedRect(QRectF(36, 27, 6, 10), 3, 3)
    painter.restore()


def ghost_icon():
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_ghost(painter, QRectF(0, 0, 128, 128))
    painter.end()
    return QIcon(pixmap)


class GhostLogo(QWidget):
    def __init__(self, size=48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAccessibleName('GhostOS logo')
    def paintEvent(self, event):
        painter = QPainter(self)
        draw_ghost(painter, QRectF(self.rect()))


class AudioVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 36)
        self.setMaximumWidth(260)
        self.target = self.level = self.phase = 0.0
        self.listening = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setAccessibleName('Microphone activity')
    def set_listening(self, active):
        self.listening = bool(active)
        if active:
            self.timer.start(33)
        else:
            self.timer.stop()
            self.target = self.level = 0.0
            self.update()
    def set_level(self, level):
        self.target = max(0.0, min(1.0, float(level)))
    def tick(self):
        self.level += (self.target - self.level) * 0.32
        self.phase += 0.19
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        for position, color in ((0, '#78c8ff'), (0.45, '#a4a0ff'), (0.75, '#df9ae8'), (1, '#f6b1a2')):
            gradient.setColorAt(position, QColor(color if self.listening else '#63636d'))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        bars = 34
        gap = self.width() / bars
        for index in range(bars):
            envelope = math.sin(math.pi * (index + 0.5) / bars) ** 0.65
            ripple = 0.4 + 0.6 * abs(math.sin(index * 0.62 + self.phase))
            height = 3 + self.level * (self.height() - 6) * envelope * ripple
            painter.drawRoundedRect(QRectF(index * gap + 1, (self.height() - height) / 2,
                                            max(2, gap - 3), height), 2, 2)
