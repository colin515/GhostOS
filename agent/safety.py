"""Permissions are derived from action semantics, never a model-provided risk label."""
from __future__ import annotations
import threading
import time
import uuid
from agent.models import Action

NAVIGATION_KEYS = {
    ('ctrl', 'l'), ('ctrl', 't'), ('alt', 'tab'), ('ctrl', 'a'),
    ('ctrl', 'c'), ('tab',), ('esc',), ('up',), ('down',), ('left',), ('right',),
    ('pageup',), ('pagedown',), ('win', 'r'),
}


def requires_approval(action: Action, tier: int) -> bool:
    if tier == 1:
        return True
    if tier == 3:
        return False
    if action.kind in ('wait', 'focus', 'browser_navigate', 'browser_snapshot', 'game_move'):
        return False
    if action.kind == 'hotkey':
        return tuple(k.lower() for k in action.args['keys']) not in NAVIGATION_KEYS
    if action.kind == 'open_app':
        return False  # Only entries from packaged, read-only shortcuts.json.
    # A click or Enter can submit a form/delete a file. Treat ambiguous input as consequential.
    return True


class ApprovalBroker:
    def __init__(self, bus):
        self.bus = bus
        self._lock = threading.Lock()
        self._pending = {}

    def create(self, request_id, action, target_window=None):
        with self._lock:
            self._pending[request_id] = dict(id=request_id, action=action, target_window=target_window, created=time.monotonic())
        self.bus.publish('APPROVAL', request_id=request_id, action=action)

    def resolve(self, request_id):
        with self._lock:
            return self._pending.pop(request_id, None)

    def pending(self):
        with self._lock:
            return list(self._pending.values())

    def clear(self):
        with self._lock:
            self._pending.clear()


class WorkerSafety:
    def __init__(self, settings, stop_event, event_queue, answers):
        self.settings, self.stop, self.events, self.answers = settings, stop_event, event_queue, answers

    def check(self):
        if self.stop.is_set():
            raise InterruptedError('Emergency stop')

    def authorize(self, action):
        import queue
        self.check()
        if not requires_approval(action, self.settings.tier):
            return
        request = uuid.uuid4().hex
        import os
        target_window = None
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
            target_window = ctypes.windll.user32.GetForegroundWindow()
        self.events.put({'kind': 'APPROVAL', 'request_id': request, 'action': action.model_dump(),
                         'target_window': target_window})
        deadline = time.monotonic() + self.settings.approval_timeout
        while time.monotonic() < deadline:
            self.check()
            try:
                reply = self.answers.get(timeout=0.1)
            except queue.Empty:
                continue
            if reply['id'] == request:
                if not reply['approved']:
                    raise PermissionError('Action declined')
                if target_window:
                    import win32gui
                    if win32gui.GetForegroundWindow() != target_window:
                        raise PermissionError('Target window changed during approval. Restore it and retry the goal.')
                return
        self.events.put({'kind': 'APPROVAL_EXPIRED', 'request_id': request})
        raise PermissionError('Approval timed out; no action executed')


class KillSwitch:
    def __init__(self, callback):
        self.callback, self.listener = callback, None

    def start(self):
        from pynput.keyboard import GlobalHotKeys
        self.listener = GlobalHotKeys({'<ctrl>+<alt>+k': self.callback,
                                      '<ctrl>+<alt>+<esc>': self.callback})
        self.listener.start()
        self.listener.wait()

    def close(self):
        if self.listener:
            self.listener.stop()
