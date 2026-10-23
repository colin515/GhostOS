from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
                            QCheckBox, QPushButton, QLabel, QMessageBox, QSpinBox)

class SettingsView(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.setWindowTitle('Agent settings')
        self.resize(600, 560)
        layout, form = QVBoxLayout(self), QFormLayout()
        self.tier = QComboBox()
        self.tier.addItems(['Tier 1 · Confirm every action', 'Tier 2 · Confirm consequential or ambiguous input',
                            'Tier 3 · Auto-approve actions; Windows UAC remains manual'])
        self.tier.setCurrentIndex(runtime.settings.tier - 1)
        form.addRow('Permissions', self.tier)
        self.model = QLineEdit(runtime.settings.model)
        form.addRow('Ollama model', self.model)
        self.cdp = QLineEdit(runtime.settings.cdp_url)
        self.cdp.setPlaceholderText('Optional: http://127.0.0.1:9222')
        form.addRow('Browser CDP', self.cdp)
        self.game = QCheckBox('Use relative game input and template polling')
        self.game.setChecked(runtime.settings.game_mode)
        form.addRow('Game mode', self.game)
        self.voice = QCheckBox('Enable microphone (download model via setup)')
        self.voice.setChecked(runtime.settings.voice_enabled)
        form.addRow('Voice', self.voice)
        self.tts = QCheckBox('Speak terminal status')
        self.tts.setChecked(runtime.settings.tts_enabled)
        form.addRow('Speech', self.tts)
        self.steps = QSpinBox()
        self.steps.setRange(1, 1000)
        self.steps.setValue(runtime.settings.max_steps)
        form.addRow('Step limit', self.steps)
        layout.addLayout(form)
        label = QLabel('Pairing grants control of this PC. Use a trusted private network.\nHTTP does not encrypt local traffic. Keep Windows Firewall on the Private profile.')
        label.setWordWrap(True)
        layout.addWidget(label)
        token = QLineEdit(runtime.token)
        token.setReadOnly(True)
        token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(token)
        show = QCheckBox('Show pairing token')
        show.toggled.connect(lambda checked: token.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        layout.addWidget(show)
        web = QPushButton(f'Start dashboard · http://{runtime.local_ip}:{runtime.settings.web_port}')
        web.clicked.connect(runtime.start_web)
        layout.addWidget(web)
        setup = QPushButton('Open model and voice setup')
        setup.clicked.connect(self.open_setup)
        layout.addWidget(setup)
        save = QPushButton('Save settings')
        save.clicked.connect(self.save)
        save.setEnabled(not runtime.running)
        setup.setEnabled(not runtime.running)
        layout.addWidget(save)

    def open_setup(self):
        from ui.setup_wizard import SetupWizard
        SetupWizard(self.runtime, self).exec()
        self.model.setText(self.runtime.settings.model)
        self.voice.setChecked(self.runtime.settings.voice_enabled)

    def save(self):
        if self.runtime.running:
            QMessageBox.warning(self, 'Agent running', 'Stop the run before changing settings.')
            return
        from dataclasses import replace
        try:
            candidate = replace(self.runtime.settings, tier=self.tier.currentIndex() + 1,
                                model=self.model.text().strip(), cdp_url=self.cdp.text().strip(),
                                game_mode=self.game.isChecked(), voice_enabled=self.voice.isChecked(),
                                tts_enabled=self.tts.isChecked(), max_steps=self.steps.value())
            candidate.save()
            self.runtime.settings = candidate
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid settings', str(exc))
            return
        self.accept()
