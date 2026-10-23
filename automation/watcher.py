"""Debounced directory triggers; busy runs are coalesced, never overlapped."""
from pathlib import Path
import queue
import time


def watch(directory, recipe, runtime, debounce=1.0):
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    from automation.recipe_parser import load_recipe
    directory, recipe = Path(directory).resolve(strict=True), Path(recipe).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('Watch target must be a directory')
    load_recipe(recipe)
    if directory == runtime.settings.data_dir or directory in runtime.settings.data_dir.parents:
        raise ValueError('Watch directory must not contain GhostOS application data/logs')
    changes = queue.Queue(maxsize=1)
    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory or event.event_type not in ('created', 'modified', 'moved', 'deleted'):
                return
            try:
                changes.put_nowait(time.monotonic())
            except queue.Full:
                pass
    observer = Observer()
    observer.schedule(Handler(), str(directory), recursive=True)
    observer.start()
    runtime.bus.publish('WATCHING', message=str(directory))
    pending_at = None
    try:
        while True:
            try:
                pending_at = changes.get(timeout=0.1)
            except queue.Empty:
                pass
            if runtime.emergency_stopped:
                pending_at = None
                continue
            if pending_at and time.monotonic() - pending_at >= debounce and not runtime.running:
                runtime.start(recipe=recipe)
                pending_at = None
            if runtime._web is None:
                runtime._cli_approve()
    finally:
        observer.stop()
        observer.join(timeout=3)
