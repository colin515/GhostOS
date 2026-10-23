"""Offscreen UI regression coverage; no microphone, model or Windows input required."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
from types import SimpleNamespace
import pytest
pytest.importorskip('PyQt6')
from PyQt6.QtWidgets import QApplication
from agent.events import EventBus
from agent.safety import ApprovalBroker
from config import Settings


def fake_runtime(tmp_path):
    bus = EventBus()
    runtime = SimpleNamespace(settings=Settings(data_dir=tmp_path), running=False, bus=bus,
                              approvals=ApprovalBroker(bus), token='test-token', local_ip='127.0.0.1',
                              emergency_stopped=False, speech=SimpleNamespace(say=lambda *a, **kw: None, cancel=lambda: None),
                              stop=lambda: None, approve=lambda *a: None, preview_enabled=False)
    runtime.goals = []
    runtime.start = lambda goal: runtime.goals.append(goal)
    return runtime


def test_settings_is_adjacent_to_send_and_voice_submits_automatically(tmp_path):
    from ui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    runtime = fake_runtime(tmp_path)
    spoken = []
    runtime.speech.say = lambda text, **kw: spoken.append(text)
    window = MainWindow(runtime)
    window.show()
    app.processEvents()
    assert window.settings_button.parent() == window.send.parent()
    assert window.settings_button.geometry().right() < window.send.geometry().left()
    window.voice_task = SimpleNamespace(cancel=threading.Event(), isRunning=lambda: False)
    window.voice_result('Open Chrome and search for a powerbank')
    assert runtime.goals == ['Open Chrome and search for a powerbank']
    assert spoken == ['On it.']
    window.close()


def test_cancelled_voice_never_starts_a_goal(tmp_path):
    from ui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    runtime = fake_runtime(tmp_path)
    window = MainWindow(runtime)
    cancelled = threading.Event()
    cancelled.set()
    window.voice_task = SimpleNamespace(cancel=cancelled, isRunning=lambda: False)
    window.voice_result('Delete files')
    assert not runtime.goals
    window.close()
    app.processEvents()


def test_activity_labels_do_not_render_empty_start_and_stop_logs():
    from ui.trajectory_view import event_text
    assert event_text({'kind':'STARTED','goal':'Open Chrome'}) == 'Open Chrome'
    assert event_text({'kind':'STOP','message':'Emergency stop'}) == 'Emergency stop'
    assert event_text({'kind':'FINISHED','status':'GOAL_IMPOSSIBLE'}) == 'Goal impossible'
