"""Quick-access AI, voice and performance controls; voice discovery runs off-thread."""
from PyQt6.QtWidgets import (QDialog, QWidget, QScrollArea, QVBoxLayout, QFormLayout, QComboBox,
                            QLineEdit, QCheckBox, QPushButton, QLabel, QMessageBox, QSpinBox, QDoubleSpinBox)
from ui.tasks import Task

class SettingsView(QDialog):
    def __init__(self, runtime, parent=None, section='general'):
        super().__init__(parent)
        self.runtime = runtime
        self.voice_task = None
        self.deferred_result = None
        self.setWindowTitle('GhostOS · ' + ('AI configuration' if section == 'ai' else 'Settings'))
        self.resize(650, 740)
        layout = QVBoxLayout(self)
        heading = QLabel('Make GhostOS yours')
        heading.setObjectName('hero')
        layout.addWidget(heading)
        body = QWidget()
        body_layout, form = QVBoxLayout(body), QFormLayout()
        form.setVerticalSpacing(13)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self.tier = QComboBox()
        self.tier.addItems(['Tier 1 · Confirm every action', 'Tier 2 · Confirm consequential input',
                            'Tier 3 · Auto-approve; UAC remains manual'])
        self.tier.setCurrentIndex(runtime.settings.tier - 1)
        form.addRow('Permissions', self.tier)
        self.model = QLineEdit(runtime.settings.model)
        form.addRow('Local vision model', self.model)
        self.browser = QComboBox()
        self.browser.addItems(['msedge', 'chrome'])
        self.browser.setCurrentText(runtime.settings.browser_channel)
        form.addRow('Browser', self.browser)
        self.cdp = QLineEdit(runtime.settings.cdp_url)
        self.cdp.setPlaceholderText('Optional: http://127.0.0.1:9222')
        form.addRow('Browser CDP', self.cdp)
        self.game = QCheckBox('Relative input and template polling')
        self.game.setChecked(runtime.settings.game_mode)
        form.addRow('Game mode', self.game)
        self.voice = QCheckBox('Microphone commands · pause to send')
        self.voice.setChecked(runtime.settings.voice_enabled)
        form.addRow('Voice input', self.voice)
        self.narrate = QCheckBox('Speak each action while working')
        self.narrate.setChecked(runtime.settings.narrate_actions)
        form.addRow('Narration', self.narrate)
        self.tts = QCheckBox('Speak the final task status')
        self.tts.setChecked(runtime.settings.tts_enabled)
        form.addRow('Completion audio', self.tts)
        self.voice_approval = QCheckBox('Listen for Yes / Approve only while permission is pending')
        self.voice_approval.setChecked(runtime.settings.voice_approval)
        form.addRow('Voice approvals', self.voice_approval)
        self.speech_engine = QComboBox()
        self.speech_engine.addItem('Piper · bundled offline neural voice', 'piper')
        self.speech_engine.addItem('Windows installed voice', 'sapi')
        self.speech_engine.setCurrentIndex(0 if runtime.settings.speech_engine == 'piper' else 1)
        form.addRow('Speech engine', self.speech_engine)
        self.speech_voice = QComboBox()
        self.speech_voice.addItem('Calm default · Zira when installed', '')
        if runtime.settings.speech_voice:
            self.speech_voice.addItem('Saved Windows voice', runtime.settings.speech_voice)
            self.speech_voice.setCurrentIndex(1)
        form.addRow('Voice', self.speech_voice)
        voices = QPushButton('Load installed Windows voices')
        voices.clicked.connect(self.load_voices)
        form.addRow('', voices)
        self.rate = QSpinBox()
        self.rate.setRange(120, 220)
        self.rate.setValue(runtime.settings.speech_rate)
        form.addRow('Speaking rate', self.rate)
        preview = QPushButton('Preview selected voice')
        preview.clicked.connect(self.preview_voice)
        form.addRow('', preview)
        self.silence = QDoubleSpinBox()
        self.silence.setRange(0.4, 2.5)
        self.silence.setSingleStep(0.1)
        self.silence.setValue(runtime.settings.vad_silence)
        self.silence.setSuffix(' seconds')
        form.addRow('Pause before sending', self.silence)
        self.width = QSpinBox()
        self.width.setRange(640, 1920)
        self.width.setSingleStep(128)
        self.width.setValue(runtime.settings.screenshot_width)
        form.addRow('Vision image width', self.width)
        self.output = QSpinBox()
        self.output.setRange(256, 2048)
        self.output.setSingleStep(128)
        self.output.setValue(runtime.settings.prediction_tokens)
        form.addRow('Output token budget', self.output)
        self.steps = QSpinBox()
        self.steps.setRange(0, 2147483647)
        self.steps.setSpecialValueText('Unlimited')
        self.steps.setValue(runtime.settings.max_steps)
        form.addRow('Task step limit', self.steps)
        self.runtime_limit = QSpinBox()
        self.runtime_limit.setRange(0, 2147483647)
        self.runtime_limit.setSpecialValueText('Unlimited')
        self.runtime_limit.setValue(runtime.settings.max_runtime)
        form.addRow('Runtime limit (seconds)', self.runtime_limit)
        ai_widgets = (self.tier, self.model, self.browser, self.cdp, self.game, self.width, self.output, self.steps, self.runtime_limit)
        for row in range(form.rowCount()):
            field = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if field and field.widget():
                form.setRowVisible(row, (field.widget() in ai_widgets) == (section == 'ai'))
        body_layout.addLayout(form)
        note = QLabel('Smaller images and shorter output reduce inference work.\nPiper speech is local and included in the Windows installer.\nStop the active task before changing model or control settings.')
        note.setWordWrap(True)
        body_layout.addWidget(note)
        label = QLabel(f'Phone dashboard · http://{runtime.local_ip}:{runtime.settings.web_port}\nPairing grants PC control. Use a trusted private network; HTTP is not encrypted.')
        label.setWordWrap(True)
        body_layout.addWidget(label)
        token = QLineEdit(runtime.token)
        token.setReadOnly(True)
        token.setEchoMode(QLineEdit.EchoMode.Password)
        body_layout.addWidget(token)
        show = QCheckBox('Show pairing token')
        show.toggled.connect(lambda checked: token.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        body_layout.addWidget(show)
        web = QPushButton('Start phone dashboard')
        web.clicked.connect(lambda: runtime.start_web())
        body_layout.addWidget(web)
        for widget in (label, token, show, web):
            widget.setVisible(section != 'ai')
        setup = QPushButton('Model and voice setup')
        setup.clicked.connect(self.open_setup)
        setup.setEnabled(not runtime.running)
        body_layout.addWidget(setup)
        body_layout.addStretch()
        self.note = QLabel('')
        layout.addWidget(self.note)
        save = QPushButton('Save settings')
        save.setObjectName('send')
        save.clicked.connect(self.save)
        save.setEnabled(not runtime.running)
        layout.addWidget(save)

    def preview_voice(self):
        from dataclasses import replace
        candidate = replace(self.runtime.settings, speech_voice=self.speech_voice.currentData(), speech_rate=self.rate.value())
        self.runtime.speech.say("Hello. I'm GhostOS. Ready when you are.", priority=True, settings=candidate)

    def load_voices(self):
        if self.voice_task and self.voice_task.isRunning():
            return
        from agent.voice import list_voices
        self.note.setText('Loading local Windows voices…')
        self.voice_task = Task(lambda progress: list_voices(), self)
        self.voice_task.result.connect(self.voices_loaded)
        self.voice_task.error.connect(self.note.setText)
        self.voice_task.finished.connect(self.voice_task_finished)
        self.voice_task.start()

    def voices_loaded(self, voices):
        current = self.speech_voice.currentData()
        self.speech_voice.clear()
        self.speech_voice.addItem('Calm default · Zira when installed', '')
        for voice in voices:
            self.speech_voice.addItem(voice['name'], voice['id'])
        index = self.speech_voice.findData(current)
        self.speech_voice.setCurrentIndex(max(0, index))
        self.note.setText('Choose a voice and a comfortable speaking rate.')

    def done(self, result):
        if self.voice_task and self.voice_task.isRunning():
            self.deferred_result = result
            self.note.setText('Finishing voice discovery…')
            return
        super().done(result)

    def voice_task_finished(self):
        if self.deferred_result is not None:
            super().done(self.deferred_result)

    def open_setup(self):
        from ui.setup_wizard import SetupWizard
        SetupWizard(self.runtime, self).exec()
        self.model.setText(self.runtime.settings.model)
        self.voice.setChecked(self.runtime.settings.voice_enabled)

    def save(self):
        if self.runtime.running:
            self.note.setText('Stop the active task before changing AI settings.')
            return
        from dataclasses import replace
        try:
            candidate = replace(self.runtime.settings, tier=self.tier.currentIndex() + 1,
                                model=self.model.text().strip(), cdp_url=self.cdp.text().strip(),
                                browser_channel=self.browser.currentText(),
                                game_mode=self.game.isChecked(), voice_enabled=self.voice.isChecked(),
                                narrate_actions=self.narrate.isChecked(), tts_enabled=self.tts.isChecked(),
                                speech_voice=self.speech_voice.currentData(), speech_rate=self.rate.value(),
                                speech_engine=self.speech_engine.currentData(), voice_approval=self.voice_approval.isChecked(),
                                max_runtime=self.runtime_limit.value(),
                                vad_silence=self.silence.value(), screenshot_width=self.width.value(),
                                prediction_tokens=self.output.value(), max_steps=self.steps.value())
            candidate.save()
            self.runtime.settings = candidate
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Could not save settings', str(exc))
            return
        self.accept()
