# Validation · GhostOS 1.4.0

Automated unit/regression coverage runs on Linux and Windows. The release pipeline
also installs all Windows dependencies, freezes the app, checks frozen imports,
creates/closes the screen indicator, synthesizes bundled neural speech without an
audio device, and exercises actual native mouse input in a disposable Windows
window. The cursor and previous foreground window are restored after that probe.
A disposable Edge profile also exercises CDP navigation, a local form fill and
click, existing-tab reuse from a different current page, verified new tabs,
explicit tab activation, native UIA/address-bar navigation, disconnect/reconnect
and preservation of the completed result tab.
It plays and pauses an actual local silent HTML5 audio stream, verifies playback
time advancement and idempotent Play, and exercises frozen model-setup verification
through the real SDK adapter against a loopback fixture.
Inno Setup compilation and a real silent install/uninstall must succeed before
GitHub publishes the downloadable installer.

Native input probes also click through the actual Controller/capture transform
at default and 150% Qt scaling, then move the target window to verify stale input
is rejected. A separate frozen practice game requires three precise clicks,
simultaneous Shift+W, held right mouse plus camera movement, a final click and
three fresh victory-marker observations. Actual Qt input events establish the
result; mocks alone cannot pass these probes.

Regression coverage includes:

- the user-contributed UI tree, browser probe, indicator, speech, diagnostics,
  gaming-engine and directory-watcher tests merged in PR #3;
- physical coordinate mapping at 100/125/150/200% scale, negative screen origins,
  changed target patches, live accessibility labels and cursor drift before press;
- canonical ChatGPT destinations, installed Steam libraries, conservative typo
  matching, launcher aliases, ambiguous titles and distinct numbered game editions;
- game-profile input restrictions and held-input release after cancellation;

- the reported YouTube-open-plus-play request, separate pending steps and rejected
  false model completion while playback is paused;
- the reported CONTINUE-without-action reply through actual SDK HTTP parsing,
  bounded repair, single-image preservation and independently validated JSON schemas;
- 8 GB model recommendations, inert setup verification and failed checks preventing save;
- context-budget trimming that preserves the original request and latest outcome;

- Windows-Use local tool calls and structured output, blocked unsupported tools,
  single-image prompts, coordinate scaling and bounded advisory loop memory;
- engine setting migration, permission checks on SDK-derived actions and exact
  installed-app launch with command-injection strings rejected;

- the supplied Microsoft Store, Chrome new-tab and Netflix failure transcripts;
- direct navigation despite an unusable model, wrong-site rejection and tab reuse;
- false success at focus/site-open rejected for new tabs and multi-step goals;
- Store registered-URI activation, URL host/path verification, safe fallback order;

- unlimited default execution beyond 1,000 actions, optional limits and migration;
- focus blockers remaining active after recovery, native app launch argument arrays;
- own-window input exclusion, automatic chat restore after completion/Stop/error,
  follow-up submission, and no restoration during a newer task or shutdown;
- smooth cursor interpolation, endpoint failure detection, five button mappings,
  double click, cancellation releasing a drag;
- settings separation, voice command auto-submit and cancelled voice rejection;
- VAD pause/noise/duration cases, speech cancellation and exact voice consent;
- request IDs, approval denial, process cleanup, authenticated dashboard boundaries;
- recipe parsing, context trimming, coordinate transforms and Windows INPUT ABI.

Tests deny external Python socket connections. Speech unit tests use fake audio
engines; the frozen voice probe synthesizes locally with ONNX telemetry disabled.
No test needs a cloud model or sends microphone recordings off the PC. A separate
Linux release job uses a checksum-pinned Ollama server and real local
`qwen3.5:4b` weights to exercise native tool calling and the full structured
action schema on CPU. Its model digest and verification results are attached to
the release. It also checks selection of the named Play accessibility target in
a synthetic image. This validates those specific CPU tasks, not general GPU
workflow accuracy.

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
