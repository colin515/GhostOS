"""First-launch hardware scan and explicit model/voice download approval."""
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QLabel, QPushButton,
                            QTextEdit, QVBoxLayout, QHBoxLayout)
from ui.tasks import Task
from agent.hardware import hardware_report, ollama_status, benchmark_model
from setup import MODELS, download_model, download_voice
from agent.model_setup import verify_model

class SetupWizard(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime, self.task = runtime, None
        self.accept_after_task = False
        self.setWindowTitle('Welcome to GhostOS')
        self.resize(650, 630)
        layout = QVBoxLayout(self)
        title = QLabel('Set up your local agent')
        title.setObjectName('hero')
        layout.addWidget(title)
        intro = QLabel('For an 8 GB GPU, use qwen3.5:4b; qwen3-vl:4b is an alternative. Update Ollama first.\nDownload, verify the agent protocol, then save. All inference stays local.')
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
        self.benchmark = QPushButton('Benchmark selected model')
        self.verify = QPushButton('Verify agent model · no desktop input')
        layout.addWidget(self.verify)
        layout.addWidget(self.benchmark)
        self.done = QPushButton('Save and continue')
        buttons.addWidget(self.scan)
        buttons.addWidget(self.pull)
        buttons.addWidget(self.done)
        layout.addLayout(buttons)
        self.scan.clicked.connect(self.inspect)
        self.pull.clicked.connect(self.download)
        self.done.clicked.connect(self.save)
        self.benchmark.clicked.connect(self.run_benchmark)
        self.verify.clicked.connect(self.run_verification)
        self.inspect()

    def busy(self, yes):
        for button in (self.scan, self.pull, self.done, self.benchmark, self.verify):
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
        self.task.finished.connect(self.task_finished)
        self.task.start()

    def task_finished(self):
        self.busy(False)
        if self.accept_after_task:
            self.accept()

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
            if voice_ready:
                settings.voice_enabled = True
            self.note.setText('Download complete. Verify agent model, or Save and continue to verify and activate it.')
        self.launch_task(work, complete)

    def run_verification(self):
        model = self.model.currentText().strip()
        def complete(report):
            import json
            self.report.setPlainText(json.dumps(report, indent=2))
            self.note.setText('Agent protocol passed. Click Save and continue to use this model.')
        self.launch_task(lambda progress: verify_model(self.runtime.settings, model, progress), complete)

    def run_benchmark(self):
        model = self.model.currentText().strip()
        def complete(report):
            import json
            self.report.setPlainText(json.dumps(report, indent=2))
            self.note.setText('Benchmark complete. Save and continue when ready.')
        self.launch_task(lambda progress: benchmark_model(self.runtime.settings, model, progress), complete)

    def save(self):
        model = self.model.currentText().strip()
        def work(progress):
            status = ollama_status(self.runtime.settings.ollama_host)
            if not status['reachable'] or model not in status['installed_models']:
                raise ValueError('Start Ollama and download the selected model first (use its exact installed tag).')
            from agent.brain import ensure_local_vision, local_model_metadata
            ensure_local_vision(local_model_metadata(self.runtime.settings.ollama_host, model))
            verify_model(self.runtime.settings, model, progress)
            return model
        def complete(model):
            self.runtime.settings.model = model
            self.runtime.settings.setup_complete = True
            self.runtime.settings.save()
            # Wait until QThread has actually returned before closing the dialog.
            self.accept_after_task = True
        self.launch_task(work, complete)

    def reject(self):
        if self.task and self.task.isRunning():
            self.note.setText('Wait for the current setup operation to finish before closing.')
            return
        super().reject()
