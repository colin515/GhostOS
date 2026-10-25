# GhostOS v1.4.2 — target-verified mouse clicks and Chrome integration

This release packages the fixes merged into `main` after v1.4.1.

## Mouse targeting

- Accessibility clicks resolve to a live point confirmed via Windows UI Automation
  hit testing, rather than trusting a potentially inaccurate bounding-box centre.
- If a button's centre hits an overlay or unrelated control, GhostOS tests other
  points **inside the same target**; if it cannot confirm the target, it does not click.
- The target is hit-tested again just before the mouse button is pressed.
- Windows UI Automation discovery prioritises clickable controls in deep trees,
  reducing missed buttons caused by hundreds of non-interactive panes.
- Mouse messages report dispatched actions, not unverified task completion.

## Chrome / Edge

- New browser automation flows use a managed local Playwright/CDP profile where
  available, which can click and fill actual DOM controls without pixel guessing.
- When a requested site is already open in a personal browser tab, GhostOS can
  reuse that tab; existing personal tabs without debugging support are controlled
  by live accessibility and mouse/keyboard fallback.
- Browser selectors must identify exactly one element before click/fill; failed
  or uncertain form submissions are not automatically replayed.

## Installation

Download `GhostOS_Installer_v1.4.2.exe` from the
[official v1.4.2 release](https://github.com/colin515/GhostOS/releases/tag/v1.4.2)
once the Windows release workflow has published it. Run over an existing GhostOS
installation; valid settings, local models and previous logs remain on disk.
The installer is unsigned; verify it using the attached SHA256SUMS.txt.

## Validation and limitations

The source changes passed the project's automated Linux and Windows test suites.
The release workflow additionally builds and tests the packaged installer before
publishing. A CI pass does not guarantee every third-party app, custom control,
DPI configuration, browser site or game can be controlled. GhostOS still
observes permissions, protected desktop boundaries and explicit user approvals.
