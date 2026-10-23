"""Hardware inventory + a small measured CPU benchmark; GPU fit remains an estimate."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import time


def hardware_report():
    import psutil
    report = {'ram_gb': round(psutil.virtual_memory().total / 1024**3, 1),
              'available_ram_gb': round(psutil.virtual_memory().available / 1024**3, 1),
              'physical_cores': psutil.cpu_count(logical=False), 'logical_cores': psutil.cpu_count(),
              'gpus': [], 'vram_gb': 0.0, 'gpu_acceleration': 'not verified',
              'ollama_executable': shutil.which('ollama')}
    started = time.perf_counter()
    sum(i * i for i in range(500000))
    report['cpu_benchmark_ms'] = round((time.perf_counter() - started) * 1000, 1)
    try:
        output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total',
            '--format=csv,noheader,nounits'], text=True, timeout=5,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        for line in output.splitlines():
            name, memory = line.rsplit(',', 1)
            report['gpus'].append({'name': name.strip(), 'vram_gb': round(float(memory) / 1024, 1)})
        report['gpu_acceleration'] = 'NVIDIA driver detected; verify actual offload using ollama ps'
    except (OSError, subprocess.SubprocessError, ValueError):
        if os.name == 'nt':
            try:
                output = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                    'Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress'],
                    text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
                adapters = json.loads(output)
                if isinstance(adapters, dict):
                    adapters = [adapters]
                # AdapterRAM may truncate above 4GB; do not recommend a huge model from this value.
                for item in adapters or []:
                    report['gpus'].append({'name': item.get('Name'), 'vram_gb': None})
                report['gpu_acceleration'] = 'GPU detected; dedicated VRAM and Ollama acceleration unverified'
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
    report['vram_gb'] = max((gpu.get('vram_gb') or 0 for gpu in report['gpus']), default=0)
    vram = report['vram_gb']
    if vram >= 24 and report['ram_gb'] >= 32:
        report['recommended_model'] = 'qwen2.5vl:32b'
        report['model_note'] = '32B weights are about 21 GB; context and graphics need extra memory.'
    elif vram >= 8:
        report['recommended_model'] = 'qwen2.5vl:7b'
        report['model_note'] = '7B weights are about 6 GB. 32B on 16 GB requires CPU offload and can be slow.'
    else:
        report['recommended_model'] = 'llava:7b'
        report['model_note'] = 'CPU/partial GPU fallback; allow at least 8–16 GB free RAM. A 3B model may work better on small PCs.'
    return report


def ollama_status(host='http://127.0.0.1:11434'):
    import ollama
    try:
        client = ollama.Client(host=host, timeout=5, trust_env=False)
        names = [item.model for item in client.list().models]
        loaded = [{'model': model.model, 'vram_bytes': model.size_vram} for model in client.ps().models]
        return {'reachable': True, 'installed_models': names, 'loaded_models': loaded}
    except Exception as exc:
        return {'reachable': False, 'installed_models': [], 'error': str(exc)}


def benchmark_model(settings, model, progress=print):
    """Explicit local inference benchmark using a synthetic image, never the desktop."""
    from agent.brain import ensure_local_vision, local_model_metadata
    if not model.strip() or model.lower().endswith('cloud'):
        raise ValueError('Select an installed local vision model')
    progress('Checking that the selected model is local and supports vision…')
    ensure_local_vision(local_model_metadata(settings.ollama_host, model))
    import io
    import ollama
    import psutil
    from PIL import Image, ImageDraw
    sample = Image.new('RGB', (512, 256), '#182238')
    ImageDraw.Draw(sample).text((30, 110), 'GHOSTOS LOCAL VISION TEST', fill='white')
    image = io.BytesIO()
    sample.save(image, format='PNG')
    client = ollama.Client(host=settings.ollama_host, timeout=120, trust_env=False)
    progress('Loading the model and measuring local vision inference (up to 120 seconds)…')
    available_before = psutil.virtual_memory().available
    started = time.perf_counter()
    result = client.generate(model=model, prompt='Describe this test image in one short sentence.',
                             images=[image.getvalue()], stream=False, keep_alive='3m',
                             options={'temperature': 0, 'num_ctx': 2048, 'num_predict': 24})
    elapsed = time.perf_counter() - started
    tokens = result.eval_count or 0
    seconds = (result.eval_duration or 0) / 1_000_000_000
    report = {
        'model': model, 'wall_seconds': round(elapsed, 2),
        'load_seconds': round((result.load_duration or 0) / 1_000_000_000, 2),
        'generated_tokens': tokens,
        'tokens_per_second': round(tokens / seconds, 2) if seconds > 0 else None,
        'available_ram_before_gb': round(available_before / 1024**3, 2),
        'available_ram_after_gb': round(psutil.virtual_memory().available / 1024**3, 2),
        'gpu_acceleration': 'not verified', 'model_vram_gb': None,
        'note': 'Synthetic image, 2K context, short output. Actual desktop/game latency may differ.'}
    # Query after inference: hardware inventory alone does not prove GPU offload.
    try:
        canonical = model if ':' in model.rsplit('/', 1)[-1] else model + ':latest'
        loaded = next((item for item in client.ps().models if item.model in (model, canonical)), None)
        if loaded is not None and loaded.size_vram is not None:
            report['model_vram_gb'] = round(loaded.size_vram / 1024**3, 2)
            report['gpu_acceleration'] = 'GPU offload observed' if loaded.size_vram > 0 else 'CPU only observed'
    except Exception as exc:
        report['offload_check_error'] = str(exc)
    progress('Benchmark complete. The model stays loaded for up to three minutes.')
    return report
