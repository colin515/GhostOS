"""Build from repository root on Windows x64. No cross-compilation is claimed."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--console', action='store_true')
    args = p.parse_args()
    if os.name != 'nt' or sys.maxsize < 2**32:
        raise SystemExit('Build with Windows and 64-bit Python 3.11')
    version = (ROOT / 'VERSION').read_text().strip()
    import re
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit('VERSION must contain major.minor.patch')
    os.chdir(ROOT)
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    version_tuple = ', '.join(version.split('.') + ['0'])
    version_info = build / 'version_info.txt'
    version_info.write_text(f'''VSVersionInfo(ffi=FixedFileInfo(filevers=({version_tuple}), prodvers=({version_tuple}),
mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','GhostOS Contributors'),
StringStruct('FileDescription','GhostOS local Windows agent'), StringStruct('FileVersion','{version}'),
StringStruct('ProductName','GhostOS'), StringStruct('ProductVersion','{version}'),
StringStruct('LegalCopyright','GPL-3.0-or-later')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])''', encoding='utf-8')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--name', 'GhostOS', '--version-file', str(version_info),
               '--manifest', str(ROOT / 'build_tools' / 'app.manifest'),
               '--console']
    if not args.console:
        command += ['--hide-console', 'hide-early']
    for source, dest in [('VERSION', '.'), ('shortcuts.json', '.'), ('docs', 'docs'), ('recipes', 'recipes'),
                         ('ui/dashboard.html', 'ui'), ('LICENSE', '.')]:
        command += ['--add-data', f'{source}{os.pathsep}{dest}']
    for module in ('faster_whisper', 'ctranslate2', 'uiautomation', 'pyttsx3', 'playwright'):
        command += ['--collect-all', module]
    for module in ('pynput.keyboard._win32', 'pynput.mouse._win32', 'pyttsx3.drivers.sapi5',
                   'win32timezone', 'pythoncom', 'pywintypes', 'win32com.client',
                   'win32job', 'win32gui', 'win32api', 'sounddevice', 'webrtcvad', '_webrtcvad'):
        command += ['--hidden-import', module]
    command += ['--exclude-module', 'PySide6', '--exclude-module', 'PyQt5', 'main.py']
    subprocess.run(command, check=True)
    # Record the exact environment used for each executable; attach during release.
    manifest = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
    (ROOT / 'dist' / 'build-dependencies.txt').write_text(manifest, encoding='utf-8')


if __name__ == '__main__':
    main()
