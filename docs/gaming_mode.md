# Gaming mode · GhostOS 1.0.0

Launch `python main.py --game --desktop`, or select Game Mode in Settings before
starting a run. After submitting a goal, focus your game during the three-second
startup delay. Use windowed or borderless mode on the primary monitor. The engine
pins its input target to the foreground window when the first game action runs.
If that window loses focus, it refuses more game input for that run.

The native driver uses PyDirectInput scan-code key events and a correctly sized
Win32 SendInput union for relative mouse movement. Each key hold is capped at two
seconds and checks cancellation/focus every 50 ms. Keys release in `finally`;
the supervisor releases held input again after emergency termination. Relative
movement is a delta, not a screen position; Windows/game sensitivity and raw-input
settings affect camera rotation. Tune `dx`/`dy` in short bursts.

Screenshots and OpenCV matching poll at `game_poll_hz` (default 10 Hz, maximum 30)
between model decisions. Vision context is refreshed on each planning step, with
a default three-second observation period between them. These are **not** claims
of 10 vision-model decisions per second. Local model latency dominates complex
strategy. UIA snapshots and coordinate grids are disabled in this mode.

Put cropped PNGs in `%LOCALAPPDATA%\GhostOS\templates`. Filenames may contain
letters, digits, underscores and hyphens. Example model-free recipe step:

```yaml
- kind: template_click
  args: {name: menu_button.png, threshold: 0.9}
```

Templates use primary-monitor physical resolution and are resized along with the
screenshot. Templates must match the same game UI scale and appearance. Five
available templates are polled for observations; `template_click` freshly matches
the named one at dispatch time. Uniform/oversized images are rejected. Click
centres translate back to physical coordinates. Permission checks still apply.
Template matches inform the next planner step; they do not start an unbounded
background click loop.

Example game input actions:

```json
{"kind":"game_move","args":{"dx":70,"dy":-15}}
{"kind":"game_key","args":{"key":"w","duration":0.3}}
{"kind":"game_click","args":{}}
```

Balanced mode asks about game keys/clicks; Tier 3 permits continuous recipe steps
without per-action approval. Stop via Ctrl+Alt+K or the phone dashboard. Test
input, loss-of-focus and the stop control in a harmless offline session before
long runs. Protected games may reject synthetic input. No anti-cheat bypass,
process injection, driver installation or claim of universal Roblox/Minecraft
compatibility is included.
