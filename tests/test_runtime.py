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
