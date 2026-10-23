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
    max_steps: int = 0
    max_runtime: int = 0
    approval_timeout: int = 120
    screenshot_width: int = 1024
    screenshot_interval: float = 0.75
    persist_screenshots: bool = False
    setup_complete: bool = False
    voice_enabled: bool = False
    tts_enabled: bool = False
    whisper_model: str = 'base'
    narrate_actions: bool = False
    startup_notice: str = field(default='', repr=False, compare=False)
    settings_version: int = 2
    voice_approval: bool = False
    speech_engine: str = 'piper'
    speech_voice: str = ''
    speech_rate: int = 160
    speech_volume: float = 0.85
    vad_silence: float = 0.9
    voice_max_seconds: int = 45
    context_tokens: int = 8192
    prediction_tokens: int = 512
    browser_channel: str = 'msedge'
    cdp_url: str = ''
    data_dir: Path = field(default_factory=user_data_dir)

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        if self.tier not in (1, 2, 3):
            raise ValueError('Permission tier must be 1, 2 or 3')
        if not (1 <= self.web_port <= 65535 and 0 <= self.max_steps <= 2147483647):
            raise ValueError('Invalid port or step budget')
        if not (1 <= self.game_poll_hz <= 30 and 320 <= self.screenshot_width <= 3840):
            raise ValueError('Invalid capture settings')
        if not (0 <= self.max_runtime <= 2147483647 and 1 <= self.approval_timeout <= 600):
            raise ValueError('Invalid runtime/approval time limit')
        if not (0.1 <= self.screenshot_interval <= 10 and 0.1 <= self.vision_interval <= 30):
            raise ValueError('Invalid polling intervals')
        if not (120 <= self.speech_rate <= 220 and 0 <= self.speech_volume <= 1):
            raise ValueError('Invalid speech rate/volume')
        if not (0.4 <= self.vad_silence <= 2.5 and 5 <= self.voice_max_seconds <= 120):
            raise ValueError('Invalid voice recording limits')
        if not (4096 <= self.context_tokens <= 32768 and 256 <= self.prediction_tokens <= 2048):
            raise ValueError('Invalid inference budget')
        if self.speech_engine not in ('piper', 'sapi'):
            raise ValueError('Unknown speech engine')
        if self.browser_channel not in ('msedge', 'chrome'):
            raise ValueError('Browser channel must be msedge or chrome')
        if not self.model.strip():
            raise ValueError('Choose a model')
        if self.model.lower().endswith('cloud'):
            raise ValueError('Cloud model tags are disabled; choose a downloaded local vision model')
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
        try:
            if path.stat().st_size > 1024 * 1024:
                raise ValueError('Settings file exceeds 1 MB')
            raw = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(raw, dict):
                raise ValueError('Settings must be a JSON object')
            from dataclasses import fields
            defaults = cls(data_dir=root)
            allowed = {f.name for f in fields(cls)} - {'data_dir', 'startup_notice'}
            unknown = set(raw) - allowed
            raw = {key: value for key, value in raw.items() if key in allowed}
            for key, value in raw.items():
                default = getattr(defaults, key)
                if isinstance(default, bool):
                    valid = type(value) is bool
                elif isinstance(default, int):
                    valid = type(value) is int
                elif isinstance(default, float):
                    valid = type(value) in (int, float)
                else:
                    valid = isinstance(value, type(default))
                if not valid:
                    raise ValueError(f'Invalid saved type for {key}')
            if raw.get('settings_version', 1) < 2:
                if raw.get('max_steps') == 40:
                    raw['max_steps'] = 0
                if raw.get('max_runtime') == 600:
                    raw['max_runtime'] = 0
                raw['settings_version'] = 2
            candidate = cls(**raw, data_dir=root)
        except (ValueError, TypeError, UnicodeError):
            return cls.repair(root, 'Invalid saved settings prevented startup')
        if unknown:
            backup = cls.backup_settings(root)
            candidate.startup_notice = f'Outdated settings fields were removed. Original saved as {backup.name}.'
            candidate.save()
        return candidate

    @staticmethod
    def backup_settings(root: Path) -> Path:
        from datetime import datetime, timezone
        import shutil
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        backup = root / f'settings.backup_{stamp}.json'
        shutil.copy2(root / 'settings.json', backup)
        return backup

    @classmethod
    def repair(cls, data_dir: Path | None = None, reason='Settings reset requested') -> 'Settings':
        root = Path(data_dir or user_data_dir())
        root.mkdir(parents=True, exist_ok=True)
        backup = cls.backup_settings(root) if (root / 'settings.json').exists() else None
        candidate = cls(data_dir=root, tier=1)
        candidate.startup_notice = reason + (f'. Original saved as {backup.name}.' if backup else '.')
        candidate.save()
        return candidate

    def save(self) -> None:
        self.__post_init__()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.pop('data_dir')
        payload.pop('startup_notice')
        path = self.data_dir / 'settings.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        temporary.replace(path)
