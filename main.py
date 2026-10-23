"""Windows launcher. Importing this module never starts automation."""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path
from config import Settings, VERSION, enable_dpi_awareness


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='GhostOS — local Windows OS agent')
    p.add_argument('--version', action='version', version=VERSION)
    p.add_argument('--diagnostics', action='store_true')
    p.add_argument('--browser-smoke-test', action='store_true', help='Check CDP on a disposable browser profile and local form')
    p.add_argument('--input-smoke-test', action='store_true', help='Move/click inside a disposable native test window')
    p.add_argument('--voice-smoke-test', action='store_true')
    p.add_argument('--setup', action='store_true')
    p.add_argument('--indicator-smoke-test', action='store_true', help='Check the activity indicator lifecycle without computer input')
    p.add_argument('--non-interactive', action='store_true', help='Deny actions needing human approval')
    p.add_argument('--desktop', action='store_true')
    p.add_argument('--web', action='store_true', help='Enable authenticated LAN dashboard')
    p.add_argument('--game', action='store_true')
    p.add_argument('--goal')
    p.add_argument('--recipe', type=Path)
    p.add_argument('--watch', type=Path, help='Directory whose changes trigger --recipe')
    p.add_argument('--register-task', metavar='NAME')
    p.add_argument('--at', default='11:00')
    p.add_argument('--tier', type=int, choices=(1, 2, 3))
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.voice_smoke_test:
        from agent.neural_speech import smoke_test
        smoke_test()
        return 0
    if args.diagnostics:
        from agent.diagnostics import diagnostics
        report = diagnostics()
        print(json.dumps(report, indent=2))
        return 0 if all(report['resources'].values()) and (not report['windows'] or all(report['modules'].values())) else 1
    if os.name != 'nt':
        print('GhostOS requires Windows 10/11 x64.', file=sys.stderr)
        return 2
    enable_dpi_awareness()  # Before Qt, UIA or screenshot imports.
    if args.browser_smoke_test:
        from agent.browser_probe import run_probe
        return run_probe()
    if args.input_smoke_test:
        from ui.input_probe import run_probe
        return run_probe()
    if args.indicator_smoke_test:
        from ui.activity_border import ActivityIndicator
        indicator = ActivityIndicator(mp.get_context('spawn'))
        try:
            indicator.start()
        finally:
            indicator.close()
        return 0 if indicator.process.exitcode == 0 else 1
    settings = Settings.load()
    if args.tier:
        settings.tier = args.tier
    settings.game_mode = args.game
    if args.setup:
        from setup import run_console
        return run_console(settings)
    if args.register_task:
        if not args.recipe:
            parser().error('--register-task requires --recipe')
        from automation.scheduler import register_task
        register_task(args.register_task, args.recipe, args.at, settings.tier)
        return 0
    from agent.runtime import Runtime, InstanceLock
    with InstanceLock(settings.data_dir):
        with Runtime(settings) as runtime:
            runtime.interactive_cli = not args.non_interactive
            if args.web:
                runtime.start_web()
                print(f'Dashboard: http://{runtime.local_ip}:{settings.web_port} — pair in desktop settings or see {settings.data_dir / "dashboard-token.txt"}')
            if args.watch:
                if not args.recipe:
                    parser().error('--watch requires --recipe')
                from automation.watcher import watch
                watch(args.watch, args.recipe, runtime)
            elif args.goal or args.recipe:
                return runtime.run_cli(args.goal, args.recipe)
            elif args.desktop or not args.web:
                from ui.app import launch
                return launch(runtime)
            else:
                runtime.wait_cli()
    return 0


if __name__ == '__main__':
    mp.freeze_support()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
