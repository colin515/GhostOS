"""Exercise the selected local planner without capturing or controlling the PC."""
from __future__ import annotations
from dataclasses import replace
from PIL import Image, ImageDraw
from agent.vision import Frame


def verify_model(settings, model, progress=print):
    candidate = replace(settings, model=model)
    progress('Checking local vision support and the actual agent action protocol…')
    image = Image.new('RGB', (512, 256), '#17171b')
    ImageDraw.Draw(image).text((30, 110), 'GHOSTOS SETUP TEST - NO DESKTOP ACCESS', fill='white')
    planner = None
    try:
        if candidate.computer_use_engine == 'windows_use':
            from agent.windows_use_engine import WindowsUseBrain
            planner = WindowsUseBrain(candidate, observe=False)
            client = planner.llm.client
        else:
            from agent.brain import Brain
            planner = Brain(candidate)
            client = planner.client
        decision = planner.next('This is an inert setup self-test. Return exactly one wait action with seconds:0.0. '
                                'Do not finish, click, type or run commands. No tool will be executed.',
                                Frame(image, image.size), [], feedback='DECISION_ACTION_REQUIRED')
        if not decision.action or decision.action.kind != 'wait' or decision.action.args['seconds'] != 0:
            raise ValueError('The model did not follow the agent protocol test. Try qwen3.5:4b or qwen3-vl:4b and update Ollama.')
        report = {'model': model, 'agent_protocol': 'passed', 'engine': candidate.computer_use_engine,
                  'desktop_capture': False, 'actions_executed': 0, 'model_vram_gb': None,
                  'execution': 'GPU offload not verified'}
        try:
            canonical = model if ':' in model.rsplit('/', 1)[-1] else model + ':latest'
            loaded = next((item for item in client.ps().models if item.model in (model, canonical)), None)
            if loaded is not None and loaded.size_vram is not None:
                report['model_vram_gb'] = round(loaded.size_vram / 1024**3, 2)
                report['execution'] = 'GPU offload observed' if loaded.size_vram > 0 else 'CPU only observed'
        except Exception:
            report['execution'] = 'GPU offload not verified'
        report['note'] = 'The installed model produced a valid inert action. This test does not prove arbitrary task accuracy.'
        progress('Model verification passed. No desktop input was sent.')
        return report
    finally:
        if planner:
            planner.close()
