# Gaming mode · GhostOS 1.4.0

Enable Game Mode in the AI gear beside Send. Use windowed or borderless mode.
Named Start Menu apps and games installed in Steam libraries can launch directly;
ambiguous names need an exact installed title. GhostOS pins game input to a real
external window and refuses to send it to another app after focus changes.
`game_bind` can bind the exact currently observed title when a launcher opens
its actual game in a different window.

## Try a complete, offline control test

1. Open the AI gear → **Open control practice game**.
2. Save settings. This enables Game Mode and selects `control-practice.yaml`.
3. Ask **Complete the practice game**. Approve input when your tier requires it.

The included game requires three precise moving-marker clicks, simultaneous
Shift+W, held right mouse plus relative camera movement, and a final click.
Completion requires its victory marker in three fresh captures. It is a local
fixture, not a claim that the model can solve every commercial game. Press Esc
in the game to close it. Release CI completes it with actual Windows input at
150% Qt scaling before publishing the installer.

From the installed app directory, you can also run:

```powershell
.\GhostOS.exe --practice-game
.\GhostOS.exe --game --game-profile control-practice.yaml --goal "Complete the practice game"
```

## Controls and timing

`game_action` holds multiple keys/buttons while moving the camera, for example:

```json
{"kind":"game_action","args":{"keys":["shift","w"],"buttons":["right"],"dx":40,"dy":0,"duration":0.2}}
```

PyDirectInput supplies scan-code keys; checked Windows SendInput supplies relative
mouse motion and buttons. Individual holds last at most two seconds and check
focus/cancellation frequently. Held inputs release in `finally`, including when
another release fails. The emergency brake also releases held input. Relative
motion is a delta; game sensitivity and raw-input settings affect camera rotation.

Profiles use fast OpenCV matching between slower model calls. Default polling is
10 Hz, configurable up to 30 Hz; this is not the model inference rate. UIA trees
and heavy grids are disabled in Game Mode. Steps and total run time default to
unlimited; optional limits remain in AI settings. Stop with Ctrl+Alt+K,
Ctrl+Alt+Esc, the task panel or the paired dashboard.

## Game-specific profiles

Profiles live under `%LOCALAPPDATA%\GhostOS\game_profiles`; PNG markers live in
`%LOCALAPPDATA%\GhostOS\templates`. Enter only the profile filename in AI settings.
The practice game generates working examples at your current display scale.
For another game, supply distinctive, tightly cropped screenshots at its actual
resolution. A simple profile looks like:

```yaml
name: Example level
window_title: Exact game window title
success_template: victory.png
success_threshold: 0.95
success_frames: 3
rules:
  - template: start-button.png
    threshold: 0.92
    cooldown: 0.5
    action:
      kind: template_click
      args:
        name: start-button.png
  - template: corridor.png
    action:
      kind: game_action
      args:
        keys: [w]
        duration: 0.2
```

Profiles accept bounded game input, template clicks and waits, with ordinary
permission checks. They cannot run terminal scripts. Missing or ambiguous windows
are reported; unmatched markers wait without speculative input. Focus recovery
restores only the pinned game. A victory template must be unique; a generic icon
can produce a false match. Recreate markers after changing scale, resolution or
graphics. Template matching is not a general 3D world model.

Model-driven finish/win requests independently inspect a fresh image for visible
victory or final credits before accepting completion. Opening a game, dispatching
input, or focusing it is insufficient. General gameplay still depends on the
model, mechanics and observable state. Whole-game completion needs a named game,
a defined objective and acceptance testing; no universal completion guarantee is
made. GhostOS does not bypass anti-cheat, protected input, UAC or secure desktops.
