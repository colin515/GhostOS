# Bundled speech attribution

GhostOS is GPL-3.0-or-later. Its Windows installer bundles:

- Piper 1.3.0 (GPL-3.0), OHF-Voice contributors:
  https://github.com/OHF-Voice/piper1-gpl/tree/v1.3.0
  Python API: https://github.com/OHF-Voice/piper1-gpl/blob/v1.3.0/docs/API_PYTHON.md
- Piper's embedded eSpeak NG phonemizer (GPL-3.0), with upstream data and source:
  https://github.com/espeak-ng/espeak-ng
- ONNX Runtime (MIT): https://github.com/microsoft/onnxruntime
- LJSpeech-medium voice from rhasspy/piper-voices (repository metadata MIT),
  trained by Bryce Beattie using the public-domain LJ Speech dataset.
  Pinned revision: bae641dcb5a608cff81ccaf7ff018baaca1a33e1.
  https://huggingface.co/rhasspy/piper-voices/tree/bae641dcb5a608cff81ccaf7ff018baaca1a33e1/en/en_US/ljspeech/medium
  Dataset: https://keithito.com/LJ-Speech-Dataset/

The exact voice model card and repository metadata ship under assets/voice.
The build script verifies model SHA-256:
`6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22`.

Synthesis runs locally; no audio/text is sent to a hosted speech provider.
ONNX Runtime telemetry is disabled before model initialization.
