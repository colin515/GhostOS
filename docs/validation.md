# Validation and release readiness · GhostOS 1.0.0

## Verified in the development environment

The initial validation runs on Linux/Python 3.12 with Windows APIs isolated in
tests. This does not certify the Windows desktop or game drivers.

- 56 automated tests passed; the native Win32 INPUT structure-size test is skipped
  outside Windows. Tests cover permission tiers, rejection of untrusted action
  fields, decline/timeout/cancellation, one-time approvals, action/recipe schemas,
  exact step-budget completion, observe/execute/terminal states, DPI coordinate
  transforms, template matching, context/event bounds, scheduler XML, authenticated
  dashboard routes, WebSocket pairing, origin checks and concurrent goal rejection.
- Python compilation and the configured Ruff error checks passed.
- PyQt6 constructed and rendered the desktop through the offscreen platform plugin.
  This checks layout/construction; it does not verify Windows focus or accessibility.
- The source CLI returns the version and reads its packaged resource paths.

The version 1.0.0 core CI passed on Windows and Linux, and Windows package
validation passed for commit `db9273353d0110d8e53e425a94e2d5196f8197d8`
([run 39988840202](https://github.com/colin515/GhostOS/actions/runs/39988840202)).
Changes pushed to main run core tests; release builds run the complete Windows
packaging and installation checks again. The packaging job installs full dependencies, freezes the application,
compiles Inno Setup, silently installs, checks the installed resources/imports,
uninstalls and uploads a preview installer artifact. A queued or failed workflow
is not a passing build. Automatic main-branch version releases and tagged releases run their own
packaging/validation before publication.

## Manual Windows acceptance before promoting a release

Use an ordinary, unlocked desktop session with no valuable documents open.

| Check | Expected result |
| --- | --- |
| Fresh per-user installation | Modern wizard, Start Menu entry, no admin request |
| First launch without Ollama | Working official download link, no silent install |
| Model download | Explicit button/console approval; progress; exact local tag saved |
| Notepad recipe at Tier 1 | Each step prompts, typing reaches Notepad after approval |
| Balanced browser navigation | Page opens; filling/clicking prompts once |
| Declined or timed-out action | No input sent; run terminates with permission status |
| Mobile pairing | No frames/logs before token; goal and approval share desktop state |
| UAC/elevated target | No secure-desktop automation, manual completion required |
| DPI at 100/125/150/200% | Target pixels map to the primary-monitor image correctly |
| Game target loses focus | Game input stops rather than controlling another app |
| Long key hold / PowerShell child | Emergency hotkey stops run, releases inputs, terminates owned children |
| Frozen launch | All Qt/COM/Playwright/voice modules import; local resources resolve |
| Daily task / watched directory | Finite single run; no overlap, no log-trigger loop |
| Uninstall | Installed files/shortcuts removed; personal app data remains |

These checks need real Windows 10/11, representative GPUs and the intended games.
A GUI screenshot, mocked controller or CI smoke check cannot prove them.

## Known operating limits

Primary-monitor targeting only. There is no OCR engine separate from the vision
model. UIA providers, game input acceptance and browser authentication depend on
the target app. UIA is bounded by node/depth caps and the supervisor's run timeout,
not a guarantee of zero-latency reads. Model inference speed and task success vary
with hardware and model ability. Game polling is faster than inference; the model
is not a high-frame-rate controller. Automated tests do not require actual screen
input or private user data.

Tier 3 is user-authority arbitrary command execution, not a sandbox. It cannot
guarantee rollback or stop remote/detached effects. Global hotkeys depend on the
normal Windows desktop; they cannot bypass a secure desktop or a frozen OS.
Task Scheduler screen runs need the user logged in and unlocked. Directory
watchers pause after the emergency brake until the watcher process is restarted
(or an explicit new goal resets the brake).

The installer is unsigned. Model licences, native dependencies and GPU drivers
have separate terms and requirements. Review the exact dependency inventory and
Windows validation results for each tagged build. The first implementation must
not be advertised as universally tested or production-certified.
