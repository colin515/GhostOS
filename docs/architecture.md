# Architecture · GhostOS 1.4.1

The non-elevated parent owns Qt, the approval broker, event journal, speech queue,
LAN dashboard and emergency hotkeys. A spawned worker owns Ollama, UIA,
Playwright/CDP, native input and commands. The glowing screen border runs in a
separate, click-through, non-focusable process and must be ready before input.
An unexpected indicator exit stops the worker.

## Background execution and focus

Submitting a goal hides the chat, including goals received from the dashboard.
After worker cleanup, `FINISHED` restores and activates the chat once, focuses
the composer and makes typed/voice follow-up available. It does not start the
microphone automatically. A newer active run or application shutdown prevents
restoration. The tray's explicit **Show GhostOS** action also restores it. While a task is active,
even that window is shown without activation. An animated non-activating ghost offers a clickable Stop action, task-state animations,
voice activity and optional browser help. A click-through animated pointer overlay
follows task mouse activity without creating a second native Windows pointer. Approval windows
also use `WindowDoesNotAcceptFocus` and `WA_ShowWithoutActivating` and never
call `exec()`, `raise_()` or `activateWindow()`.

GhostOS UI handles carry a Windows property. `FocusGuard` remembers the last
external foreground window and refuses native input into GhostOS's own windows.
`focus_window` restores/maximizes a target, temporarily attaches input queues,
requests foreground transfer and verifies the actual foreground handle. All
attachments are detached in `finally`. Windows can deny input/focus on UAC,
locked or protected desktops; failed verification is reported and re-observed,
never treated as proof that the user's goal is impossible.

Known applications are discovered through Windows App Paths and fixed installed
locations. Executables are launched with argument arrays and `shell=False`.
Recovery no longer invokes Windows Search or Alt+Tab. Legacy recipe strategy
`search` maps to native launch. Arbitrary approved PowerShell runs invisibly with
CREATE_NO_WINDOW, a per-command timeout, bounded output and a kill-on-close job.
It does not request elevation or bypass execution policy.

## Navigation engines

The default `WindowsUseBrain` integrates a pinned local subset of the MIT-licensed
Windows-Use SDK: cached UIA tree/window inventory, Ollama tool-call/message handling
and advisory loop detection. Cloud providers, telemetry and upstream execution
are excluded. An adapter converts UIA targets into screenshot coordinates before
inference. Tool-capable models use function calls; existing local vision models
use the SDK structured response path. Each result becomes a validated GhostOS
Action and passes Controller/WorkerSafety. This retains unlimited execution and
avoids an upstream loop bypassing approvals. The AI gear also offers the legacy
planner; Game Mode keeps its specialized planner. Upstream source identities and
MIT/Apache notices are bundled under `ghostos_vendor/windows_use`.

`app_list` reuses the SDK's Windows installed-app reader through a hidden, fixed,
read-only PowerShell inventory query. Exact installed display names can launch
through `shell:AppsFolder`; model text is never interpolated into that command.
`focus_window` uses a listed native handle and refuses GhostOS-owned handles.


Browser actions use a loopback CDP connection to Chrome/Edge first. A separate
GhostOS browser profile is provisioned automatically, or the user can supply a
loopback endpoint. A read-only DOM excerpt provides selector context. Failure
switches the run to native controls and offers an optional setup explanation.
Uncertain form operations are never automatically replayed. Browser processes
and result tabs remain open after successful worker exit. See [browser setup](browser_control.md).

UIA provides live physical bounds. Each observation records its window handle,
physical capture origin, original size and resized image size. The active external
window can be on any monitor, including negative desktop coordinates. UIA nodes
are converted to image coordinates before inference; actions convert back exactly
once. Explicit normalized-1000 coordinates are supported without heuristic guessing.

`ui_click` validates live element identity, foreground ownership and bounds just
before pressing. Unique accessible labels can also resolve a target. Coordinate
clicks compare a fresh target patch and reject stale geometry. MouseDriver checks
focus throughout smooth movement and rechecks the cursor endpoint before every
press. A user moving the cursor cancels that press. Drags release on all exit
paths. TARGET events include the physical/image point and annotated preview;
MOUSE events include requested/observed positions. Windows can reject input on
protected surfaces; no driver or privilege bypass is attempted.

