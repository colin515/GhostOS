from types import SimpleNamespace
import pytest
from agent.processes import kill_tree, ChildJob


def test_kill_tree_handles_nonexistent_pid():
    # Attempting to kill non-existent PID (e.g. 99999999) catches psutil.NoSuchProcess / psutil.Error
    kill_tree(99999999)


def test_child_job_init_and_close():
    proc = SimpleNamespace(pid=12345)
    # ChildJob creates Win32 Job object if os.name == 'nt', on non-Windows it handles cleanly
    job = ChildJob(proc)
    job.close()
    assert job.handle is None
