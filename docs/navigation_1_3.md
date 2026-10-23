# Navigation fixes · GhostOS 1.3

The reported failures came from relying on a screenshot-only verdict before doing
basic navigation. Store was missing from the app catalog; the preflight only
recognized literal domains; a model could confuse app focus with completing the
whole request. Recovery then repeated focus/observation instead of navigating.

This release introduces a deterministic navigation stage. Simple requests to
open Store, create a Chrome tab or visit Netflix execute before inference. Store
uses `ms-windows-store://home` and verifies a foreground Store window, including
Windows 10's UWP frame-host case. Browser actions reuse an accessible existing tab
or navigate to the target URL. A new-tab request requires creation evidence.
The local model cannot veto those operations because another app/site is visible.

Every action still passes the configured permission tier and Stop check. Browser
fallbacks try automatic/native/CDP paths, report concrete outcomes and keep the
goal active after that initial ladder. No default global step/runtime cap was
introduced. Uncertain form submissions, scripts and deletions are not replayed.

Long goals retain the original instruction after the opening step. The worker
rejects success before navigation is verified or before further task work has
happened, and asks for a fresh full-goal completion check. The schema requires an
action after premature success/impossibility claims. This improves persistence;
it cannot make every model reliable on arbitrary websites. CAPTCHAs, sign-in,
protected desktops and missing applications can still require user assistance.

Regression tests cover the supplied transcripts without Ollama. The frozen
Windows browser probe uses local pages and a disposable profile to exercise CDP
and native tab switching/new-tab/address navigation. No Netflix account or
external website is required. Existing installer upgrade/repair checks remain.

Install by running the new setup EXE over the existing version. Saved models,
recipes and logs remain in place; see [installation](installation.md).


## Open-source computer use

The default AI engine now integrates [Windows-Use](https://github.com/Jeomon/Windows-Use)
0.8.1 at a pinned commit. Its cached Windows accessibility tree exposes the
foreground window, other open windows and interactive controls to local Ollama.
Tool-capable models use native tool calls; existing local vision models use the
SDK's structured response path. A legacy planner remains selectable under the AI
gear beside Send. Game Mode keeps its specialized input loop.

The installer includes the audited local SDK subset and its MIT/Apache licences.
No Windows-Use cloud provider, API key, subscription or telemetry is enabled.
All actions pass GhostOS's permissions, completion checks and Stop handling;
upstream fixed step/failure limits are not used. See the [integration provenance](../ghostos_vendor/windows_use/UPSTREAM.md).

This is an integration with an open-source engine, not ChatGPT's proprietary
computer-use model. Performance and complex-task reliability depend on the local
model and available Windows/browser accessibility information.
