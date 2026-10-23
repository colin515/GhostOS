"""Responsive desktop: vector identity, focused composer, adjacent settings and streaming voice."""
from __future__ import annotations
import json
import sys
import threading
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QPlainTextEdit, QSplitter, QMessageBox,
                            QFrame, QCheckBox, QSystemTrayIcon, QMenu)
from ui.trajectory_view import TrajectoryView, event_text
from ui.settings_view import SettingsView
from ui.widgets import GhostLogo, AudioVisualizer, ghost_icon
from ui.tasks import VoiceTask

STYLE = '''
QWidget { background:#141416; color:#f3f3f5; font-family:"Segoe UI Variable", "Segoe UI"; font-size:14px; }
QLabel#brand {font-size:24px; font-weight:650; letter-spacing:-1px;}
QLabel#hero {font-size:32px; font-weight:600; color:#f4f4f6; padding:8px 0;}
QLabel#subtitle {color:#96969f; padding-bottom:12px;}
QLabel#eyebrow {color:#92929c; font-size:11px; font-weight:600; letter-spacing:2px; padding:8px 0;}
QLabel#status {color:#b4d4c1; background:#202824; border:1px solid #303d35; border-radius:12px; padding:7px 14px;}
QLabel#preview {background:#202023; color:#9898a2; border:1px solid #303035; border-radius:14px; padding:8px;}
QFrame#composer {background:#222225; border:1px solid #414149; border-radius:22px;}
QPlainTextEdit,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:#222225; border:1px solid #39393e; border-radius:10px; padding:10px; selection-background-color:#55517c;}
QTextEdit {background:#202023; border:1px solid #39393e; border-radius:12px; padding:10px;}
QPlainTextEdit#chat {background:transparent; border:0; padding:10px 0; font-size:15px;}
QPlainTextEdit#prompt {border:0; background:transparent; padding:8px; font-size:16px;}
QPlainTextEdit#activityLog {background:transparent; border:0; color:#b4b4be; font-size:12px; padding:4px 0;}
QPushButton {background:#2c2c30; border:1px solid #414148; border-radius:12px; padding:10px 15px;}
QPushButton:hover {background:#3b3b42;} QPushButton:disabled {color:#73737e; border-color:#303036;}
QPushButton#send {background:#eeedf8; color:#22212c; border-color:#eeedf8; font-weight:650;}
QPushButton#send:hover {background:#d7d4ee;} QPushButton#send:disabled {background:#45434e; color:#96939e; border-color:#45434e;}
QPushButton#settings {font-family:"Segoe UI Symbol"; font-size:21px; padding:5px;}
QPushButton#stop {background:#322326; color:#ffb3bd; border-color:#533039;}
QSplitter::handle {background:#2b2b30; width:1px;} QCheckBox {padding:4px; color:#b9b9c2;}
QCheckBox::indicator {width:16px; height:16px; border:1px solid #63636e; border-radius:4px; background:#26262b;}
QCheckBox::indicator:checked {background:#bdb7ec; border-color:#d5d0f5;}
QScrollArea {border:0;} QToolTip {background:#303035; color:#fff; border:1px solid #505057;}
QLabel a {color:#b9b4ff;}
'''

