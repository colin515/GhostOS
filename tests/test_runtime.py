import queue
import threading
from types import SimpleNamespace
from agent.events import EventBus
from agent.runtime import Runtime
from agent.safety import ApprovalBroker
from config import Settings


def test_stop_cancels_worker_owned_tree_and_inputs(monkeypatch):
    import agent.processes
    import agent.gaming_engine
    killed, released = [], []
    monkeypatch.setattr(agent.processes, 'kill_tree', lambda pid: killed.append(pid))
    monkeypatch.setattr(agent.gaming_engine, 'release_inputs', lambda: released.append(True))
    runtime = Runtime.__new__(Runtime)
    runtime._lock = threading.RLock()
    runtime.bus = EventBus()
    runtime.approvals = ApprovalBroker(runtime.bus)
    runtime.approvals.create('pending', {'kind': 'focus'})
    runtime._process = SimpleNamespace(pid=12345)
    runtime._stop = threading.Event()
    runtime._capture_cancel = threading.Event()
    runtime.stop()
    assert runtime._stop.is_set()
    assert runtime._capture_cancel.is_set()
    assert runtime._terminal_status == 'STOPPED'
    assert runtime.emergency_stopped
    assert not runtime.approvals.pending()
    assert killed == [12345]
    assert released == [True]


def test_noninteractive_console_denies_instead_of_waiting(monkeypatch):
    runtime = Runtime.__new__(Runtime)
    runtime.interactive_cli = False
    runtime.bus = EventBus()
    runtime.approvals = ApprovalBroker(runtime.bus)
    runtime.approvals.create('pending', {'kind': 'focus'})
    answers = []
    runtime.approve = lambda rid, approved: answers.append((rid, approved))
    runtime._cli_approve()
    assert answers == [('pending', False)]


def test_shell_job_failure_still_cleans_up_process(monkeypatch, tmp_path):
    import subprocess
    import agent.processes
    from agent.controller import Controller
    from agent.safety import WorkerSafety
    monkeypatch.setenv('SystemRoot', str(tmp_path))
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kw: SimpleNamespace(pid=12345))
    killed = []
    monkeypatch.setattr(agent.processes, 'kill_tree', lambda pid: killed.append(pid))
    def broken_job(process):
        raise RuntimeError('Cannot own this process')
    monkeypatch.setattr(agent.processes, 'ChildJob', broken_job)
    controller = Controller.__new__(Controller)
    controller.settings = Settings(data_dir=tmp_path)
    controller.safety = WorkerSafety(SimpleNamespace(tier=3), threading.Event(), queue.Queue(), queue.Queue())
    import pytest
    with pytest.raises(RuntimeError, match='Cannot own'):
        controller.shell('Write-Output hello', 2)
    assert killed == [12345]
    assert controller.process is None


def test_start_is_nonblocking_and_stop_during_setup_prevents_worker(monkeypatch, tmp_path):
    import time
    runtime = Runtime(Settings(data_dir=tmp_path))
    entered, release = threading.Event(), threading.Event()
    def manager():
        entered.set()
        release.wait(3)
        return object()
    runtime.context = SimpleNamespace(Manager=manager)
    started = time.monotonic()
    runtime.start('Open Chrome')
    assert time.monotonic() - started < 0.5
    assert entered.wait(1)
    assert runtime.running
    import pytest
    with pytest.raises(RuntimeError, match='already active'):
        runtime.start('Another task')
    runtime.stop()
    release.set()
    runtime._launch_thread.join(2)
    assert not runtime.running
    assert runtime._terminal_status == 'STOPPED'
    assert any(event.get('goal') == 'Open Chrome' for event in runtime.bus.after())
    runtime.speech.close()


def test_network_inventory_failure_does_not_prevent_desktop_start(monkeypatch):
    from agent.runtime import local_ip
    import psutil
    monkeypatch.setattr(psutil, 'net_if_addrs', lambda: (_ for _ in ()).throw(PermissionError('restricted')))
    assert local_ip() == '127.0.0.1'


def test_supervisor_log_error_still_stops_worker_and_hides_indicator(monkeypatch, tmp_path):
    import agent.processes
    import agent.gaming_engine
    killed = []
    monkeypatch.setattr(agent.processes, 'kill_tree', lambda pid: killed.append(pid))
    monkeypatch.setattr(agent.gaming_engine, 'release_inputs', lambda: None)
    runtime = Runtime(Settings(data_dir=tmp_path))
    runtime._stop = threading.Event()
    process = SimpleNamespace(pid=456, is_alive=lambda: True, join=lambda **kw: None)
    closed = []
    indicator = SimpleNamespace(close=lambda: closed.append(True))
    runtime._process = process
    # Missing parent directory produces a real logging failure before the event loop.
    runtime._supervise(process, tmp_path / 'missing', indicator)
    assert not runtime.running
    assert runtime._stop.is_set()
    assert runtime._terminal_status == 'ERROR'
    assert killed == [456]
    assert closed == [True]
    assert any(event['kind'] == 'FINISHED' for event in runtime.bus.after())
    runtime.speech.close()


def test_indicator_start_failure_prevents_automation(monkeypatch, tmp_path):
    import ui.activity_border
    runtime = Runtime(Settings(data_dir=tmp_path))
    runtime.context = SimpleNamespace(Manager=lambda: object())
    cleaned = []
    class BrokenIndicator:
        def __init__(self, context):
            pass
        def start(self):
            raise RuntimeError('Indicator could not start')
        def close(self):
            cleaned.append(True)
    monkeypatch.setattr(ui.activity_border, 'ActivityIndicator', BrokenIndicator)
    runtime.start('Open Chrome')
    runtime._launch_thread.join(2)
    assert not runtime.running
    assert runtime._process is None
    assert runtime._terminal_status == 'ERROR'
    assert cleaned == [True]
    runtime.speech.close()
