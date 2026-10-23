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
    try:
        addresses = psutil.net_if_addrs()
        statistics = psutil.net_if_stats()
    except (OSError, psutil.Error):
        return '127.0.0.1'
    for name, addrs in addresses.items():
        stats = statistics.get(name)
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
        self._starting = False
        self._launch_thread = None
        self._launch_cancel = threading.Event()
        self._indicator = None
        self.preview_enabled = False
        self._manager = None
        self._stop = self._events = self._answers = None
        self._terminal_status = None
        self._web = self._web_thread = None
        self._capture_cancel = None
        self._closing = False
        self.emergency_stopped = False
        self.interactive_cli = True
        self._cli_prompt_thread = None
        self._voice_approval = None
        self._kill_switch = KillSwitch(self.stop)
        # Fresh per application launch, never placed in URLs/logs or embedded in the web page.
        self.token = secrets.token_urlsafe(32)
        token_file = settings.data_dir / 'dashboard-token.txt'
        token_file.write_text(self.token, encoding='utf-8')
        if os.name != 'nt':
            token_file.chmod(0o600)
        self.local_ip = local_ip()
        from agent.voice import SpeechService
        self.speech = SpeechService(lambda: self.settings, lambda message: self.bus.publish('ERROR', message=message))

    @property
    def running(self):
        # A read must not block Qt while multiprocessing starts in a background thread.
        return getattr(self, '_starting', False) or self._process is not None

    def __enter__(self):
        self._kill_switch.start()
        return self

    def start(self, goal=None, recipe=None):
        if not goal and not recipe:
            raise ValueError('Provide a goal or recipe')
        if goal and (not isinstance(goal, str) or len(goal) > 16000 or not goal.strip()):
            raise ValueError('Provide a nonempty goal of at most 16,000 characters')
        with self._lock:
            if self._closing:
                raise RuntimeError('Application is closing')
            if self.running:
                raise RuntimeError('An agent run is already active')
            self._starting = True
            self._launch_cancel = threading.Event()
            stamp = datetime.now(timezone.utc).strftime('run_%Y%m%d_%H%M%S_%f')
            self._terminal_status = None
            self.emergency_stopped = False
            self.approvals.clear()
            self.speech.cancel()
            self.bus.publish('STARTED', goal=goal or f'Recipe: {Path(recipe).name}', run=stamp)
            self._launch_thread = threading.Thread(target=self._launch,
                args=(goal, recipe, stamp, self._launch_cancel), daemon=True, name='GhostOS-launch')
            self._launch_thread.start()
        return stamp

    def _launch(self, goal, recipe, stamp, cancelled):
        process = indicator = None
        try:
            log_dir = self.settings.data_dir / 'logs' / stamp
            log_dir.mkdir()
            (log_dir / 'events.jsonl').write_text(json.dumps({'kind': 'STARTED', 'goal': goal or f'Recipe: {Path(recipe).name}', 'run': stamp}, ensure_ascii=False) + '\n', encoding='utf-8')
            if self._manager is None:
                self._manager = self.context.Manager()
            if cancelled.is_set():
                raise InterruptedError('Stopped before worker startup')
            # Includes CLI and remote-only runs, even while the main desktop is minimized.
            from ui.activity_border import ActivityIndicator
            indicator = ActivityIndicator(self.context)
            self._indicator = indicator
            indicator.start()
            if cancelled.is_set():
                raise InterruptedError('Stopped before worker startup')
            self._stop = self.context.Event()
            self._events = self._manager.Queue(maxsize=100)
            self._answers = self._manager.Queue(maxsize=20)
            process = self.context.Process(target=run_worker,
                args=(self.settings, goal, str(recipe) if recipe else None,
                      self._stop, self._events, self._answers), name='GhostOS-worker')
            self._process = process
            process.start()
            if cancelled.is_set():
                self.stop(reason='Stopped during startup')
            self._capture_cancel = threading.Event()
            threading.Thread(target=self._capture_live, args=(self._capture_cancel, log_dir), daemon=True).start()
            self._starting = False
            self._monitor = threading.Thread(target=self._supervise,
                args=(process, log_dir, indicator), daemon=True)
            self._monitor.start()
        except Exception as exc:
            if process and process.pid:
                from agent.processes import kill_tree
                kill_tree(process.pid)
            if indicator:
                indicator.close()
            self._process = None
            self._terminal_status = 'STOPPED' if cancelled.is_set() or isinstance(exc, InterruptedError) else 'ERROR'
            self._starting = False
            self.bus.publish('STATUS', status=self._terminal_status, message=str(exc))
            self.bus.publish('FINISHED', status=self._terminal_status)

    def _capture_live(self, cancel, log_dir):
        # Capture independently of Ollama/approval waits so the LAN feed stays live.
        from agent.vision import Vision
        vision = Vision(self.settings.screenshot_width)
        while not cancel.is_set():
            if not self._web and not self.preview_enabled:
                cancel.wait(self.settings.screenshot_interval)
                continue
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

    def _supervise(self, process, log_dir, indicator=None):
        started = time.monotonic()
        try:
            with (log_dir / 'events.jsonl').open('a', encoding='utf-8', buffering=1) as log:
                while True:
                    if indicator and not indicator.process.is_alive() and not self._stop.is_set():
                        self.stop(reason='Activity indicator stopped unexpectedly', status='INDICATOR_ERROR')
                    if self.settings.max_runtime and time.monotonic() - started > self.settings.max_runtime and not self._stop.is_set():
                        self.stop(reason='Maximum run time reached', status='MAX_RUNTIME_EXCEEDED')
                    try:
                        event = self._events.get(timeout=0.1)
                    except queue.Empty:
                        if not process.is_alive():
                            break
                        continue
                    kind = event.pop('kind')
                    if kind == 'WORKER_DONE':
                        break
                    if kind == 'APPROVAL':
                        self.approvals.create(event['request_id'], event['action'], event.get('target_window'))
                        if self.settings.voice_approval:
                            from agent.voice_approval import VoiceApproval
                            self.cancel_voice_approval()
                            self._voice_approval = VoiceApproval(self, event['request_id'])
                            self._voice_approval.start()
                        log.write(json.dumps(dict(kind=kind, **event), ensure_ascii=False) + '\n')
                    else:
                        if kind == 'APPROVAL_EXPIRED':
                            self.approvals.resolve(event['request_id'])
                            self.cancel_voice_approval()
                        if kind == 'EXECUTING' and self.settings.narrate_actions:
                            from agent.voice import action_narration
                            self.speech.say(action_narration(event['action']))
                        if kind == 'STATUS' and not self._stop.is_set():
                            self._terminal_status = event.get('status')
                        published = self.bus.publish(kind, **event)
                        if kind != 'FRAME':
                            log.write(json.dumps(published, ensure_ascii=False) + '\n')
                        elif self.settings.persist_screenshots:
                            import base64
                            (log_dir / f"frame_{published['id']:06d}.jpg").write_bytes(base64.b64decode(event['image']))
                process.join(timeout=2)
        except Exception as exc:
            self._terminal_status = 'ERROR'
            self._stop.set()
            self.bus.publish('ERROR', message=f'Worker supervision failed: {type(exc).__name__}: {exc}')
        finally:
            if process.is_alive():
                from agent.processes import kill_tree
                kill_tree(process.pid)
                process.join(timeout=1)
            if not self._terminal_status:
                self._terminal_status = 'STOPPED' if self._stop.is_set() else 'WORKER_CRASHED'
                self.bus.publish('STATUS', status=self._terminal_status)
            if self._stop.is_set() or self._terminal_status in ('ERROR', 'WORKER_CRASHED'):
                from agent.gaming_engine import release_inputs
                release_inputs()
            self.approvals.clear()
            self.cancel_voice_approval()
            if self._capture_cancel:
                self._capture_cancel.set()
            if indicator:
                indicator.close()
            terminal_status = self._terminal_status
            if self.settings.tts_enabled and terminal_status != 'STOPPED':
                self.speech.say(terminal_status.replace('_', ' ').capitalize() + '.')
            with self._lock:
                self._process = None
                self.bus.publish('FINISHED', status=terminal_status, logs=str(log_dir))

    def cancel_voice_approval(self):
        listener = getattr(self, '_voice_approval', None)
        if listener:
            listener.cancel.set()

    def approve(self, request_id, approved, source='button'):
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
                    from agent.window_focus import focus_window
                    focus_window(pending['target_window'], self._stop)
                    ctypes.windll.user32.AllowSetForegroundWindow(self._process.pid)
                except Exception:
                    approved = False
            self._answers.put_nowait({'id': request_id, 'approved': bool(approved)})
            self.cancel_voice_approval()
            self.bus.publish('APPROVAL_RESOLVED', request_id=request_id, approved=bool(approved), source=source)
            return True

    def stop(self, reason='Emergency stop', status='STOPPED'):
        with self._lock:
            self.emergency_stopped = True
            process = self._process
            if getattr(self, '_launch_cancel', None):
                self._launch_cancel.set()
            if self._stop is not None:
                self._stop.set()  # Brake before hiding the indicator or stopping child processes.
            if self._capture_cancel:
                self._capture_cancel.set()
            self._terminal_status = status
            self.approvals.clear()
        self.cancel_voice_approval()
        if getattr(self, '_indicator', None):
            self._indicator.request_stop()
        if getattr(self, 'speech', None):
            self.speech.cancel()
        if process is None:
            return
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
        if self._launch_thread:
            self._launch_thread.join(timeout=6)
        if self._monitor:
            self._monitor.join(timeout=4)
        self._kill_switch.close()
        self.speech.close()
        if self._indicator:
            self._indicator.close()
        if self._web:
            self._web.should_exit = True
        if self._web_thread:
            self._web_thread.join(timeout=3)
        if self._manager:
            self._manager.shutdown()
