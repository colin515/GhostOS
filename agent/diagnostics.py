"""Safe smoke check: imports/resources only; never moves the mouse or starts Ollama."""
import importlib
import importlib.util
import os
from config import VERSION, RESOURCE_DIR, dpi_scale


def diagnostics():
    modules = ('PyQt6.QtWidgets', 'fastapi', 'uvicorn', 'ollama', 'playwright', 'cv2', 'PIL',
               'psutil', 'webrtcvad', 'pynput', 'uiautomation', 'win32api', 'faster_whisper', 'pyttsx3')
    available, errors = {}, {}
    windows_only = {'pynput', 'uiautomation', 'win32api'}
    for name in modules:
        try:
            available[name] = importlib.util.find_spec(name) is not None
            if available[name] and (os.name == 'nt' or name not in windows_only):
                importlib.import_module(name)
        except Exception as exc:
            available[name] = False
            errors[name] = f'{type(exc).__name__}: {exc}'
    return {'version': VERSION, 'windows': os.name == 'nt', 'dpi_scale': dpi_scale(),
            'resources': {name: (RESOURCE_DIR / name).exists() for name in
                          ('docs/installation.md', 'ui/dashboard.html', 'shortcuts.json', 'VERSION')},
            'modules': available, 'import_errors': errors}
