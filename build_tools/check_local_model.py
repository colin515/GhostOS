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
    model = 'qwen3.5:4b'
    reports = []
    with tempfile.TemporaryDirectory(prefix='GhostOS-model-check-') as root:
        for engine in ('windows_use','native'):
            settings = Settings(data_dir=Path(root),computer_use_engine=engine,context_tokens=8192,inference_timeout=300)
            reports.append(verify_model(settings,model,print))
        from PIL import Image,ImageDraw
        from agent.vision import Frame
        from agent.windows_use_engine import WindowsUseBrain
        image = Image.new('RGB',(512,256),'#20212a')
        draw = ImageDraw.Draw(image)
        draw.rectangle((60,90,200,160),fill='#d4d9ff')
        draw.text((105,116),'Play',fill='black')
        draw.rectangle((280,90,440,160),fill='#555762')
        draw.text((325,116),'Cancel',fill='white')
        frame = Frame(image,(1024,512),origin=(-600,200))
        targets = [{'id':7,'name':'Play','type':'ButtonControl','bounds':[-480,380,-200,520]},
                   {'id':8,'name':'Cancel','type':'ButtonControl','bounds':[-40,380,280,520]}]
        planner = WindowsUseBrain(Settings(data_dir=Path(root),model=model,inference_timeout=300),observe=False)
        try:
            decision = planner.next('Click the Play button. Use ui_click with its current accessibility id. Never click Cancel.',frame,targets,feedback='DECISION_ACTION_REQUIRED')
            if not decision.action or decision.action.kind != 'ui_click' or decision.action.args['element_id'] != 7:
                raise RuntimeError('The real model failed to ground the requested Play control: ' + str(decision))
            reports.append({'grounding':'passed','target':'Play','element_id':7,'actions_executed':0})
        finally:
            planner.close()
    client = ollama.Client(host='http://127.0.0.1:11434',timeout=10,trust_env=False)
    try:
        digest = next(item.digest for item in client.list().models if item.model == model)
    finally:
        client._client.close()
    output = {'model':model,'digest':digest,'reports':reports,
              'scope':'Real recommended 4B model on CPU: tool calls, structured vision output and named accessibility grounding. No desktop input; does not measure the user GPU or arbitrary game skill.'}
    target = ROOT / 'dist' / 'local-model-verification.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()
