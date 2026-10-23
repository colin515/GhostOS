"""Safe smoke check: imports/resources only; never moves the mouse or starts Ollama."""
import importlib.util
import os
from config import VERSION, RESOURCE_DIR, dpi_scale


def diagnostics():
    modules = ('PyQt6', 'fastapi', 'uvicorn', 'ollama', 'playwright', 'cv2', 'PIL',
               'psutil', 'pynput', 'uiautomation', 'win32api', 'faster_whisper', 'pyttsx3')
    return {'version': VERSION, 'windows': os.name == 'nt', 'dpi_scale': dpi_scale(),
            'resources': {name: (RESOURCE_DIR / name).exists() for name in
                          ('docs/installation.md', 'ui/dashboard.html', 'shortcuts.json', 'VERSION')},
            'modules': {name: importlib.util.find_spec(name) is not None for name in modules}}
