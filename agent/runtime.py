"""Parent supervisor shared by Qt, CLI and FastAPI; no UI automation on GUI threads."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
from agent.events import EventBus
from agent.safety import ApprovalBroker, KillSwitch
from agent.worker import run_worker


class InstanceLock:
    def __init__(self, root):
        self.root, self.file = root, None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = (self.root / 'runtime.lock').open('a+b')
        self.file.seek(0)
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError('Another GhostOS instance is already active') from exc
        return self

    def __exit__(self, *_):
        if self.file:
            self.file.close()


def local_ip():
    # No public network probe. Use the IPv4 interfaces reported by the OS.
    import psutil
    for name, addrs in psutil.net_if_addrs().items():
        stats = psutil.net_if_stats().get(name)
        if not stats or not stats.isup:
            continue
        for address in addrs:
            if address.family == socket.AF_INET and not address.address.startswith(('127.', '169.254.')):
                return address.address
    return '127.0.0.1'


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        for name in ('logs', 'templates', 'recipes'):
            (settings.data_dir / name).mkdir(exist_ok=True)
        self.bus = EventBus()
        self.approvals = ApprovalBroker(self.bus)
        self.context = mp.get_context('spawn')
        self._lock = threading.RLock()
        self._process = self._monitor = None
        self._manager = None
        self._stop = self._events = self._answers = None
        self._terminal_status = None
        self._web = self._web_thread = None
        self._capture_cancel = None
        self._closing = False
        self.emergency_stopped = False
        self.interactive_cli = True
        self._cli_prompt_thread = None
        self._kill_switch = KillSwitch(self.stop)
        # Fresh per application launch, never placed in URLs/logs or embedded in the web page.
        self.token = secrets.token_urlsafe(32)
        token_file = settings.data_dir / 'dashboard-token.txt'
        token_file.write_text(self.token, encoding='utf-8')
        if os.name != 'nt':
            token_file.chmod(0o600)
        self.local_ip = local_ip()

    @property
    def running(self):
        with self._lock:
            return self._process is not None

    def __enter__(self):
        self._kill_switch.start()
        return self

    def start(self, goal=None, recipe=None):
        if self._closing:
            raise RuntimeError('Application is closing')
        if not goal and not recipe:
            raise ValueError('Provide a goal or recipe')
        if goal and (not isinstance(goal, str) or len(goal) > 16000):
            raise ValueError('Goal is too long')
        with self._lock:
            if self._process is not None:
                raise RuntimeError('An agent run is already active')
            stamp = datetime.now(timezone.utc).strftime('run_%Y%m%d_%H%M%S_%f')
            log_dir = self.settings.data_dir / 'logs' / stamp
            log_dir.mkdir()
            self._terminal_status = None
            self.emergency_stopped = False
            self.approvals.clear()
            self._stop = self.context.Event()
            if self._manager is None:
                self._manager = self.context.Manager()
            # Manager queues remain intact when a worker is terminated mid-frame.
            self._events = self._manager.Queue(maxsize=100)
            self._answers = self._manager.Queue(maxsize=20)
            process = self.context.Process(target=run_worker,
                args=(self.settings, goal, str(recipe) if recipe else None,
                      self._stop, self._events, self._answers), name='GhostOS-worker')
            self._process = process
            try:
                process.start()
            except Exception:
                self._process = None
                raise
            self.bus.publish('STARTED', goal=goal or f'Recipe: {Path(recipe).name}', run=stamp)
            self._capture_cancel = threading.Event()
            capture = threading.Thread(target=self._capture_live, args=(self._capture_cancel, log_dir), daemon=True)
            capture.start()
            self._monitor = threading.Thread(target=self._supervise, args=(process, log_dir), daemon=True)
            self._monitor.start()
        return stamp

    def _capture_live(self, cancel, log_dir):
        # Capture independently of Ollama/approval waits so the LAN feed stays live.
        from agent.vision import Vision
        vision = Vision(self.settings.screenshot_width)
        while not cancel.is_set():
            try:
                frame = vision.capture()
                if cancel.is_set():
                    return
                event = self.bus.publish('FRAME', image=frame.base64(grid=not self.settings.game_mode))
                if self.settings.persist_screenshots:
                    (log_dir / f"live_{event['id']:06d}.jpg").write_bytes(frame.jpeg())
            except Exception:
                # Worker still reports capture errors; do not flood logs if the desktop locks.
                pass
            cancel.wait(self.settings.screenshot_interval)

    def _supervise(self, process, log_dir):
        started = time.monotonic()
        with (log_dir / 'events.jsonl').open('a', encoding='utf-8', buffering=1) as log:
            while True:
                if time.monotonic() - started > self.settings.max_runtime and not self._stop.is_set():
                    self._terminal_status = 'MAX_RUNTIME_EXCEEDED'
                    self.stop(reason='Maximum run time reached', status='MAX_RUNTIME_EXCEEDED')
                try:
                    event = self._events.get(timeout=0.1)
                except queue.Empty:
                    if not process.is_alive():
                        break
                    continue
                kind = event.pop('kind')
                if kind == 'WORKER_DONE':
                    # Worker closes queues/driver before process exit. Join is bounded below.
                    break
                if kind == 'APPROVAL':
                    self.approvals.create(event['request_id'], event['action'], event.get('target_window'))
                    log.write(json.dumps(dict(kind=kind, **event), ensure_ascii=False) + '\n')
                else:
                    if kind == 'APPROVAL_EXPIRED':
                        self.approvals.resolve(event['request_id'])
                    if kind == 'STATUS':
                        self._terminal_status = event.get('status')
                    published = self.bus.publish(kind, **event)
                    if kind != 'FRAME':
                        log.write(json.dumps(published, ensure_ascii=False) + '\n')
                    elif self.settings.persist_screenshots:
                        import base64
                        (log_dir / f"frame_{published['id']:06d}.jpg").write_bytes(base64.b64decode(event['image']))
            process.join(timeout=2)
            if process.is_alive():
                from agent.processes import kill_tree
                kill_tree(process.pid)
                process.join(timeout=1)
            if not self._terminal_status:
                self._terminal_status = 'STOPPED' if self._stop.is_set() else 'WORKER_CRASHED'
                self.bus.publish('STATUS', status=self._terminal_status)
            self.approvals.clear()
            if self._capture_cancel:
                self._capture_cancel.set()
            terminal_status = self._terminal_status
            with self._lock:
                self._process = None
            self.bus.publish('FINISHED', status=terminal_status, logs=str(log_dir))

    def approve(self, request_id, approved):
        with self._lock:
            if not self._process or self._stop.is_set():
                return False
            pending = self.approvals.resolve(request_id)
            if not pending:
                return False
            if time.monotonic() - pending['created'] >= self.settings.approval_timeout:
                return False
            if approved and pending.get('target_window') and os.name == 'nt':
                import win32gui
                import ctypes
                try:
                    win32gui.SetForegroundWindow(pending['target_window'])
                    ctypes.windll.user32.AllowSetForegroundWindow(self._process.pid)
                except Exception:
                    approved = False
            self._answers.put_nowait({'id': request_id, 'approved': bool(approved)})
            self.bus.publish('APPROVAL_RESOLVED', request_id=request_id, approved=bool(approved))
            return True

    def stop(self, reason='Emergency stop', status='STOPPED'):
        # Set the brake first, then terminate only our worker/descendants. Never kill an external Ollama.
        with self._lock:
            self.emergency_stopped = True
            process = self._process
            if process is None:
                return
            self._stop.set()
            if self._capture_cancel:
                self._capture_cancel.set()
            self._terminal_status = status
            self.approvals.clear()
        self.bus.publish('STOP', message=reason)
        if process.pid:
            from agent.processes import kill_tree
            kill_tree(process.pid)
        from agent.gaming_engine import release_inputs
        release_inputs()

    def start_web(self):
        if self._web:
            return
        import uvicorn
        from agent.web_dashboard import create_app
        self._web = uvicorn.Server(uvicorn.Config(create_app(self), host=self.settings.web_host,
                                  port=self.settings.web_port, log_level='warning', access_log=False, proxy_headers=False))
        server = self._web
        def serve():
            try:
                server.run()
            except (Exception, SystemExit) as exc:
                self.bus.publish('ERROR', message=f'Dashboard failed to start: {exc}')
            finally:
                self._web = None
        self._web_thread = threading.Thread(target=serve, daemon=True)
        self._web_thread.start()
        self.bus.publish('SERVER', message=f'Starting dashboard on {self.local_ip}:{self.settings.web_port}')

    def _cli_events(self, cursor):
        for event in self.bus.after(cursor):
            cursor = event['id']
            print(json.dumps(event, ensure_ascii=False), flush=True)
        return cursor

    def _cli_approve(self):
        import sys
        for request in self.approvals.pending():
            if not self.interactive_cli or sys.stdin is None or not sys.stdin.isatty():
                self.approve(request['id'], False)
                continue
            if self._cli_prompt_thread and self._cli_prompt_thread.is_alive():
                return
            def prompt(request=request):
                print(json.dumps(request['action'], indent=2))
                try:
                    answer = input('Approve this action? [y/N] ').lower() == 'y'
                except (EOFError, OSError):
                    answer = False
                self.approve(request['id'], answer)
            # A pending console read must not block cancellation or timeout handling.
            self._cli_prompt_thread = threading.Thread(target=prompt, daemon=True)
            self._cli_prompt_thread.start()

    def run_cli(self, goal=None, recipe=None):
        self.start(goal, recipe)
        cursor = 0
        while self.running:
            cursor = self._cli_events(cursor)
            self._cli_approve()
            time.sleep(0.1)
        self._cli_events(cursor)
        return 0 if self._terminal_status in ('GOAL_SATISFIED', 'RECIPE_COMPLETED', 'COMMAND_COMPLETED') else 1

    def wait_cli(self):
        cursor = 0
        while True:
            cursor = self._cli_events(cursor)
            if self._web_thread and not self._web_thread.is_alive():
                raise RuntimeError('Dashboard server stopped; check the error log or port availability')
            if not self._web:
                self._cli_approve()
            time.sleep(0.2)

    def __exit__(self, *_):
        self._closing = True
        self.stop(reason='Application closing')
        if self._monitor:
            self._monitor.join(timeout=4)
        self._kill_switch.close()
        if self._web:
            self._web.should_exit = True
        if self._web_thread:
            self._web_thread.join(timeout=3)
        if self._manager:
            self._manager.shutdown()
