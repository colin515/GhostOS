"""Independent Qt indicator process: click-through yellow edges on every connected screen."""
from __future__ import annotations
import os


def run_indicator(stop, ready):
    from PyQt6.QtCore import Qt, QTimer, QRect
    from PyQt6.QtGui import QColor, QPainter
    from PyQt6.QtWidgets import QApplication, QWidget
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    class Edge(QWidget):
        def __init__(self, rect, orientation):
            super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                             Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                             Qt.WindowType.WindowDoesNotAcceptFocus)
            self.orientation = orientation
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setGeometry(rect)
            self.show()
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                user = ctypes.WinDLL('user32', use_last_error=True)
                user.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
                user.SetWindowDisplayAffinity.restype = wintypes.BOOL
                # On pre-2004 Windows do not use the old black-rectangle capture mode.
                import sys
                if sys.getwindowsversion().build >= 19041:
                    user.SetWindowDisplayAffinity(int(self.winId()), 0x11)
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Static glow cannot manufacture visual changes in the agent's stall detector.
            for i, alpha in enumerate((255, 235, 180, 115, 65, 32, 14, 5)):
                painter.setPen(QColor(255, 210, 48, alpha))
                if self.orientation == 'top':
                    painter.drawLine(0, i, self.width(), i)
                elif self.orientation == 'bottom':
                    painter.drawLine(0, self.height() - 1 - i, self.width(), self.height() - 1 - i)
                elif self.orientation == 'left':
                    painter.drawLine(i, 0, i, self.height())
                else:
                    painter.drawLine(self.width() - 1 - i, 0, self.width() - 1 - i, self.height())
    edges = []
    connected = set()
    def refresh(*_):
        for edge in edges:
            edge.close()
        edges.clear()
        for screen in app.screens():
            if screen not in connected:
                screen.geometryChanged.connect(refresh)
                connected.add(screen)
            g = screen.geometry()
            rects = [(QRect(g.x(), g.y(), g.width(), 8), 'top'),
                     (QRect(g.x(), g.bottom() - 7, g.width(), 8), 'bottom'),
                     (QRect(g.x(), g.y(), 8, g.height()), 'left'),
                     (QRect(g.right() - 7, g.y(), 8, g.height()), 'right')]
            edges.extend(Edge(rect, side) for rect, side in rects)
    app.screenAdded.connect(refresh)
    app.screenRemoved.connect(refresh)
    refresh()
    app.processEvents()
    ready.set()
    timer = QTimer()
    timer.timeout.connect(lambda: app.quit() if stop.is_set() else None)
    timer.start(80)
    app.exec()


class ActivityIndicator:
    def __init__(self, context):
        self.stop = context.Event()
        self.ready = context.Event()
        self.process = context.Process(target=run_indicator, args=(self.stop, self.ready),
                                       name='GhostOS-screen-indicator', daemon=True)
    def start(self):
        self.process.start()
        if not self.ready.wait(8):
            self.close()
            raise RuntimeError('The active-screen indicator could not start; no automation was launched')
    def request_stop(self):
        self.stop.set()
    def close(self):
        self.stop.set()
        if self.process.pid:
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1)
