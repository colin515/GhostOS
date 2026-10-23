"""Dark PyQt6 desktop with streaming activity, screenshots, approvals and optional voice."""
from __future__ import annotations
import json
import sys
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QPlainTextEdit, QTextEdit, QSplitter, QMessageBox)
from ui.trajectory_view import TrajectoryView
from ui.settings_view import SettingsView
from ui.tasks import Task

STYLE = '''
QWidget { background:#11141b; color:#e9effc; font-family:Segoe UI; font-size:14px; }
QMainWindow { background:#11141b; }
QLabel#hero {font-size:30px; font-weight:600; color:#b3caff; padding:14px 0;}
QLabel#eyebrow {color:#a2b2d1; font-size:12px; font-weight:600; padding:10px;}
QTextEdit,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox {background:#1c2230; border:1px solid #343e50; border-radius:12px; padding:12px; selection-background-color:#41577a;}
QPushButton {background:#263146; border:1px solid #3c4b64; border-radius:10px; padding:10px 16px;}
QPushButton:hover {background:#354760;} QPushButton:disabled {color:#68758c;}
QPushButton#send {background:#a7c5ff; color:#132342; font-weight:600;}
QPushButton#stop {background:#703042; border-color:#a74e67;}
QSplitter::handle {background:#293246;} QCheckBox {padding:5px;}
'''

class MainWindow(QMainWindow):
    def __init__(self, runtime):
        super().__init__()
        self.runtime, self.cursor, self.frame_id = runtime, 0, 0
        self.voice_task = self.tts_task = None
        self.approval_dialog = None
        self.approval_id = None
        self.setWindowTitle('GhostOS · Your local OS agent')
        self.resize(1250, 820)
        root, layout = QWidget(), QVBoxLayout()
        root.setLayout(layout)
        self.setCentralWidget(root)
        header = QHBoxLayout()
        title = QLabel('GhostOS')
        title.setObjectName('hero')
        header.addWidget(title)
        self.status = QLabel('Ready · local inference')
        header.addWidget(self.status)
        header.addStretch()
        settings = QPushButton('Settings')
        settings.clicked.connect(lambda: SettingsView(runtime, self).exec())
        header.addWidget(settings)
        stop = QPushButton('■ Stop')
        stop.setObjectName('stop')
        stop.clicked.connect(runtime.stop)
        header.addWidget(stop)
        layout.addLayout(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        chat, chat_layout = QWidget(), QVBoxLayout()
        chat.setLayout(chat_layout)
        welcome = QLabel('What would you like to do?')
        welcome.setObjectName('hero')
        chat_layout.addWidget(welcome)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.document().setMaximumBlockCount(600)
        self.chat.setPlaceholderText('Describe your goal. Watch each action as your local agent works.')
        chat_layout.addWidget(self.chat)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText('Open an app, work in a browser, or describe a multi-step goal…')
        self.input.setMaximumHeight(130)
        chat_layout.addWidget(self.input)
        buttons = QHBoxLayout()
        self.voice_button = QPushButton('● Voice')
        self.voice_button.clicked.connect(self.record)
        buttons.addWidget(self.voice_button)
        buttons.addStretch()
        self.send = QPushButton('Start goal ↗')
        self.send.setObjectName('send')
        self.send.clicked.connect(self.start)
        buttons.addWidget(self.send)
        chat_layout.addLayout(buttons)
        chat_layout.addWidget(QLabel('Emergency brake: Ctrl + Alt + K  ·  Ctrl + Alt + Esc'))
        splitter.addWidget(chat)
        self.trajectory = TrajectoryView()
        splitter.addWidget(self.trajectory)
        splitter.setSizes([750, 450])
        layout.addWidget(splitter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)

    def append_chat(self, text):
        self.chat.append(text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>'))

    def start(self):
        goal = self.input.toPlainText().strip()
        if not goal:
            return
        try:
            self.runtime.start(goal)
            self.append_chat('You · ' + goal)
            self.input.clear()
            # Remove our window from the automation target; game mode waits three seconds for focus.
            self.showMinimized()
        except (RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot start', str(exc))

    def poll(self):
        for event in self.runtime.bus.after(self.cursor):
            self.cursor = event['id']
            self.trajectory.add_event(event)
            kind = event['kind']
            if kind in ('THOUGHT', 'STATUS', 'ERROR', 'RECOVERY'):
                self.append_chat('Agent · ' + (event.get('message') or event.get('status', '')))
            if kind == 'FINISHED':
                self.showNormal()
                self.status.setText(event['status'])
                if self.runtime.settings.tts_enabled:
                    self.say(event['status'].replace('_', ' '))
        self.send.setEnabled(not self.runtime.running)
        frame = self.runtime.bus.latest_frame()
        if frame and frame['id'] > self.frame_id:
            self.frame_id = frame['id']
            self.trajectory.frame(frame)
        pending = self.runtime.approvals.pending()
        ids = {p['id'] for p in pending}
        if self.approval_dialog and self.approval_id not in ids:
            self.approval_dialog.close()
            self.approval_dialog = None
            self.approval_id = None
        if pending and self.approval_dialog is None:
            request = pending[0]
            self.approval_id = request['id']
            dialog = QMessageBox(self)
            dialog.setWindowTitle('Approve agent action')
            dialog.setText('Allow this exact action?')
            dialog.setInformativeText(json.dumps(request['action'], indent=2))
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
            # A non-modal dialog keeps remote approval, screenshots and stop responsive.
            dialog.finished.connect(lambda result, rid=request['id']: self.approval_finished(rid, result))
            self.approval_dialog = dialog
            dialog.show()

    def approval_finished(self, request_id, result):
        self.runtime.approve(request_id, result == QMessageBox.StandardButton.Yes)
        self.approval_dialog = None
        self.approval_id = None

    def record(self):
        if not self.runtime.settings.voice_enabled:
            QMessageBox.information(self, 'Voice setup', 'Enable voice and download its model in Settings → Open model and voice setup.')
            return
        if self.voice_task and self.voice_task.isRunning():
            return
        from agent.voice import record_and_transcribe
        self.voice_button.setEnabled(False)
        self.voice_task = Task(lambda progress: record_and_transcribe(self.runtime.settings, progress), self)
        self.voice_task.progress.connect(self.status.setText)
        self.voice_task.result.connect(self.input.setPlainText)
        self.voice_task.error.connect(self.status.setText)
        self.voice_task.finished.connect(lambda: self.voice_button.setEnabled(True))
        self.voice_task.start()

    def say(self, text):
        if self.tts_task and self.tts_task.isRunning():
            return
        from agent.voice import speak
        self.tts_task = Task(lambda progress: speak(text), self)
        self.tts_task.error.connect(self.status.setText)
        self.tts_task.start()

    def closeEvent(self, event):
        for task in (self.voice_task, self.tts_task):
            if task and task.isRunning():
                self.status.setText('Wait for the voice operation to finish before closing.')
                event.ignore()
                return
        self.runtime.stop(reason='Desktop closed')
        event.accept()


def launch(runtime):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(STYLE)
    window = MainWindow(runtime)
    window.show()
    if not runtime.settings.setup_complete:
        from ui.setup_wizard import SetupWizard
        if SetupWizard(runtime, window).exec() != 1:
            window.status.setText('Setup incomplete — open Settings to finish')
    return app.exec()
