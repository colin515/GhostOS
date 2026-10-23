"""Least-privilege interactive scheduled runs; password-free current-user Task Scheduler XML."""
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape


def task_xml(recipe, at, tier):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', at):
        raise ValueError('Time must be HH:MM in local Windows time')
    if tier not in (1, 2, 3):
        raise ValueError('Invalid permission tier')
    recipe = Path(recipe).resolve(strict=True)
    from automation.recipe_parser import load_recipe
    load_recipe(recipe)
    if getattr(sys, 'frozen', False):
        executable = Path(sys.executable)
        args = ['--recipe', str(recipe), '--tier', str(tier)]
    else:
        executable = Path(sys.executable)
        args = [str(Path(__file__).resolve().parents[1] / 'main.py'), '--recipe', str(recipe), '--tier', str(tier)]
    arguments = subprocess.list2cmdline(args)
    import getpass
    username = os.environ.get('USERNAME', getpass.getuser())
    domain = os.environ.get('USERDOMAIN')
    account = domain + chr(92) + username if domain else username
    start = datetime.now().strftime('%Y-%m-%d') + 'T' + at + ':00'
    # InteractiveToken means logged in; locked/secure desktops still cannot be controlled.
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<Triggers><CalendarTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
<Principals><Principal id="Author"><UserId>{escape(account)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT15M</ExecutionTimeLimit></Settings>
<Actions Context="Author"><Exec><Command>{escape(str(executable))}</Command><Arguments>{escape(arguments)}</Arguments><WorkingDirectory>{escape(str(recipe.parent))}</WorkingDirectory></Exec></Actions>
</Task>'''


def register_task(name, recipe, at='11:00', tier=2):
    if os.name != 'nt':
        raise OSError('Windows Task Scheduler is required')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', name):
        raise ValueError('Task name must contain only letters, digits, _ and -')
    content = task_xml(recipe, at, tier)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'task.xml'
        path.write_text(content, encoding='utf-16')
        # No /F: never silently overwrite an existing task.
        subprocess.run(['schtasks.exe', '/Create', '/TN', f'GhostOS-{name}', '/XML', str(path)], check=True)
