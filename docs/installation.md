# Installation · GhostOS 1.0.0

## Prerequisites

Windows 10/11 x64, a standard user session, Microsoft Edge, current graphics
drivers, and Ollama running locally. Python 3.11 x64 is required for source builds
only. Internet is used to install packages and download models; subsequent model
inference, screenshots and speech transcription stay local. Browser tasks use
the network addresses requested by the user.

Use the source setup in README, or install the GitHub Release executable. The
installer is per-user and requests no elevation. It does not silently install
Ollama, GPU drivers, voice models, scheduled tasks, firewall rules or certificates.
It is unsigned. Verify the release SHA256SUMS file; do not assume SmartScreen
will trust a newly published binary. Bundled binaries do not require Python.

## First run

1. Open GhostOS normally, never as Administrator.
2. The wizard measures CPU throughput, inventories RAM and checks NVIDIA VRAM
   where `nvidia-smi` is available. AMD/Intel inventory may not expose reliable
   dedicated memory; the wizard reports unknown rather than guessing.
3. Install/start Ollama using the displayed official download link if missing.
4. Choose an exact installed model tag, or click Download selected model. The
   button explicitly approves a potentially large download. Ollama pulls through
   its streaming local API, equivalent to `ollama pull MODEL`.
5. Optionally check voice download. `faster-whisper` is a Python package, **not**
   an Ollama model. Its CTranslate2 Whisper weights download from Hugging Face.
6. Save after the selected vision tag appears in the local model inventory.

The default small-context budget is 8,192 tokens with one latest screenshot.
32B weights are about 21 GB. A 16 GB GPU needs offload for that model, and games
also need VRAM; use the smaller model if latency or memory pressure is high.
These inventory-based recommendations cannot guarantee a model will fit.

## Configuration and recovery

`%LOCALAPPDATA%\GhostOS\settings.json` is atomically replaced when settings save.
The CLI `--tier` and `--game` overrides apply to that invocation. Application data
is never written under Program Files or the installation directory. Logs are
`logs/run_TIMESTAMP/events.jsonl` beneath the data directory. Token, browser
profile, model cache and logs must not be committed to Git.

`GhostOS.exe --diagnostics` performs a non-invasive module/resource smoke check.
It does not start inference or manipulate the screen. For terminal output from a
frozen build, build with `python build_tools/build.py --console`; the release
executable automatically hides a console it owns, while preserving output when
started in an existing terminal. Source CLI runs use `python main.py`.

If Ollama is unavailable, start the Ollama desktop app and rerun setup. If a model
name is rejected, inspect `ollama list`; `qwen2.5vl:7b` is valid, `qwen2.5-vl:7b`
is not. For protected apps, UAC, locked sessions or elevated targets, finish the
step manually and provide a new goal. GhostOS does not bypass those boundaries.

## Uninstallation

Use Windows Installed apps or the Start Menu Uninstall shortcut. Inno removes
installed binaries and shortcuts. User data and external model caches are kept.
To remove everything, stop GhostOS, remove any `GhostOS-*` scheduled tasks you
registered, uninstall, and manually delete `%LOCALAPPDATA%\GhostOS`. Ollama and
its model cache have their own uninstall process. No uninstaller recursively
deletes unrelated directories or installed applications.

## Release process

Set `VERSION` to a three-component version, commit it, and push a matching tag.
`.github/workflows/release.yml` rejects mismatches. The installer version, binary
version resource, documentation archive name and release name share that value.
The attached ZIP contains the docs from the exact tagged commit. Source remains
available in GitHub's automatic source archives. CI also captures the exact
resolved package versions so the build environment can be inspected. Ranged
requirements are not a complete reproducible lockfile; independently review
dependency updates before a public release.
