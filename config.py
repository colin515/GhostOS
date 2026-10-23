"""Version, resource paths and per-user writable settings."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import ctypes
import json
import os
from pathlib import Path
import sys

RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
VERSION = (RESOURCE_DIR / 'VERSION').read_text(encoding='utf-8').strip()


def user_data_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'GhostOS'


def enable_dpi_awareness() -> None:
    if os.name == 'nt':
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)


def dpi_scale() -> float:
    if os.name != 'nt':
        return 1.0
    return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0


@dataclass
class Settings:
    tier: int = 2
    model: str = 'qwen2.5vl:7b'
    ollama_host: str = 'http://127.0.0.1:11434'
    web_host: str = '0.0.0.0'
    web_port: int = 8000
    game_mode: bool = False
    game_poll_hz: int = 10
    vision_interval: float = 3.0
    max_steps: int = 40
    max_runtime: int = 600
    approval_timeout: int = 120
    screenshot_width: int = 1280
    screenshot_interval: float = 0.75
    persist_screenshots: bool = False
    setup_complete: bool = False
    voice_enabled: bool = False
    tts_enabled: bool = False
    whisper_model: str = 'base'
    cdp_url: str = ''
    data_dir: Path = field(default_factory=user_data_dir)

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        if self.tier not in (1, 2, 3):
            raise ValueError('Permission tier must be 1, 2 or 3')
        if not (1 <= self.web_port <= 65535 and 1 <= self.max_steps <= 1000):
            raise ValueError('Invalid port or step budget')
        if not (1 <= self.game_poll_hz <= 30 and 320 <= self.screenshot_width <= 3840):
            raise ValueError('Invalid capture settings')
        if not (1 <= self.max_runtime <= 7200 and 1 <= self.approval_timeout <= 600):
            raise ValueError('Invalid runtime/approval time limit')
        if not (0.1 <= self.screenshot_interval <= 10 and 0.1 <= self.vision_interval <= 30):
            raise ValueError('Invalid polling intervals')
        if not self.model.strip():
            raise ValueError('Choose a model')
        from urllib.parse import urlparse
        for address in (self.ollama_host, self.cdp_url):
            if address and urlparse(address).hostname not in ('localhost', '127.0.0.1', '::1'):
                raise ValueError('Ollama and CDP endpoints must be loopback addresses')

    @classmethod
    def load(cls, data_dir: Path | None = None) -> 'Settings':
        root = data_dir or user_data_dir()
        path = root / 'settings.json'
        if not path.exists():
            return cls(data_dir=root)
        raw = json.loads(path.read_text(encoding='utf-8'))
        raw['data_dir'] = root
        return cls(**raw)

    def save(self) -> None:
        self.__post_init__()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.pop('data_dir')
        path = self.data_dir / 'settings.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        temporary.replace(path)
