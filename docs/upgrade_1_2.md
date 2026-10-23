# GhostOS 1.2.1 changes

- Chat hides for every run; completion never steals focus. Explicit tray restore,
  non-activating task/approval panels and a click-through yellow screen border.
- Verified Windows foreground recovery and direct executable launch replace
  Windows Search/Alt+Tab recovery. Own UI windows are excluded as input targets.
- CDP-first Chrome/Edge with an automatic separate loopback profile, persistent
  result tabs, native fallback warning and optional setup help.
- Smooth, verified native cursor motion; five mouse buttons, double click,
  drag/drop and both scroll axes, with physical-coordinate debug events.
- Unlimited steps and total runtime by default, including migration from old
  defaults. Model blockers/errors re-observe and retry with cancellable backoff.
- AI-only controls beside Send; voice and dashboard settings in the header.
  Custom multi-resolution GhostOS icon in the EXE, taskbar, shortcuts and setup.
- Bundled offline Piper neural voice, automatic VAD, reactive microphone waveform,
  immediate acknowledgment, optional narration and request-scoped voice approval.

Windows secure desktops/UAC and protected input remain manual. A vision model
can choose an incorrect target or misjudge completion; start with Strict mode.
See [architecture](architecture.md), [browser help](browser_control.md), and
[validation](validation.md) for implementation and test scope.
