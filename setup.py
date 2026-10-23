"""Interactive application configuration (not a setuptools packaging script)."""
from __future__ import annotations
from config import Settings
from agent.hardware import hardware_report, ollama_status, benchmark_model
from agent.runtime import local_ip

MODELS = ['qwen3.5:4b', 'qwen3-vl:4b', 'qwen3-vl:8b', 'qwen3.5:2b',
          'qwen2.5vl:7b', 'qwen2.5vl:32b', 'llama3.2-vision:11b', 'llava:7b', 'qwen2.5vl:3b']


def download_model(settings, model, progress=print):
    import ollama
    if model.lower().endswith('cloud'):
        raise ValueError('Choose a local model; cloud model tags are disabled')
    client = ollama.Client(host=settings.ollama_host, timeout=120, trust_env=False)
    try:
        for part in client.pull(model, stream=True):
            percent = f' {100 * part.completed / part.total:.0f}%' if part.total and part.completed else ''
            progress((part.status or 'Downloading') + percent)
    except Exception as exc:
        raise RuntimeError('Model download failed. Update Ollama from https://ollama.com/download/windows, '
                           'check its connection, and retry. qwen3-vl:4b is an alternative for older Ollama versions. '
                           + str(exc)[:300]) from exc


def download_voice(settings, progress=print):
    from faster_whisper.utils import download_model as download_whisper
    progress('Downloading local Whisper speech model from Hugging Face…')
    target = settings.data_dir / 'voice-model'
    target.mkdir(parents=True, exist_ok=True)
    download_whisper(settings.whisper_model, output_dir=str(target))
    progress('Voice model ready. Transcription stays local.')


def run_console(settings):
    import json
    report = hardware_report()
    status = ollama_status(settings.ollama_host)
    print(json.dumps(report, indent=2))
    print(f'LAN dashboard address: http://{local_ip()}:{settings.web_port}')
    if not status['reachable']:
        print('Install/start Ollama: https://ollama.com/download/windows then run setup again.')
        return 1
    print('Installed models:', ', '.join(status['installed_models']) or '(none)')
    model = input(f'Model [{report["recommended_model"]}]: ').strip() or report['recommended_model']
    if model not in status['installed_models']:
        if input(f'Download {model}? This can use many GB. [y/N] ').lower() != 'y':
            return 1
        download_model(settings, model)
    from agent.brain import ensure_local_vision, local_model_metadata
    ensure_local_vision(local_model_metadata(settings.ollama_host, model))
    from agent.model_setup import verify_model
    print(json.dumps(verify_model(settings, model), indent=2))
    if input('Benchmark selected local vision model (may take up to 120 seconds)? [y/N] ').lower() == 'y':
        print(json.dumps(benchmark_model(settings, model), indent=2))
    if input('Download optional local voice model? [y/N] ').lower() == 'y':
        download_voice(settings)
        settings.voice_enabled = True
    settings.model, settings.setup_complete = model, True
    settings.save()
    print('Setup complete. Launch: python main.py --desktop')
    return 0


if __name__ == '__main__':
    raise SystemExit(run_console(Settings.load()))
