# GhostOS v1.4.1 — precision clicks and animated agent UI

## Changes

- A vision-predicted click near one unique actionable Windows UI Automation
  element now prefers the element's **live physical centre**. Existing safeguards
  reject stale elements, changed windows and unexpected visual differences.
  Ambiguous or inaccessible targets retain their existing visual fallback.
- Physical Windows cursor APIs now align pointer commands with physical
  screenshot/UIA coordinates to reduce DPI-scaling mistakes.
- A blinking animated ghost replaces the rectangular bottom-right task Stop
  panel, with visible thinking, working, moving, waiting, listening and recovery
  states. Click it to stop, or use the existing emergency keyboard shortcuts.
- A separate click-through animated ghost pointer highlights the agent's cursor
  activity without changing the user's system cursor settings. Windows still
  has one system cursor for input.
- New click-centre, overlay and hit-testing regression coverage.

## Install or update

Download `GhostOS_Installer_v1.4.1.exe` from the [v1.4.1 GitHub release]
(https://github.com/colin515/GhostOS/releases/tag/v1.4.1) when its automated
Windows release build has published the asset. Run it over the previous
installation; there is no need to uninstall first. Your settings and local
models are preserved. The Windows installer remains unsigned.

## Validation and limits

Automated Linux/Windows tests cover the new code paths. The Windows release
workflow builds, installs, tests and uninstalls the packaged application before
publishing. Some behaviour, including different DPI/multi-monitor
configurations, third-party applications, protected desktops and games, still
requires hands-on validation on representative Windows PCs.

The new snapping logic is intentionally conservative. An inaccessible,
canvas-rendered or ambiguous target may still require visual estimation, and
some games reject injected system input. No general-purpose desktop agent can
guarantee completion of arbitrary tasks or games.
