# Validation · GhostOS 1.2.3

Automated unit/regression coverage runs on Linux and Windows. The release pipeline
also installs all Windows dependencies, freezes the app, checks frozen imports,
creates/closes the screen indicator, synthesizes bundled neural speech without an
audio device, and exercises actual native mouse input in a disposable Windows
window. The cursor and previous foreground window are restored after that probe.
A disposable Edge profile also exercises CDP navigation, a local form fill and
click, disconnect/reconnect and preservation of the completed result tab.
Inno Setup compilation and a real silent install/uninstall must succeed before
GitHub publishes the downloadable installer.

Regression coverage includes:

- unlimited default execution beyond 1,000 actions, optional limits and migration;
- focus blockers remaining active after recovery, native app launch argument arrays;
- own-window input exclusion and no automatic chat restore on completion;
- smooth cursor interpolation, endpoint failure detection, five button mappings,
  double click, cancellation releasing a drag;
- settings separation, voice command auto-submit and cancelled voice rejection;
- VAD pause/noise/duration cases, speech cancellation and exact voice consent;
- request IDs, approval denial, process cleanup, authenticated dashboard boundaries;
- recipe parsing, context trimming, coordinate transforms and Windows INPUT ABI.

Tests deny external Python socket connections. Speech unit tests use fake audio
engines; the frozen voice probe synthesizes locally with ONNX telemetry disabled.
No test needs a cloud model or sends microphone recordings off the PC.

Automated checks do not establish reliable completion of arbitrary natural
language tasks. The Galaxus purchase/search workflow, real microphone acoustics,
voice quality preferences, multiple monitor DPI arrangements, browser enterprise
policies and specific games need acceptance testing on representative PCs. Vision
can choose the wrong control or misjudge success. Windows may reject foreground
transfer or SendInput on secure/protected surfaces; GhostOS reports those failures
and never bypasses UAC. The installer is unsigned.

Before a public recommendation, test Chrome already running/minimized, CDP
unavailable, blocked focus, a >100-step task, right/middle/X-button interactions,
a cancelled drag, approval while chat is hidden, stale voice approval after Stop,
and low-end CPU/GPU inference. Use Tier 1 initially and redact private audit logs
before reporting problems.

The upgrade test installs published 1.2.2, starts its background web runtime,
then updates in place without specifying a destination. It checks the previous
custom folder, termination of the old process, new binary version, native
desktop startup, recovery of a corrupted settings file, explicit installer repair,
a single Installed apps entry and retained recipes/models/logs. Bootstrap and
settings recovery also have unit coverage.
