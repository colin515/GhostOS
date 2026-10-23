from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit
import base64

class TrajectoryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel('LIVE TRAJECTORY')
        heading.setObjectName('eyebrow')
        layout.addWidget(heading)
        self.screen = QLabel('Your screen appears when a run starts')
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setMinimumHeight(180)
        self.screen.setWordWrap(True)
        layout.addWidget(self.screen)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(600)
        layout.addWidget(self.log)
        self.pixmap = None

    def frame(self, event):
        pixmap = QPixmap()
        if pixmap.loadFromData(base64.b64decode(event['image'])):
            self.pixmap = pixmap
            self.render_frame()

    def render_frame(self):
        if self.pixmap:
            self.screen.setPixmap(self.pixmap.scaled(max(100, self.width() - 30), 320,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_frame()

    def add_event(self, event):
        import json
        message = event.get('message') or event.get('status') or json.dumps(event.get('action', event.get('steps', '')), ensure_ascii=False)
        self.log.appendPlainText(f'{event["kind"]}  {message}')
