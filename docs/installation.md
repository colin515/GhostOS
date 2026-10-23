# Installation · GhostOS 1.0.1

## Prerequisites

Windows 10/11 x64, a standard user session, Microsoft Edge, current graphics
drivers, and Ollama running locally. Python 3.11 x64 is required for source builds
only. Internet is used to install packages and download models; subsequent model
inference, screenshots and speech transcription stay local. Browser tasks use
the network addresses requested by the user.

Download **GhostOS_Installer_v1.0.1.exe** from the
[latest GitHub Release](https://github.com/colin515/GhostOS/releases/latest), run
it, and open GhostOS from the Start Menu. Choose the `.exe` under **Assets**;
the source ZIP is for developers. No Python installation is needed. The
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
6. Optionally click **Benchmark selected model**. This measures a short local
   vision request using a synthetic image, reports model load time and output
   tokens per second, and checks actual GPU memory residency through Ollama.
   It does not download another model or capture your desktop. Slow model loads
   may reach the 120-second request timeout; choose a smaller model if needed.
7. Save after the selected vision tag appears in the local model inventory.
   Setup checks local-only metadata and vision capability before saving.

GhostOS rejects cloud-tagged models and inspects local model metadata before
sending any goal or screenshot. A remote alias or a model without vision support
is refused. Ollama HTTP clients ignore proxy environment variables for loopback
requests. For an additional server-wide local-only setting, set
`OLLAMA_NO_CLOUD=1` in Ollama's own environment and restart Ollama; see the
[official Ollama FAQ](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
GhostOS does not change the settings of a separately running Ollama server.

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

Set `VERSION` to a new three-component version, commit it, and push to `main`.
The workflow creates the matching tag and publishes the installer automatically.
A matching tag push or a manual **Windows release** workflow run from `main`
is also supported. Tag/version mismatches and runs from other branches fail.
Published releases are immutable in this workflow; use a new version rather
than replacing an existing release. The installer version, binary
version resource, documentation archive name and release name share that value.
The attached ZIP contains the docs from the exact tagged commit. Source remains
available in GitHub's automatic source archives. CI also captures the exact
resolved package versions so the build environment can be inspected. Ranged
requirements are not a complete reproducible lockfile; independently review
dependency updates before a public release.
