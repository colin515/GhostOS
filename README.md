# GhostOS

A free, open-source Windows 10/11 local OS agent. GhostOS combines a PyQt6 desktop,
a phone-friendly FastAPI dashboard, local Ollama vision inference, Windows UI
Automation, Playwright, and bounded game input.

**Status:** version 1.2.1. Automated tests and Windows build, installation and
uninstallation smoke checks pass. Native desktop workflows, hardware acceleration
and game compatibility still need validation on representative PCs. A local vision model can make mistakes. Start with Tier 1
and simple goals. No subscriptions, paid tiers or hosted inference service.

## Download and install

1. Open [the latest release](https://github.com/colin515/GhostOS/releases/latest).
2. Under **Assets**, download **GhostOS_Installer_v1.2.1.exe** and run it.
3. Open GhostOS from the Start Menu. The first-run wizard guides you through
   installing Ollama and downloading a local vision model.

The setup executable includes Python and application dependencies. You do not
need to download the source ZIP or install Python. Windows 10/11 x64 is required.
The installer is unsigned, so Windows may display an unknown-publisher warning.
See [installation instructions](docs/installation.md) for verification and setup.

## Run from source on Windows

Install [Python 3.11 x64](https://www.python.org/downloads/windows/) and
[Ollama for Windows](https://ollama.com/download/windows). Start Ollama normally.
Clone this repository:

```powershell
git clone https://github.com/colin515/GhostOS.git
cd GhostOS
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe build_tools/fetch_voice.py
.\.venv\Scripts\python.exe main.py --desktop
```

The first-run wizard scans RAM, CPU and GPU, recommends a vision model, and asks
before downloading model weights. You can also run `main.py --setup` in a terminal.
`build_tools/bootstrap.ps1` performs the same environment setup. Do not run the
application as Administrator. No browser download is needed: Playwright launches
Microsoft Edge using a separate local profile by default.

### Ollama configuration

Use an up-to-date Ollama release. **The valid model tag is `qwen2.5vl`, without a
hyphen.** All inference goes to `http://127.0.0.1:11434`. No cloud API key is needed.

| Dedicated GPU memory | Default recommendation | Practical limitation |
| --- | --- | --- |
| At least 24 GB plus 32 GB system RAM | `qwen2.5vl:32b` | ~21 GB weights, plus runtime/context memory |
| 8–23 GB | `qwen2.5vl:7b` | ~6 GB weights; leave memory for Windows/game |
| Below 8 GB or unknown GPU memory | `llava:7b` | CPU or partial GPU offload; RAM and latency matter |

`llama3.2-vision:11b` and `qwen2.5vl:3b` are selectable alternatives. A 16 GB GPU
is offered 32B as an optional choice, rather than being assumed to fit it fully.
The hardware inventory is a model-fit estimate. After downloading a model, click
**Benchmark selected model** in setup to measure local vision inference, model
load time, output tokens per second, RAM availability and GPU memory use. The
benchmark uses a synthetic image and does not capture your desktop. Actual
workflow latency depends on screen complexity and context size. Model licences remain separate.

### Desktop and phone dashboard

Describe a goal and press **Send**. The chat hides while GhostOS works and never
automatically restores on completion. A non-activating panel provides Stop and
approvals; explicitly restore the chat from its tray icon when wanted. The
trajectory shows public progress, current screenshots and cursor debug events.

The **AI gear beside Send** controls model, permissions, browser and optional
execution limits. **Settings in the top-right** controls voice and the dashboard. In Settings, start the dashboard. On a phone on the
same trusted Wi-Fi, open the displayed `http://<PC-IP>:8000`, then enter the pairing
token from Settings. You can submit goals, approve actions and stop a run. Only
one goal runs at a time. The server is opt-in, binds `0.0.0.0:8000`, requires a
per-launch token, checks origins/hosts, and rejects non-private clients.

```powershell
.\.venv\Scripts\python.exe main.py --desktop --web
.\.venv\Scripts\python.exe main.py --web
.\.venv\Scripts\python.exe main.py --goal "Open Notepad and type Hello" --tier 1
.\.venv\Scripts\python.exe main.py --game --desktop
```

A glowing yellow, click-through border appears around every connected screen
while an agent task is active, including tasks started from the phone or CLI.
The main window stays hidden without hiding the indicator. Native exclusive
fullscreen games and secure desktops can suppress normal Windows overlays.

### Voice commands and narration

Enable voice and download the recognition model through **Settings → Model and
voice setup**. Click Speak, talk, then pause. WebRTC VAD ends the recording;
cached local Whisper transcribes, the agent says **"On it"** and starts the task.
The microphone waveform reacts to your voice. Stop cancels pending recordings.

The Windows installer includes a free, offline **Piper neural voice** with no API
key or TTS setup. Choose Piper or a Windows fallback voice, preview it, and adjust
the speaking rate in Settings. Narration and completion audio are independent.
**Voice approvals** is opt-in: say "Yes" or "Approve" only while a permission
request is listening, or "No" to decline. Ambiguous phrases do not authorize.
Listening begins after speech playback stops and is bound to that exact request.
Buttons remain available. Voice consent is not speaker authentication.

**Ctrl + Alt + K**,  **Ctrl + Alt + Esc**, the desktop Stop button and the mobile
Stop button cancel the worker and release held keyboard/mouse inputs. Only owned
worker processes/children are terminated; an independently running Ollama remains
available. Already-completed side effects are not rolled back. Windows UAC and
protected/locked desktops require manual handling.

## Permission tiers

| Tier | Behaviour |
| --- | --- |
| 1 — Strict | Confirm every executable action, including waits and recovery focus |
| 2 — Balanced | Automatically navigate/open packaged app shortcuts/read browser state; confirm shell commands, typing, ambiguous clicks, form input, game keys/clicks and non-navigation hotkeys |
| 3 — Max risk | Automatically approve all supported actions; no privilege elevation or UAC automation |

Balanced intentionally confirms ambiguous clicks: a normal click can submit a
form or delete a file. Permissions are derived from validated actions, never an
LLM-provided risk label. Approval timeout/decline stops the run. Scheduled runs
without an interactive approval channel deny actions needing confirmation.

## Autonomous recovery and performance

Native Windows APIs restore and verify focus. Known applications launch directly
from their installed executable, without Windows Search or Alt+Tab recovery.
Browser actions prefer Playwright/CDP with a separate loopback browser profile;
CDP failures warn, offer optional setup help and switch to mouse/keyboard control.
See [browser control](docs/browser_control.md).

The actual cursor moves smoothly and is verified through Windows APIs. Left,
right, middle, X1/X2, double click, dragging and scrolling are supported. MOUSE
logs show requested and observed physical positions. Vision targeting uses the
primary screen; Windows can block input on protected/secure desktops.

**Steps and runtime are unlimited by default.** Optional nonzero limits are in
AI settings. Model "impossible" answers become blocked progress, followed by
fresh observations and safe recovery; repeated model errors use cancellable
backoff. The run ends on success, Stop, an explicit limit, declined/expired
permission or unrecoverable system error. Uncertain writes are not blindly retried.

Worker startup, JPEG preview decoding, speech and recognition stay off the UI
thread. Logs are batched, previews replace older frames, JPEGs are cached per
observation, and hidden previews skip extra capture work. New settings use 1024px
vision images and a 512-token response budget; existing image-width settings are
preserved. Raise image width/output budget for small text or complex forms.
GPU/model speed remains hardware-dependent.

## Recipes, scheduling and triggers

```powershell
.\.venv\Scripts\python.exe main.py --recipe recipes/notepad.yaml --tier 1
.\.venv\Scripts\python.exe main.py --register-task DailyDocs --recipe recipes/browser.yaml --at 11:00 --tier 2
.\.venv\Scripts\python.exe main.py --watch C:\Inbox --recipe recipes/browser.yaml --tier 2
```

Task Scheduler runs daily in the logged-in user's interactive session, at least
privilege. “Headless” means no GhostOS GUI; it does **not** mean screen automation
works while logged out or on the lock screen. Start neither a second desktop nor
a second scheduled run at the same time. Watchers debounce changes and coalesce
triggers while busy. Choose an input directory separate from logs/output to
avoid feedback loops. Inspect every recipe you download.

For an explicit, model-free fast path, pass `/action {"kind":"hotkey","args":{"keys":["ctrl","l"]}}`
as the goal. PowerShell uses the `shell` action with a `script` and bounded
`timeout`; it still passes the current permission tier. Natural language goals
always use observe → decide → authorize → execute → verify.

## Build and release

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe build_tools/build.py
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.2.1 build_tools/GhostOS_installer.iss
```

A one-folder PyInstaller distribution contains `GhostOS.exe` and its runtime.
Inno Setup wraps it as `GhostOS_Installer_v1.2.1.exe`, installs per user without
admin rights, adds Start Menu shortcuts and provides an uninstaller. The app has
an asInvoker, Per-Monitor-V2 manifest. **Installers are unsigned** until a
maintainer adds their own trusted Authenticode signing pipeline; SmartScreen may
show a warning. This project does not promise otherwise.

Update `VERSION` and push directly to `main`. The release workflow automatically
builds and publishes that version, creating its matching tag at the exact build
commit. Pushing a matching version tag (`v1.2.1`) or manually running **Windows
release** from `main` also works. Use a new version for every published release;
published assets are not silently replaced.

The workflow tests on Windows, freezes the application, compiles and smoke-tests
the installer, and publishes the setup executable, versioned documentation ZIP,
exact build dependency inventory and SHA-256 checksums. A successful installer
build is required for publication. Versioned docs also live at `/tree/<tag>/docs`.

## Project layout

```text
.github/workflows/   tests.yml, release.yml
build_tools/         build.py, GhostOS_installer.iss, app.manifest, bootstrap.ps1, start.cmd
main.py              GUI/CLI/web/game/recipe/watch/schedule launcher
config.py            per-user settings and DPI awareness
setup.py             interactive model and voice setup
ui/                  app.py, settings_view.py, trajectory_view.py, setup_wizard.py,
                     tasks.py, dashboard.html
agent/               brain.py, controller.py, vision.py, ui_tree.py, gaming_engine.py,
                     safety.py, runtime.py, worker.py, events.py, processes.py,
                     web_dashboard.py, web_engine.py, hardware.py, diagnostics.py, voice.py
automation/          recipe_parser.py, scheduler.py, watcher.py
recipes/             finite, validated YAML examples
docs/                installation.md, gaming_mode.md, web_dashboard.md, architecture.md,
                     validation.md
shortcuts.json       packaged Windows application commands
tests/               permission, API, worker, recipe and coordinate tests
VERSION              release version source of truth
```

Persistent files live in `%LOCALAPPDATA%\GhostOS`: settings, recipes, templates,
voice model, isolated browser profile, token and `logs/run_TIMESTAMP/events.jsonl`.
Screenshots stream in memory; disk screenshot logging is disabled by default.
Audit logs can contain typed text, command output and page data. Keep them private.
The uninstaller preserves personal app data and separately installed Ollama/models.
Delete the data folder yourself when you want to remove those files.

## Contribute

Open an issue with reproducible steps, Windows version and redacted logs. Fork,
create a branch, implement a focused change, run tests/lint, and submit a pull
request. Add tests for permission boundaries and bug fixes. Do not attach real
credentials, tokens, browser profiles or private screenshots. Contributions must
remain compatible with **GPL-3.0-or-later**, selected to accommodate PyQt6's GPL
licensing. No CLA, payment or hosted account is required.

See [the 1.2 changes](docs/upgrade_1_2.md), [installation](docs/installation.md), [game mode](docs/gaming_mode.md),
[dashboard](docs/web_dashboard.md), [architecture](docs/architecture.md) and
[validation limits](docs/validation.md).
