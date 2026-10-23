"""Coalesced preview decoding off the Qt GUI thread; one pending frame, bounded text."""
import base64
import json
import threading
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit


def event_text(event):
    if event.get('kind') == 'MOUSE':
        return str({key: value for key, value in event.items() if key in ('phase', 'position', 'start', 'target', 'button', 'clicks', 'ticks')})
    if event.get('message'):
        return str(event['message'])[:1800]
    if event.get('goal'):
        return str(event['goal'])
    if event.get('status'):
        return str(event['status']).replace('_', ' ').capitalize()
    if event.get('steps'):
        return ' → '.join(event['steps'])
    if event.get('action'):
        action = event['action']
        return action['kind'] + '  ' + json.dumps(action.get('args', {}), ensure_ascii=False)[:1000]
    return {'STARTED': 'Starting task', 'STOP': 'Stopping task', 'FINISHED': 'Task ended'}.get(event['kind'], '')


class FrameDecoder(QThread):
    decoded = pyqtSignal(int, QImage)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.condition = threading.Condition()
        self.pending = None
        self.closing = False
    def submit(self, event, width):
        with self.condition:
            self.pending = (event['id'], event['image'], max(100, width))
            self.condition.notify()
    def run(self):
        while True:
            with self.condition:
                while self.pending is None and not self.closing:
                    self.condition.wait()
                if self.closing:
                    return
                frame_id, encoded, width = self.pending
                self.pending = None
            try:
                image = QImage.fromData(base64.b64decode(encoded))
            except (ValueError, TypeError):
                continue
            if not image.isNull():
                image = image.scaled(width, 270, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                self.decoded.emit(frame_id, image)
    def close(self):
        with self.condition:
            self.closing = True
            self.condition.notify()
        self.wait(1500)


class TrajectoryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel('LIVE ACTIVITY')
        heading.setObjectName('eyebrow')
        layout.addWidget(heading)
        self.screen = QLabel('A live preview appears during your task')
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setMinimumHeight(180)
        self.screen.setMaximumHeight(285)
        self.screen.setWordWrap(True)
        self.screen.setObjectName('preview')
        layout.addWidget(self.screen)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setObjectName('activityLog')
        layout.addWidget(self.log)
        self.frame_id = 0
        self.decoder = FrameDecoder(self)
        self.decoder.decoded.connect(self.render_frame)
        self.decoder.start()
    def frame(self, event):
        self.decoder.submit(event, self.width() - 24)
    def render_frame(self, frame_id, image):
        if frame_id >= self.frame_id:
            self.frame_id = frame_id
            self.screen.setPixmap(QPixmap.fromImage(image))
    def add_events(self, events):
        lines = []
        for event in events:
            if event['kind'] in ('INFERENCE', 'AUDIO_LEVEL'):
                continue
            label = {'THOUGHT': 'PROGRESS', 'RESULT': 'DONE', 'STARTED': 'GOAL'}.get(event['kind'], event['kind'])
            lines.append(label + '  ' + event_text(event))
        if lines:
            self.log.appendPlainText('\n'.join(lines))
    def add_event(self, event):
        self.add_events([event])
    def shutdown(self):
        self.decoder.close()