class MainWindow(QMainWindow):
    def __init__(self, runtime):
        super().__init__()
        self.runtime, self.cursor, self.frame_id = runtime, 0, 0
        from ui.control_panel import ControlPanel
        self.panel = ControlPanel(self.stop, self.browser_help)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(ghost_icon(), self)
            self.tray.setToolTip('GhostOS · local computer control')
            menu = QMenu(self)
            menu.addAction('Show GhostOS', self.show_from_tray)
            menu.addAction('Emergency stop', self.stop)
            menu.addAction('Quit', self.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_from_tray() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self.tray.show()
        self.voice_task = None
        self.approval_dialog = None
        self.approval_id = None
        self.closing_requested = False
        self.last_chat = ''
        self.setWindowTitle('GhostOS')
        self.setWindowIcon(ghost_icon())
        self.resize(1240, 820)
        self.setMinimumSize(850, 610)
        root, layout = QWidget(), QVBoxLayout()
        layout.setContentsMargins(26, 20, 26, 16)
        layout.setSpacing(16)
        root.setLayout(layout)
        self.setCentralWidget(root)
        header = QHBoxLayout()
        header.addWidget(GhostLogo(46))
        title = QLabel('GhostOS')
        title.setObjectName('brand')
        header.addWidget(title)
        header.addStretch()
        self.status = QLabel('●  Ready · local inference')
        self.status.setObjectName('status')
        header.addWidget(self.status)
        self.general_settings_button = QPushButton('Settings')
        self.general_settings_button.setToolTip('Voice, appearance and phone dashboard')
        self.general_settings_button.clicked.connect(lambda: self.open_settings('general'))
        header.addWidget(self.general_settings_button)
        self.stop_button = QPushButton('■  Stop')
        self.stop_button.setObjectName('stop')
        self.stop_button.clicked.connect(self.stop)
        header.addWidget(self.stop_button)
        layout.addLayout(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        chat, chat_layout = QWidget(), QVBoxLayout()
        chat.setLayout(chat_layout)
        chat_layout.setContentsMargins(0, 16, 20, 0)
        welcome = QLabel('What can I help you do?')
        welcome.setObjectName('hero')
        chat_layout.addWidget(welcome)
        subtitle = QLabel('Your apps. Your computer. Your local AI.')
        subtitle.setObjectName('subtitle')
        chat_layout.addWidget(subtitle)
        self.chat = QPlainTextEdit()
        self.chat.setObjectName('chat')
        self.chat.setReadOnly(True)
        self.chat.setMaximumBlockCount(300)
        self.chat.setPlaceholderText('Describe a goal below, or speak naturally.\nGhostOS will show its progress here.')
        chat_layout.addWidget(self.chat, 1)
        composer = QFrame()
        composer.setObjectName('composer')
        compose_layout = QVBoxLayout(composer)
        compose_layout.setContentsMargins(12, 10, 12, 12)
        self.input = QPlainTextEdit()
        self.input.setObjectName('prompt')
        self.input.setPlaceholderText('Ask GhostOS to do something…')
        self.input.setMaximumHeight(110)
        compose_layout.addWidget(self.input)
        buttons = QHBoxLayout()
        self.voice_button = QPushButton('●  Speak')
        self.voice_button.setToolTip('Speak a command. Pause to finish and send automatically; click again to cancel.')
        self.voice_button.clicked.connect(self.record)
        buttons.addWidget(self.voice_button)
        self.visualizer = AudioVisualizer()
        buttons.addWidget(self.visualizer, 1)
        self.settings_button = QPushButton('⚙')
        self.settings_button.setObjectName('settings')
        self.settings_button.setFixedSize(44, 44)
        self.settings_button.setAccessibleName('AI settings')
        self.settings_button.setToolTip('AI configuration · model, permissions and execution')
        self.settings_button.clicked.connect(lambda: self.open_settings('ai'))
        buttons.addWidget(self.settings_button)
        self.send = QPushButton('Send  ↑')
        self.send.setObjectName('send')
        self.send.setMinimumHeight(44)
        self.send.clicked.connect(self.start)
        buttons.addWidget(self.send)
        compose_layout.addLayout(buttons)
        chat_layout.addWidget(composer)
        footer = QHBoxLayout()
        self.voice_status = QLabel('Pause after speaking to send your command')
        self.voice_status.setObjectName('subtitle')
        footer.addWidget(self.voice_status, 1)
        self.narrate = QCheckBox('Narrate actions')
        self.narrate.setChecked(runtime.settings.narrate_actions)
        self.narrate.toggled.connect(self.toggle_narration)
        footer.addWidget(self.narrate)
        chat_layout.addLayout(footer)
        splitter.addWidget(chat)
        self.trajectory = TrajectoryView()
        splitter.addWidget(self.trajectory)
        splitter.setSizes([790, 365])
        layout.addWidget(splitter, 1)
        safety = QLabel('Yellow screen border = agent active     ·     Emergency stop: Ctrl + Alt + K or Ctrl + Alt + Esc')
        safety.setObjectName('subtitle')
        layout.addWidget(safety)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(150)

    def open_settings(self, section='general'):
        if self.runtime.running:
            self.status.setText('Stop the task before opening settings')
            return
        SettingsView(self.runtime, self, section=section).exec()
        self.narrate.setChecked(self.runtime.settings.narrate_actions)

    def showEvent(self, event):
        super().showEvent(event)
        from agent.window_focus import mark_ui
        mark_ui(int(self.winId()))

    def hide_for_task(self):
        from agent.window_focus import mark_ui
        for widget in QApplication.topLevelWidgets():
            mark_ui(int(widget.winId()))
            if widget not in (self.panel, self.approval_dialog):
                widget.hide()
        self.hide()
        self.panel.help_button.hide()
        self.panel.label.setText('GhostOS is working in the background')
        self.panel.show()

    def show_from_tray(self):
        # Never activate the chat while a worker still owns desktop input.
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, self.runtime.running)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, self.runtime.running)
        self.showNormal()
        if not self.runtime.running:
            self.raise_()
            self.activateWindow()

    def return_to_chat(self):
        if self.runtime.running or self.closing_requested:
            return
        self.show_from_tray()
        self.input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.voice_status.setText('Ready for your next command · press Speak or type below')

    def browser_help(self):
        self.panel.label.setText('Optional CDP setup: choose Chrome in AI settings. GhostOS creates a separate local browser profile automatically. If your policy blocks it, see docs/browser_control.md. Mouse and keyboard continue to work.')
        self.panel.help_button.hide()

    def toggle_narration(self, checked):
        self.runtime.settings.narrate_actions = checked
        try:
            self.runtime.settings.save()
        except OSError as exc:
            self.status.setText(f'Could not save setting: {exc}')
        if not checked:
            self.runtime.speech.cancel()

    def append_chat(self, text):
        if text and text != self.last_chat:
            self.chat.appendPlainText(text)
            self.last_chat = text

    def start(self):
        self.submit_goal(self.input.toPlainText().strip())

    def submit_goal(self, goal, voice=False):
        if not goal:
            return
        try:
            self.runtime.start(goal)
            if voice:
                self.runtime.speech.say('On it.', priority=True)
            self.input.clear()
            self.hide_for_task()
        except (RuntimeError, ValueError) as exc:
            self.status.setText(str(exc))

    def stop(self):
        if self.voice_task:
            self.voice_task.cancel.set()
        self.runtime.speech.cancel()
        self.visualizer.set_listening(False)
        self.status.setText('Stopping…')
        threading.Thread(target=self.runtime.stop, daemon=True).start()

    def poll(self):
        request = self.runtime.settings.data_dir / 'show-window.request'
        if request.exists():
            try:
                request.unlink()
                self.show_from_tray()
            except OSError:
                pass
        self.runtime.preview_enabled = self.isVisible() and not self.isMinimized()
        events = self.runtime.bus.after(self.cursor)[:60]
        self.trajectory.add_events(events)
        finished = False
        for event in events:
            self.cursor = event['id']
            kind = event['kind']
            if kind == 'STARTED':
                finished = False
                self.hide_for_task()
                self.append_chat('You\n' + event_text(event) + '\n')
            elif kind in ('THOUGHT', 'STATUS', 'ERROR', 'RECOVERY', 'TASK_PROGRESS'):
                self.append_chat('GhostOS\n' + event_text(event) + '\n')
            if kind in ('INFERENCE', 'RECOVERY'):
                self.status.setText('●  ' + event_text(event)[:85])
            if kind == 'FINISHED':
                finished = True
                self.panel.hide()
                self.status.setText('●  ' + event_text(event))
            if kind == 'BROWSER_FALLBACK':
                self.panel.label.setText(event['message'])
                self.panel.help_button.show()
            if kind == 'VOICE_APPROVAL':
                self.panel.label.setText(event['message'])
                self.panel.wave.set_listening(True)
            if kind == 'AUDIO_LEVEL':
                self.panel.wave.set_listening(event['level'] > 0)
                self.panel.wave.set_level(event['level'])
        busy = self.runtime.running
        recording = self.voice_task and self.voice_task.isRunning()
        self.send.setEnabled(not busy and not recording)
        self.settings_button.setEnabled(not recording)
        self.voice_button.setEnabled(not busy or bool(recording))
        if self.runtime.emergency_stopped and recording:
            self.voice_task.cancel.set()
            self.visualizer.set_listening(False)
        frame = self.runtime.bus.latest_frame()
        if self.runtime.preview_enabled and frame and frame['id'] > self.frame_id:
            self.frame_id = frame['id']
            self.trajectory.frame(frame)
        self.poll_approvals()
        if finished:
            self.return_to_chat()

    def poll_approvals(self):
        pending = self.runtime.approvals.pending()
        ids = {p['id'] for p in pending}
        if self.approval_dialog and self.approval_id not in ids:
            dialog = self.approval_dialog
            self.approval_dialog = None
            self.approval_id = None
            dialog.close()
        if pending and self.approval_dialog is None:
            request = pending[0]
            self.approval_id = request['id']
            dialog = QMessageBox(None)
            dialog.setWindowTitle('Approve agent action')
            dialog.setText('Allow this action?')
            dialog.setInformativeText(json.dumps(request['action'], indent=2))
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            dialog.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
            dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            for button in dialog.buttons():
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            from agent.window_focus import mark_ui
            mark_ui(int(dialog.winId()))
            dialog.finished.connect(lambda result, rid=request['id']: self.approval_finished(rid, result))
            self.approval_dialog = dialog
            dialog.show()

    def approval_finished(self, request_id, result):
        if self.approval_dialog:
            from agent.window_focus import unmark_ui
            unmark_ui(int(self.approval_dialog.winId()))
        # Foreground restoration can call Windows APIs; never block the GUI event loop.
        threading.Thread(target=self.runtime.approve,
                         args=(request_id, result == QMessageBox.StandardButton.Yes), daemon=True).start()
        self.approval_dialog = None
        self.approval_id = None

    def record(self):
        if self.voice_task and self.voice_task.isRunning():
            self.voice_task.cancel.set()
            self.voice_status.setText('Cancelling voice input…')
            return
        if not self.runtime.settings.voice_enabled:
            self.open_settings()
            self.voice_status.setText('Enable voice and download its model in Model and voice setup.')
            return
        if self.runtime.running:
            return
        self.runtime.emergency_stopped = False
        self.runtime.speech.cancel()  # Avoid transcribing our own narration.
        self.voice_task = VoiceTask(self.runtime.settings, self)
        self.voice_task.progress.connect(self.voice_progress)
        self.voice_task.level.connect(self.visualizer.set_level)
        self.voice_task.result.connect(self.voice_result)
        self.voice_task.error.connect(self.voice_error)
        self.voice_task.finished.connect(self.voice_finished)
        self.visualizer.set_listening(True)
        self.voice_button.setText('■  Cancel')
        self.send.setEnabled(False)
        self.voice_task.start()

    def voice_progress(self, message):
        self.voice_status.setText(message)
        if message.startswith('Transcribing'):
            self.visualizer.set_listening(False)

    def voice_result(self, text):
        if self.voice_task.cancel.is_set() or self.runtime.emergency_stopped or self.closing_requested:
            return
        self.visualizer.set_listening(False)
        if text.strip():
            self.voice_status.setText('Heard you. Starting your task…')
            self.submit_goal(text.strip(), voice=True)
        else:
            self.voice_status.setText('No speech detected. Try again when ready.')

    def voice_error(self, message):
        self.visualizer.set_listening(False)
        if not self.voice_task.cancel.is_set():
            self.voice_status.setText(message)

    def voice_finished(self):
        self.visualizer.set_listening(False)
        self.voice_button.setText('●  Speak')
        if self.closing_requested:
            self.close()

    def closeEvent(self, event):
        self.closing_requested = True
        from agent.window_focus import unmark_ui
        unmark_ui(int(self.winId()))
        if self.voice_task and self.voice_task.isRunning():
            self.voice_task.cancel.set()
            self.voice_status.setText('Stopping voice input before closing…')
            event.ignore()
            return
        self.timer.stop()
        self.panel.close()
        if self.tray:
            self.tray.hide()
        if self.approval_dialog:
            self.approval_dialog.close()
        self.runtime.preview_enabled = False
        self.stop()
        self.trajectory.shutdown()
        event.accept()
        QApplication.instance().quit()


def launch(runtime, smoke_test=False):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('GhostOS')
    app.setQuitOnLastWindowClosed(False)
    import os
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GhostOS.Desktop')
    app.setWindowIcon(ghost_icon())
    app.setStyleSheet(STYLE)
    window = MainWindow(runtime)
    window.show()
    from agent.startup import log_startup
    log_startup('Desktop window ready')
    if runtime.settings.startup_notice:
        window.append_chat('GhostOS\n' + runtime.settings.startup_notice)
        window.status.setText('Settings recovered · review AI settings before running')
    if smoke_test:
        QTimer.singleShot(750, window.close)
    if not runtime.settings.setup_complete:
        from ui.setup_wizard import SetupWizard
        if SetupWizard(runtime, window).exec() != 1:
            window.status.setText('Setup incomplete · open AI settings to finish')
    return app.exec()
