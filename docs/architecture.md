# Architecture · GhostOS 1.0.1

`main.py` selects desktop, network, CLI, recipe, watcher or scheduler mode and
sets Per-Monitor-V2 DPI awareness before importing capture/Qt libraries. One
per-user file lock prevents separate instances from controlling the same PC.
The non-elevated parent owns a bounded event bus, approval broker, optional
FastAPI server and global stop listener. A spawned worker owns automation,
Playwright and Ollama requests. The GUI never waits on inference or a command. A separate read-only capture thread
keeps the desktop/LAN screenshot feed live during model inference and approval
waits; it stops with the run.

## Decision and execution boundary

1. Capture the primary monitor; retain physical size with the model-size image.
2. Read a bounded foreground UIA tree on an initialized COM thread (desktop mode).
3. Build context from the goal, compact outcome history, current DOM excerpt and
   exactly one latest screenshot. Old images are never retained in model context.
4. Ask local Ollama for a schema-constrained `Decision`. A brief public `summary`
   and short `plan` are logged as THOUGHT and PLAN; hidden chain-of-thought is not
   requested or displayed.
5. Validate the action type and arguments. Unknown actions/fields are rejected.
6. Apply intrinsic permission rules and a unique expiring approval, when needed.
7. Dispatch one action. Return an outcome; capture again before the next decision.
8. End with `GOAL_SATISFIED`, `GOAL_IMPOSSIBLE`, `MAX_STEPS_EXCEEDED` or a runtime,
   permission, stop/error state. Completion is a model assessment, not a formal
   proof of success.

YAML recipes and `/action JSON` skip inference, but share validation, authorization
and dispatch. They end as `RECIPE_COMPLETED` or `COMMAND_COMPLETED` to avoid
claiming the goal was visually verified. The recipe step budget includes all
steps; increase `max_steps` before a longer recipe. A deterministic compression
of old outcomes bounds text without another model call. Image resize transforms
map model pixels back to primary-monitor physical pixels; no extra global DPI
factor is applied to physical screenshots/UIA bounds. Multi-monitor targeting is
not implemented. DPI scale queries are diagnostic and available for future
logical-coordinate integrations.

## Hybrid engines

UIA exposes current element IDs and physical bounds. Mouse fallback is an optional
OpenCV-labelled grid on the latest model screenshot. Native keyboard shortcuts
and packaged `shortcuts.json` commands take precedence. Unicode typing uses
SendInput rather than modifying the clipboard. GUI approval restores the captured
foreground target before releasing the worker, and the worker checks focus again.
Failed foreground restoration denies the action.

Playwright runs inside the worker thread that created it, with an isolated Edge
profile. When `cdp_url` is explicitly configured, it attaches to a Chromium
browser on loopback and uses that existing context. The app does not enable a
remote-debugging port for you. Closing an attached connection does not deliberately
close the user-owned browser. Browser form fills and ambiguous clicks are subject
to approval; all action effects still require subsequent observation.

Game mode uses the same decision boundary, with UIA/grids disabled and short
relative DirectInput/SendInput actions. Fast OpenCV polling provides template
observations between slower model calls. It is not a real-time competitive game
AI and does not bypass protected input systems.

## Recovery, safety and lifecycle

If a visual action produces no measurable screen change within two seconds, a
permission-checked focus recovery runs. The next observation asks the planner to
recalculate targets or prefer Tab navigation. The system does not blindly press
Enter or replay commands/submissions. Three repeated stalls/errors terminate the
run. Some invisible but successful actions can trigger this conservative stall
check; shell and browser-fill actions are not automatically retried.

PowerShell runs with a bounded time/output budget, no profile, no elevation and no
execution-policy bypass. Each shell child is assigned to a Windows kill-on-close
Job Object; cleanup also kills its descendant tree. The global brake sets the
cancel event, terminates the owned worker tree and releases pressed inputs. It
does not shut down Windows or kill every Python/Ollama process. Cancellation
cannot undo writes or external requests that already completed. The supervisor
also enforces a total deadline if a third-party automation API hangs.

Permissions govern agent dispatch, not a security sandbox. Tier 3 arbitrary shell
commands have the logged-in user's full authority and could spawn detached or
externally scheduled work; no user-space stop button can guarantee cancellation
of all effects of arbitrary scripts. No tier can automatically handle UAC.
Refusing elevated app startup avoids accidentally granting a privileged token.

Event queues are bounded manager queues so terminating a worker while it sends a
large screenshot does not corrupt the supervisor's IPC queue. The in-memory bus
retains a bounded event journal and one latest frame. Session JSONL logs persist
under user application data. Screenshot disk logging is opt-in and off by default.
Local Whisper and SAPI text-to-speech run outside the GUI thread; they do not send
audio to a hosted service.

## Automation and packaging

Recipes are finite validated YAML, with no eval/interpolation. Directory watcher
changes are debounced; busy runs coalesce. Task Scheduler XML uses InteractiveToken
and LeastPrivilege, so screen workflows need an unlocked logged-in desktop. It
never stores account passwords or silently replaces an existing task.

PyInstaller packages an onedir app with Qt/COM/Playwright/voice resources. An
asInvoker manifest preserves Windows privilege boundaries. Inno Setup installs
per-user. Tagged GitHub Actions builds test, freeze, install/uninstall smoke-test,
then publish the installer, exact dependency inventory, documentation and hashes.
The build job has read-only repository permissions; only the separate publish job
receives contents-write access. There is no telemetry or hosted inference tier.
