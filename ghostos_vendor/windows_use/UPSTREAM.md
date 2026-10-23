# Windows-Use local SDK components

Source: https://github.com/Jeomon/Windows-Use
Version: 0.8.1, commit `582a5669e9251372beb63baf39dac453693ff0d8`.
Original blob identities are recorded in `upstream-manifest.json`.

Windows-Use is Copyright (c) 2025 CursorTouch, MIT licensed (LICENSE-MIT).
Its UIAutomation modules retain their original yinkaisheng attribution and
Apache-2.0 terms (LICENSE-APACHE-UIA). Both licences ship in the Windows installer.

GhostOS vendors only the desktop/accessibility tree, local Ollama provider,
message/tool models and loop detection components. Upstream Agent execution,
cloud providers, telemetry, messaging connectors, CLI, speech services and file
operation tools are not included. This keeps the Windows installer local and
avoids installing unrelated cloud SDKs. Source modifications:

- imports are namespaced under `ghostos_vendor.windows_use`;
- package initializers expose only included local components;
- Ollama clients ignore proxy environment variables for loopback requests;
- visited-state memory is bounded for GhostOS's unlimited execution;
- `agent/windows_use_engine.py` integrates the SDK with GhostOS's single-image,
  bounded-context planning loop, strict action schemas and permission controller.

The integration uses upstream cached UIA observations and Ollama tool-call/message
handling. It deliberately does not call upstream `Agent.invoke` or tool execution:
those would bypass GhostOS's approval boundary and introduce fixed step/failure
limits. Every proposed operation executes through GhostOS `Controller.execute`.
Virtual-desktop internal APIs and upstream input/shell execution are not used.
The adapter filters GhostOS windows and maps physical UIA coordinates to the
current screenshot exactly once. Model choice remains the user's local model.

To update, review a new pinned upstream commit and licences, refresh only this
subset, retain the documented changes, run all regressions and the frozen Windows
browser/SDK probe. Never replace these files by downloading code on app startup.
