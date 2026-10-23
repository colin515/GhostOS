"""No desktop I/O: exercise asynchronous first-run dialog completion offscreen."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from types import SimpleNamespace
import pytest
pytest.importorskip('PyQt6')
from PyQt6.QtWidgets import QApplication
from config import Settings


def spin_until(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Qt task did not complete')


def test_setup_save_closes_after_background_task(monkeypatch, tmp_path):
    import ui.setup_wizard as wizard
    monkeypatch.setattr('agent.brain.local_model_metadata', lambda host, model: {'capabilities': ['vision']})
    monkeypatch.setattr(wizard, 'hardware_report', lambda: {'recommended_model': 'qwen2.5vl:7b', 'model_note': 'test'})
    monkeypatch.setattr(wizard, 'ollama_status', lambda host: {'reachable': True, 'installed_models': ['qwen2.5vl:7b']})
    app = QApplication.instance() or QApplication([])
    runtime = SimpleNamespace(settings=Settings(data_dir=tmp_path), local_ip='127.0.0.1')
    dialog = wizard.SetupWizard(runtime)
    spin_until(app, lambda: dialog.done.isEnabled())
    dialog.save()
    spin_until(app, lambda: dialog.result() == 1)
    assert runtime.settings.setup_complete
    assert Settings.load(tmp_path).setup_complete


def test_setup_refuses_remote_model_before_marking_complete(monkeypatch, tmp_path):
    import ui.setup_wizard as wizard
    monkeypatch.setattr(wizard, 'hardware_report', lambda: {'recommended_model': 'llava:7b', 'model_note': 'test'})
    monkeypatch.setattr(wizard, 'ollama_status', lambda host: {'reachable': True, 'installed_models': ['llava:7b']})
    monkeypatch.setattr('agent.brain.local_model_metadata', lambda *args: {'remote_host': 'https://ollama.com', 'capabilities': ['vision']})
    app = QApplication.instance() or QApplication([])
    runtime = SimpleNamespace(settings=Settings(data_dir=tmp_path), local_ip='127.0.0.1')
    dialog = wizard.SetupWizard(runtime)
    spin_until(app, lambda: dialog.done.isEnabled())
    dialog.save()
    spin_until(app, lambda: dialog.done.isEnabled() and 'Cloud/remote' in dialog.note.text())
    assert not runtime.settings.setup_complete
    assert not (tmp_path / 'settings.json').exists()
    dialog.reject()


def test_setup_benchmark_is_available_and_runs_in_background(monkeypatch, tmp_path):
    import ui.setup_wizard as wizard
    monkeypatch.setattr(wizard, 'hardware_report', lambda: {'recommended_model': 'llava:7b', 'model_note': 'test'})
    monkeypatch.setattr(wizard, 'ollama_status', lambda host: {'reachable': True, 'installed_models': ['llava:7b']})
    monkeypatch.setattr(wizard, 'benchmark_model', lambda settings, model, progress: {'tokens_per_second': 10})
    app = QApplication.instance() or QApplication([])
    runtime = SimpleNamespace(settings=Settings(data_dir=tmp_path), local_ip='127.0.0.1')
    dialog = wizard.SetupWizard(runtime)
    spin_until(app, lambda: dialog.benchmark.isEnabled())
    dialog.benchmark.click()
    spin_until(app, lambda: dialog.done.isEnabled() and 'tokens_per_second' in dialog.report.toPlainText())
    assert not runtime.settings.setup_complete
    dialog.reject()
