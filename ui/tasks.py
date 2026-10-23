"""Qt tasks retain references in their owner until completion."""
from PyQt6.QtCore import QThread, pyqtSignal

class Task(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.progress.emit))
        except Exception as exc:
            self.error.emit(f'{type(exc).__name__}: {exc}')


class VoiceTask(Task):
    level = pyqtSignal(float)
    def __init__(self, settings, parent=None):
        import threading
        self.cancel = threading.Event()
        from agent.voice import record_and_transcribe
        super().__init__(lambda progress: record_and_transcribe(settings, progress, self.level.emit, self.cancel), parent)
