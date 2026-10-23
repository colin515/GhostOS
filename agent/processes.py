"""Worker ownership and process-tree cleanup. No system-wide taskkill patterns."""
import os


def kill_tree(pid):
    import psutil
    try:
        root = psutil.Process(pid)
        descendants = root.children(recursive=True)
        for child in reversed(descendants):
            try:
                child.kill()
            except psutil.Error:
                pass
        try:
            root.kill()
        except psutil.Error:
            pass
        psutil.wait_procs(descendants + [root], timeout=1)
    except psutil.Error:
        pass


class ChildJob:
    def __init__(self, process):
        self.handle = None
        if os.name == 'nt':
            import win32job
            import win32api
            import win32con
            self.handle = win32job.CreateJobObject(None, None)
            info = win32job.QueryInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation)
            info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation, info)
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, process.pid)
            try:
                win32job.AssignProcessToJobObject(self.handle, handle)
            except Exception:
                # Fail closed: without ownership, do not let a command escape the stop control.
                kill_tree(process.pid)
                self.close()
                raise
            finally:
                handle.Close()

    def close(self):
        if self.handle:
            self.handle.Close()
            self.handle = None
