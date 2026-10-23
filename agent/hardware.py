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
        client = ollama.Client(host=host, timeout=5)
        names = [item.model for item in client.list().models]
        loaded = [{'model': model.model, 'vram_bytes': model.size_vram} for model in client.ps().models]
        return {'reachable': True, 'installed_models': names, 'loaded_models': loaded}
    except Exception as exc:
        return {'reachable': False, 'installed_models': [], 'error': str(exc)}
