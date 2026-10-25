# GhostOS v1.4.4 — goal-driven website interactions and windowed game menus

## Fix: YouTube keeps reopening instead of searching

A request to **open YouTube, search for lo-fi music, and click the first video**
is three separate steps. The current version handles the navigation prerequisite
once, then uses DOM-backed `browser_search` in the *existing* CDP browser tab
and verifies the search results URL. The following step uses
`browser_first_video` to select a visible YouTube result and checks that
the destination is a real video watch URL. It does not repeatedly reopen
YouTube's home page. The model also no longer receives redundant navigation
tools when the current step is a search or form task.

The agent can now use `browser_fill_target` and `browser_press_target` with
specific indexed form elements from a fresh snapshot, in addition to the
existing unique-selector-based fill/click tools. Uncertain submissions
are still not replayed automatically and remain subject to user approvals.

## Fix: windowed games click random locations

- Game screenshots capture the foreground **game client area** (the content)
  and record its actual Windows screen origin rather than capturing title bar
  and window borders.
- Menu clicks use `game_menu_click` with coordinates from the observed client
  image. The click's physical target must belong to that same focused window.
- A coordinate grid helps the local vision model choose a location in the
  screenshot. Existing camera-relative movements are not used as menu aiming.
- Blind `game_click`, generic desktop clicks and camera controls are blocked
  when the stated task is a new-game or difficulty menu.
- A fresh screenshot is observed after each click. If three menu clicks
  cause no meaningful scene change, automation stops rather than clicking
  indiscriminately.

## Open-source evaluation

We reviewed browser-use, Playwright, Microsoft UFO and OmniParser. GhostOS
already uses Playwright and has a Windows-Use/UIA integration; these targeted
changes use those components rather than adding a heavyweight grounding
model and dependencies to the installer. For custom game canvases, local
visual recognition is still the primary bottleneck.

## Installation

Download **GhostOS_Installer_v1.4.4.exe** from
[GitHub Releases](https://github.com/colin515/GhostOS/releases/tag/v1.4.4)
after publishing. Install over the existing GhostOS app; models and settings
remain in the user data folder.

## Limitations and testing

Automated Windows and Linux checks exercise task decomposition, direct
search/video navigation, and game-client coordinate transforms, but they
cannot demonstrate successful gameplay in every third-party game.
Another Brick in the Mall is a custom-engine game, and complex commands
such as designing a functional supermarket and placing furniture require
interactive screen interpretation and game-specific procedures not
delivered by a generic menu-click patch. A user's own desktop remains the
final integration test. A completed action means input was dispatched,
not that the requested objective was achieved.