Canonical named destinations resolve ChatGPT directly. Installed-app matching uses
exact names first, explicit launcher aliases second and conservative unambiguous
fuzzy matching last; it never invents a website from an unknown game name. Steam
inventory reads trusted local VDF manifests and validates an actual installed
directory. Numeric AppIDs activate through Steam; a game window is verified by
its process executable inside that directory. Start Menu launches retain their
registered application IDs. Unknown or ambiguous names stay pending.

Game Mode supports simultaneous keys/buttons and relative mouse motion with
focus/cancellation checks and unconditional input release. `game_bind` requires
the exact observed foreground title. Optional YAML profiles run fast template
policies and require repeated fresh victory matches; they share permissions and
cannot execute shell commands. Without a profile, finish/win claims receive an
independent fresh-image victory check. The offline practice game verifies all
control stages with real Windows input. This establishes input capability rather
than universal game-playing competence. See [gaming mode](gaming_mode.md).

## Persistent execution

`max_steps=0` and `max_runtime=0` mean **unlimited**, the defaults. Nonzero limits
are optional in AI settings. Old default 40-step/600-second settings migrate to
unlimited; other saved limits are preserved. Scheduled task execution time is
also unlimited. Individual network calls, commands, microphone recordings and
approval requests retain timeouts so Stop and error reporting remain useful.

A model GOAL_IMPOSSIBLE answer becomes a recovery progress event, not a terminal status. Native focus,
direct launch and fresh observations are attempted, followed by cancellable
cooldowns and replanning. Exhausting the initial recovery ledger does not end
the task. Repeated invalid/model transport replies retry with a capped backoff.
The goal remains active until success, Stop, an optional explicit limit,
permission denial/expiry, or an unrecoverable capture/process/system error.
There is no automatic retry of scripts, submissions or deletions with uncertain
outcomes. Persistence is not permission to bypass consent or Windows UAC.

Validated YAML recipes and explicit `/action JSON` bypass model inference but
share permission checks. They report RECIPE_COMPLETED/COMMAND_COMPLETED, not
visually verified success. Explicit navigation is routed by `navigation.py` before
inference, with three distinct browser strategies (automatic tab reuse/CDP,
native address-bar navigation, explicit CDP). `windows_apps.py` includes Store
URI activation and Windows 10 ApplicationFrameHost child-process discovery.
`browser_open`, `browser_new_tab`, `browser_tabs` and `browser_switch_tab` have
validated arguments and share the permission boundary with all other actions.

Native tab reuse reads browser chrome through UIA, excludes webpage documents,
selects candidate tabs and verifies their actual URL. Address-bar navigation
verifies the foreground window and focused editor ownership before typing.
Tab creation verifies a count increase. CDP inventories/activates existing tabs,
creates real tabs, and tracks newly opened pages after clicks. Structured evidence
is valid JSON even when DOM text is unavailable; merely dispatching input does
not prove success. Uncertain form operations are never replayed as navigation.

Pure navigation finishes only with matching evidence. For complex goals, the
prerequisite remains separate: success at app focus/site open is rejected, at
least one subsequent task action must succeed, and a fresh-observation completion
check must reassess the whole original goal. After a premature terminal verdict,
the next inference schema requires an action. General task completion still
relies on the local model's visual/DOM assessment and is not guaranteed.

`task_progress.py` retains explicit sequential clauses as pending steps. Only
completion of the final step emits terminal STATUS; intermediate steps emit
TASK_PROGRESS and preserve the full original request. `browser_media.py` checks
HTML5 media state and advancing playback time through CDP, or the actual YouTube
accessible Play/Pause control through native mouse input. Play is idempotent.
Playback success claims are checked against fresh player state, including when
the model claims completion after another action. Consent/login/buffering and
unknown controls remain pending rather than being treated as success.

`model_protocol.py` supplies a generation schema with per-action argument types
and separate CONTINUE/terminal branches. The runtime validator remains strict.
A missing action causes a bounded correction request, never an inferred mouse
click or script from prose. `model_setup.py` exercises the selected installed
planner using an inert wait request and synthetic image before saving setup;
it never creates a Controller or reads the actual desktop.

## Responsiveness and local inference

