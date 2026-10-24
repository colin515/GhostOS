"""Read Steam's installed inventory and launch registered numeric app IDs only."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time


@dataclass(frozen=True)
class InstalledGame:
    name: str
    app_id: str
    directory: Path

    def windows(self):
        import psutil
        import win32gui, win32process
        from agent.window_focus import is_agent_window
        output = []
        def visit(hwnd,_):
            if not win32gui.IsWindowVisible(hwnd) or is_agent_window(hwnd):
                return
            try:
                _,pid = win32process.GetWindowThreadProcessId(hwnd)
                executable = Path(psutil.Process(pid).exe()).resolve()
                if executable.is_relative_to(self.directory.resolve()):
                    output.append(hwnd)
            except (OSError,psutil.Error):
                pass
        win32gui.EnumWindows(visit,None)
        return output

    def ensure(self, requested, stop, strategy='launch'):
        from agent.window_focus import focus_window
        launched = False
        until = time.monotonic() + 30
        while not stop.is_set():
            windows = self.windows()
            if windows:
                hwnd = focus_window(windows[0],stop)
                return json.dumps({'app':self.name,'requested_app':requested,'verified':True,'foreground':True,
                                   'hwnd':hwnd,'source':'steam','app_id':self.app_id})
            if not launched:
                if strategy == 'focus':
                    raise LookupError(f'{self.name} is installed but not running')
                os.startfile('steam://rungameid/' + self.app_id)
                launched = True
            if time.monotonic() >= until:
                raise RuntimeError(f'{self.name} launch was sent to Steam; wait for its window or dismiss the launcher dialog. Do not launch another copy.')
            stop.wait(.2)
        raise InterruptedError('Stopped')


def steam_roots():
    if os.name != 'nt':
        return []
    import winreg
    roots = []
    for hive,key,value in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),
                           (winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam','InstallPath')]:
        try:
            with winreg.OpenKey(hive,key) as handle:
                path,_ = winreg.QueryValueEx(handle,value)
                roots.append(Path(path))
        except OSError:
            pass
    return roots


def installed_games(roots=None):
    import vdf
    roots = steam_roots() if roots is None else list(roots)
    libraries = set(roots)
    def read(path):
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Steam inventory file too large')
        return vdf.loads(path.read_text(encoding='utf-8-sig'))
    for root in roots:
        for path in (root/'steamapps/libraryfolders.vdf',root/'config/libraryfolders.vdf'):
            try:
                data = read(path).get('libraryfolders',{})
                for key,value in data.items():
                    if str(key).isdigit():
                        location = value.get('path') if isinstance(value,dict) else value
                        if isinstance(location,str):
                            libraries.add(Path(location))
            except (OSError,ValueError,TypeError,AttributeError,SyntaxError):
                continue
    output = {}
    for library in libraries:
        for manifest in sorted((library/'steamapps').glob('appmanifest_*.acf'))[:2000]:
            try:
                state = read(manifest).get('AppState',{})
                app_id,name,folder = str(state.get('appid','')),state.get('name',''),state.get('installdir','')
                if (not re.fullmatch(r'[1-9][0-9]{0,9}',app_id) or manifest.stem != 'appmanifest_' + app_id
                        or not name or len(name) > 120 or not folder or folder in ('.','..')
                        or any(c in folder for c in '/\\\0:')):
                    continue
                directory = library/'steamapps/common'/folder
                if directory.is_dir():
                    output[name] = InstalledGame(name,app_id,directory)
            except (OSError,ValueError,TypeError,AttributeError,SyntaxError):
                continue
    return output
