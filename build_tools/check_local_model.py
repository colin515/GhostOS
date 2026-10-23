"""Release check against real local weights; never captures or controls the runner."""
from pathlib import Path
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from config import Settings
    from agent.model_setup import verify_model
    import ollama
    model = 'qwen3.5:0.8b'
    reports = []
    with tempfile.TemporaryDirectory(prefix='GhostOS-model-check-') as root:
        for engine in ('windows_use','native'):
            settings = Settings(data_dir=Path(root),computer_use_engine=engine,context_tokens=8192)
            reports.append(verify_model(settings,model,print))
    client = ollama.Client(host='http://127.0.0.1:11434',timeout=10,trust_env=False)
    try:
        digest = next(item.digest for item in client.list().models if item.model == model)
    finally:
        client._client.close()
    output = {'model':model,'digest':digest,'reports':reports,
              'scope':'Real CPU model protocol checks; no desktop input. Does not benchmark the recommended 4B model or an 8 GB GPU.'}
    target = ROOT / 'dist' / 'local-model-verification.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()