Process startup, commands, recognition, speech and frame decoding stay outside
Qt's GUI thread. Logs update in bounded batches; frames replace old frames rather
than accumulating. Hidden previews skip extra read-only capture. Model requests
contain one current image and bounded text history; old results use deterministic
compression without a second inference. Default images are 1024px wide, with a
512-token response budget. UIA provider calls can stall inside a third-party
provider; the process supervisor and emergency brake can terminate that worker.
An optional runtime limit can additionally bound unattended runs.

`context_budget.py` trims history, browser inventories and accessibility nodes
according to the context budget, reserving space for system/tool schemas, image
tokens and output. It preserves the full goal and latest outcome rather than
letting oversized trees silently crowd them out. Thinking-capable models receive
`think:false` when they advertise optional thinking; public assessments stay short.

THOUGHT/PLAN events are brief public progress assessments and intended actions,
not hidden chain-of-thought. Page text and command output are untrusted data.
All model/recipe/API actions use the same strict Pydantic argument validation.

## Voice and approvals

WebRTC VAD detects utterance endpoints from 20ms PCM frames, with pre-roll,
noise rejection, silence timeout and bounded recording duration. Cached local
Whisper transcribes on CPU int8. The waveform uses real microphone levels.
A voice goal starts immediately with an asynchronous "On it" acknowledgment.

The installer contains Piper 1.3, its embedded phonemizer and the pinned
LJSpeech-medium neural voice. No API key or TTS download is needed after install.
ONNX Runtime telemetry is disabled before creating any voice session. Speech
runs in one owner thread with bounded messages, small playback chunks and
cancellation tickets. Windows SAPI remains a selectable fallback. Narration
starts only after authorization and never reads field values or scripts aloud.

Voice approval is off by default. When enabled it listens only for one current,
expiring permission request, after acknowledgment playback and an echo cooldown.
Only exact affirmative/negative phrases resolve it; ambiguous speech does not.
Request IDs, expiry and Stop are checked again before delivering the answer.
Buttons and the authenticated phone dashboard remain available. It is ordinary
spoken consent, not speaker authentication; other people audible to the mic can
answer. Recognition requires the separate first-run Whisper model download.

## Safety, logs and packaging

Tier 1 confirms every action. Tier 2 auto-approves non-consequential navigation,
read-only browser state and direct known-app launch; typing, ambiguous clicks,
drags, form input, scripts and game keys/clicks require consent. Tier 3 approves
all supported non-elevated actions. The parent restores/validates an approved
native target before releasing input. No tier handles UAC automatically.

The emergency brake sets cancellation first, kills the owned worker tree and
releases held keys and all mouse buttons. It cannot undo completed side effects.
The bounded in-memory bus retains one frame; JSONL audit logs persist per run.
Disk screenshots are opt-in. Logs may contain user text and page data.

PyInstaller bundles the custom multi-resolution ICO and voice resources. The
window, taskbar, Start Menu shortcut and Inno wizard share GhostOS identity.
An asInvoker/Per-Monitor-V2 manifest preserves privilege and coordinate behavior.
The main-push/tag workflow tests, freezes, exercises native mouse input in a
disposable window, exercises a local browser form and persistent CDP tabs,
synthesizes neural speech without audio hardware, checks the
indicator, compiles Inno Setup, and tests install/uninstall before publishing
an EXE, versioned documentation, dependency inventory and checksums. Installers
are currently unsigned. The full app remains free under GPL-3.0-or-later.

## Upgrades and startup recovery

The frozen entry point is `launcher.py`, a small stdlib-only bootstrap that logs
import/startup failures before loading Qt. Interactive launch failures show a
Windows message; CLI failures return an error code. Logs rotate under
`%LOCALAPPDATA%\GhostOS\startup.log`. A second desktop launch signals the
existing UI through a per-user request file; it never starts a second agent.
Valid old settings migrate, unknown fields are backed up and removed, and invalid
settings recover to Strict mode with a backup and a visible notice.

Inno keeps the established AppId and previous installation path. Restart Manager
force-closes processes holding GhostOS files before replacement; previous runs
are not automatically resumed. An explicit, unchecked repair task backs up and
resets only settings. Release CI verifies upgrades from the published 1.2.2
installer with a running headless process and checks actual GUI startup after
normal and corrupted-setting upgrades. Models, recipes and logs are preserved.
