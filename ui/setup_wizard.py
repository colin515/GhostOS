"""First-launch hardware scan and explicit model/voice download approval."""
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QLabel, QPushButton,
                            QTextEdit, QVBoxLayout, QHBoxLayout)
from ui.tasks import Task
from agent.hardware import hardware_report, ollama_status
from setup import MODELS, download_model, download_voice

class SetupWizard(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime, self.task = runtime, None
        self.setWindowTitle('Welcome to GhostOS')
        self.resize(650, 630)
        layout = QVBoxLayout(self)
        title = QLabel('Set up your local agent')
        title.setObjectName('hero')
        layout.addWidget(title)
        intro = QLabel('Choose a vision model for this PC. Downloads start only when you press Download.\nOllama runs separately; all agent inference uses its local API.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        link = QLabel('<a href="https://ollama.com/download/windows">Download Ollama for Windows ↗</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(MODELS)
        layout.addWidget(self.model)
        self.voice = QCheckBox('Also download optional Whisper voice model')
        layout.addWidget(self.voice)
        self.note = QLabel(f'LAN address: http://runtime:{runtime.settings.web_port}'.replace('runtime', runtime.local_ip))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QHBoxLayout()
        self.scan = QPushButton('Scan again')
        self.pull = QPushButton('Download selected model')
        self.done = QPushButton('Save and continue')
        buttons.addWidget(self.scan)
        buttons.addWidget(self.pull)
        buttons.addWidget(self.done)
        layout.addLayout(buttons)
        self.scan.clicked.connect(self.inspect)
        self.pull.clicked.connect(self.download)
        self.done.clicked.connect(self.save)
        self.inspect()

    def busy(self, yes):
        for button in (self.scan, self.pull, self.done):
            button.setEnabled(not yes)
        self.model.setEnabled(not yes)
        self.voice.setEnabled(not yes)

    def launch_task(self, function, callback):
        if self.task and self.task.isRunning():
            return
        self.busy(True)
        self.task = Task(function, self)
        self.task.progress.connect(self.note.setText)
        self.task.result.connect(callback)
        self.task.error.connect(self.note.setText)
        self.task.finished.connect(lambda: self.busy(False))
        self.task.start()

    def inspect(self):
        def work(progress):
            progress('Measuring hardware and checking local Ollama…')
            return hardware_report(), ollama_status(self.runtime.settings.ollama_host)
        def show(result):
            import json
            hardware, status = result
            self.report.setPlainText(json.dumps({'hardware': hardware, 'ollama': status}, indent=2))
            self.model.setCurrentText(hardware['recommended_model'])
            self.note.setText(hardware['model_note'])
        self.launch_task(work, show)

    def download(self):
        # Pressing this explicitly labelled button is approval for these downloads.
        model, voice = self.model.currentText().strip(), self.voice.isChecked()
        settings = self.runtime.settings
        def work(progress):
            download_model(settings, model, progress)
            if voice:
                download_voice(settings, progress)
            return voice
        def complete(voice_ready):
            settings.voice_enabled = voice_ready
            self.note.setText('Downloads complete. Click Save and continue.')
        self.launch_task(work, complete)

    def save(self):
        model = self.model.currentText().strip()
        def work(progress):
            status = ollama_status(self.runtime.settings.ollama_host)
            if not status['reachable'] or model not in status['installed_models']:
                raise ValueError('Start Ollama and download the selected model first (use its exact installed tag).')
            return model
        def complete(model):
            self.runtime.settings.model = model
            self.runtime.settings.setup_complete = True
            self.runtime.settings.save()
            # Wait until QThread has actually returned before closing the dialog.
            self.task.finished.connect(self.accept)
        self.launch_task(work, complete)

    def reject(self):
        if self.task and self.task.isRunning():
            self.note.setText('Wait for the current setup operation to finish before closing.')
            return
        super().reject()
