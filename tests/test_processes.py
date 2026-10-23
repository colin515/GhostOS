import sys
import os
from types import SimpleNamespace
from agent.processes import kill_tree, ChildJob


def test_kill_tree_handles_nonexistent_pid():
    # Attempting to kill non-existent PID (e.g. 99999999) catches psutil.NoSuchProcess / psutil.Error
    kill_tree(99999999)


def test_child_job_init_and_close(monkeypatch):
    class FakeHandle:
        def Close(self):
            pass

    win32job_mock = SimpleNamespace(
        CreateJobObject=lambda name, title: FakeHandle(),
        QueryInformationJobObject=lambda handle, info_class: {'BasicLimitInformation': {'LimitFlags': 0}},
        SetInformationJobObject=lambda handle, info_class, info: None,
        AssignProcessToJobObject=lambda handle, proc_handle: None,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=1,
        JobObjectExtendedLimitInformation=1,
    )
    win32api_mock = SimpleNamespace(
        OpenProcess=lambda access, inherit, pid: FakeHandle()
    )
    win32con_mock = SimpleNamespace(PROCESS_ALL_ACCESS=1)

    monkeypatch.setattr(os, 'name', 'nt')
    monkeypatch.setitem(sys.modules, 'win32job', win32job_mock)
    monkeypatch.setitem(sys.modules, 'win32api', win32api_mock)
    monkeypatch.setitem(sys.modules, 'win32con', win32con_mock)

    proc = SimpleNamespace(pid=12345)
    job = ChildJob(proc)
    assert job.handle is not None
    job.close()
    assert job.handle is None
