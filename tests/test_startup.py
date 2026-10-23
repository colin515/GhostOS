from pathlib import Path
import threading
import time
from agent.startup import guarded_main, request_show
from agent.runtime import InstanceLock, AlreadyRunning
import pytest


def test_stale_lock_file_does_not_prevent_startup(tmp_path):
    (tmp_path / 'runtime.lock').write_text('0')
    with InstanceLock(tmp_path):
        with pytest.raises(AlreadyRunning):
            with InstanceLock(tmp_path):
                pass
    with InstanceLock(tmp_path):
        pass


def test_second_launch_gets_existing_window_acknowledgment(tmp_path):
    def existing():
        request = tmp_path / 'show-window.request'
        until = time.monotonic() + 2
        while time.monotonic() < until:
            if request.exists():
                request.unlink()
                return
            time.sleep(0.01)
    thread = threading.Thread(target=existing)
    thread.start()
    assert request_show(tmp_path, timeout=2)
    thread.join(2)
    assert not request_show(tmp_path, timeout=0.05)  # Headless or unresponsive instance.


def test_startup_import_failure_writes_a_readable_log(monkeypatch, tmp_path):
    import agent.startup as startup
    monkeypatch.setattr(startup, 'data_root', lambda: Path(tmp_path))
    monkeypatch.setattr('sys.argv', ['GhostOS.exe','--diagnostics'])
    def broken():
        raise ImportError('missing application module')
    assert guarded_main(broken) == 1
    text = (tmp_path / 'startup.log').read_text()
    assert 'missing application module' in text and 'Traceback' in text
