"""Non-activating controls stay available while the main chat is hidden."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
from ui.widgets import AudioVisualizer


class ControlPanel(QWidget):
    def __init__(self, stop, browser_help):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('GhostOS task controls')
        self.setFixedWidth(340)
        layout = QVBoxLayout(self)
        self.label = QLabel('GhostOS is working in the background')
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.wave = AudioVisualizer()
        layout.addWidget(self.wave)
        row = QHBoxLayout()
        self.help_button = QPushButton('CDP setup help')
        self.help_button.clicked.connect(browser_help)
        self.help_button.hide()
        row.addWidget(self.help_button)
        button = QPushButton('■ Stop')
        button.clicked.connect(stop)
        row.addWidget(button)
        layout.addLayout(row)
        for widget in self.findChildren(QPushButton):
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def showEvent(self, event):
        super().showEvent(event)
        from agent.window_focus import mark_ui
        mark_ui(int(self.winId()))
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 18, area.bottom() - self.height() - 18)
