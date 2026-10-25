# GhostOS v1.4.3 — correctly grounded browser clicks

## Fixed from real user logs

A request to open YouTube and select the first video previously yielded repeated
`ValueError: Coordinate outside latest screenshot`, followed by physical
Windows clicks unrelated to the actual DOM. GhostOS had mixed a resized Windows
desktop screenshot with the browser's Playwright/CDP automation.

**Managed browsers now use a single coherent coordinate system:** Playwright
captures the web viewport as CSS pixels. The agent sees a screenshot of that
specific viewport. The model can select a numbered visible DOM target and click
it with Playwright's locator actionability checks, or use a browser viewport
pixel which is converted from that same screenshot.

This removes the Windows desktop scaling and crop-origin mismatch from
browser actions. Invalid points and non-interactive hit targets are rejected
with useful geometry rather than triggering wrong clicks.

### Browser/navigation improvements

- Browser snapshot includes visible clickable DOM target IDs, labels, hrefs,
  CSS viewport dimensions, video-link count and visible dialogs.
- Links to videos are prioritized when the user asks to click the first video.
- Click-target IDs are revalidated against live DOM identity immediately before
  action; stale destinations cannot be silently clicked.
- When DOM targets exist, the Windows-Use model is offered browser DOM controls
  rather than confusing native UIA/Win32 click tools.
- Browser mouse moves, clicks and scrolling use CDP, not the physical OS mouse.
- Task event logs record screenshot source, coordinates and image dimensions.
- Source regression tests reproduce the screenshot-size error. A local
  synthetic-browser smoke probe also tests a first-video DOM click.
- Existing personal Chrome tabs without CDP remain in native control mode.

### Visual polish

The bottom-right ghost has richer state-specific expressions, smoother floating,
reactive glow, orbiting particles and updated labels. Desktop styling features
improved contrast, input focus, buttons, card backgrounds and scrollbar colours.

## Install

Download **GhostOS_Installer_v1.4.3.exe** from
[GitHub Releases](https://github.com/colin515/GhostOS/releases/tag/v1.4.3)
once GitHub publishes the installer. Run it over your existing GhostOS install.
Local settings and Ollama model downloads are preserved. The installer is unsigned.

## What remains to verify

The source regression tests passed in CI on Windows and Linux. The release build
compiles and publishes the installer; it is intentionally not gated on the
previous lengthy local-model and upgrade smoke tests.

The uploaded YouTube log itself shows a watch-history-disabled homepage and a
cookie-consent prompt. A first visible video can be genuinely absent; this
is distinct from click targeting. Protected desktops, inaccessible native apps,
games and custom canvases may still require other input strategies. The installed
build has not been tested on the user's own display, so performance there
cannot be guaranteed.

For the analysis and research sources, see [browser grounding](browser_grounding.md).
