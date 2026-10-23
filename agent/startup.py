"""Bootstrap error reporting and explicit second-launch activation; stdlib only."""
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
import traceback


def data_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'GhostOS'


def log_startup(message):
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('GhostOS.startup')
    handler = RotatingFileHandler(root / 'startup.log', maxBytes=512000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(message)
    finally:
        logger.removeHandler(handler)
        handler.close()


def guarded_main(function):
    try:
        log_startup('Launching ' + sys.executable)
        return function()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        try:
            log_startup(detail)
            location = str(data_root() / 'startup.log')
        except OSError:
            location = 'Startup log could not be written'
        message = f'GhostOS could not start: {type(exc).__name__}: {exc}\n\nDetails: {location}\n\nRun the latest installer to update or repair this installation.'
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        desktop_launch = len(sys.argv) == 1 or '--desktop' in sys.argv
        if os.name == 'nt' and desktop_launch:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'GhostOS startup error', 0x10)
        return 1


def request_show(root, timeout=2):
    """A second explicit desktop launch asks the first process to show its window."""
    path = Path(root) / 'show-window.request'
    path.write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8')
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if not path.exists():
            return True
        time.sleep(0.05)
    return False
