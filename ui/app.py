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
QWidget { background:#10121b; color:#eceef9; font-family:"Segoe UI Variable","Segoe UI"; font-size:14px; }
QMainWindow { background:#10121b; }
QLabel#brand {font-size:25px; font-weight:700; color:#f5f5fc; letter-spacing:-1px;}
QLabel#hero {font-size:34px; font-weight:650; color:#fcfcff; padding:10px 0;}
QLabel#subtitle {color:#9ba4b8; padding-bottom:12px;}
QLabel#eyebrow {color:#a29fcb; font-size:11px; font-weight:700; letter-spacing:2px; padding:8px 0;}
QLabel#status {color:#9df0c8; background:#172e2d; border:1px solid #2c5145; border-radius:12px; padding:8px 15px; font-weight:600;}
QLabel#preview {background:#181d2b; color:#9daac0; border:1px solid #303b51; border-radius:15px; padding:9px;}
QFrame#composer {background:#1b2030; border:1px solid #455278; border-radius:23px;}
QFrame#composer:focus-within {border-color:#9388ea;}
QPlainTextEdit,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:#1b2030; border:1px solid #354057; border-radius:12px; padding:11px; selection-background-color:#6760a6;}
QPlainTextEdit:focus,QLineEdit:focus {border:1px solid #7771bf;}
QTextEdit {background:#1b2030; border:1px solid #343d56; border-radius:12px; padding:10px;}
QPlainTextEdit#chat {background:transparent; border:0; padding:10px 0; font-size:15px;}
QPlainTextEdit#prompt {border:0; background:transparent; padding:8px; font-size:16px;}
QPlainTextEdit#activityLog {background:transparent; border:0; color:#bac2d7; font-size:12px; padding:4px 0;}
QPushButton {background:#272d40; color:#f0f1fa; border:1px solid #3d4860; border-radius:12px; padding:10px 15px; font-weight:500;}
QPushButton:hover {background:#323b55; border-color:#6675a2;}
QPushButton:pressed {background:#22263a;}
QPushButton:disabled {color:#68748f; border-color:#273046; background:#1c2231;}
QPushButton#send {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #c4bafa,stop:1 #8ccff1); color:#141a2c; border-color:#b4bbf5; font-weight:750;}
QPushButton#send:hover {background:#dad6ff; border-color:#ece8ff;}
QPushButton#send:disabled {background:#393d54; color:#929ab4; border-color:#414962;}
QPushButton#settings {font-family:"Segoe UI Symbol"; font-size:21px; padding:5px;}
QPushButton#stop {background:#392430; color:#ffc2cd; border-color:#653849;}
QPushButton#stop:hover {background:#613044; border-color:#98506b;}
QSplitter::handle {background:#273148; width:1px;}
QCheckBox {padding:4px; color:#c1c9df;}
QCheckBox::indicator {width:16px; height:16px; border:1px solid #687593; border-radius:5px; background:#242c3e;}
QCheckBox::indicator:checked {background:#aaa4f5; border-color:#e0dcff;}
QScrollArea {border:0;}
QScrollBar:vertical {background:#151b29; width:9px; margin:2px;}
QScrollBar::handle:vertical {background:#3b4860; border-radius:4px; min-height:26px;}
QToolTip {background:#252d42; color:#f8f8ff; border:1px solid #586484; padding:7px;}
QLabel a {color:#b2a8ff;}
'''

class MainWindow(QMainWindow):
    def __init__(self, runtime):
        super().__init__()
        self.runtime, self.cursor, self.frame_id = runtime, 0, 0
        from ui.control_panel import ControlPanel
        self.panel = ControlPanel(self.stop, self.browser_help)
        from ui.ghost_cursor import GhostCursor
        self.ghost_cursor = GhostCursor()
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
        explanation = ('Optional CDP setup: choose Chrome in AI settings. GhostOS creates a separate '
                       'local browser profile automatically. If your policy blocks it, see '
                       'docs/browser_control.md. Mouse and keyboard continue to work.')
        self.panel.label.setText(explanation)
        self.panel.setToolTip(explanation)
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
            if kind in ('INFERENCE', 'PLAN', 'RECOVERY', 'ERROR', 'ACTION', 'EXECUTING',
                        'MOUSE', 'TARGET', 'APPROVAL', 'VOICE_APPROVAL', 'AUDIO_LEVEL'):
                self.panel.set_activity(kind)
            if kind == 'MOUSE':
                self.ghost_cursor.note_mouse(event)
            if kind == 'FINISHED':
                finished = True
                self.ghost_cursor.hide()
                self.panel.hide()
                self.status.setText('●  ' + event_text(event))
            if kind == 'BROWSER_FALLBACK':
                self.panel.label.setText(event['message'])
                self.panel.setToolTip(event['message'])
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
        self.ghost_cursor.close()
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
