"""Bound observations before Ollama truncates the goal or latest action outcome."""
from __future__ import annotations
import json


def clip(text, limit):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit - 100] + '\n[…trimmed…]\n' + text[-70:]


def browser_observation(raw):
    try:
        data = json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(data,dict):
            return clip(raw,1600)
        fields = ('transport','url','verified','operation','media','evidence','message','observation_warning')
        output = {k:data[k] for k in fields if k in data}
        output['text'] = clip(data.get('text',''),1000)
        output['tabs'] = [{k:clip(v,180) if isinstance(v,str) else v for k,v in tab.items()}
                          for tab in data.get('tabs',[])[:10]]
        output['controls'] = data.get('controls',[])[:25]
        return output
    except (ValueError,TypeError):
        return clip(raw,1600)


def pack_prompt(goal, history, observation, browser, feedback, screenshot_size, settings, system_chars, tool_chars=0):
    # Reserve room for the image, action output, system instructions and tool schemas.
    budget = max(1800, int((settings.context_tokens - settings.prediction_tokens - 1500) * 3) - system_chars - tool_chars)
    data = {'goal':goal, 'history':clip(history,2200), 'desktop':observation,
            'browser':browser_observation(browser), 'feedback':clip(feedback,1800),
            'screenshot_size':screenshot_size, 'game_mode':settings.game_mode}
    # Copy provider data before trimming; cached SDK observations remain untouched.
    data = json.loads(json.dumps(data,ensure_ascii=False,default=str))
    def size():
        return len(json.dumps(data,ensure_ascii=False))
    if size() > budget:
        data['history'] = clip(history,700)
    desktop = data['desktop']
    if isinstance(desktop,dict):
        for key in ('controls','fallback_ui_tree','windows'):
            nodes = desktop.get(key)
            if isinstance(nodes,list):
                while len(nodes) > 1 and size() > budget:
                    nodes.pop()
    elif isinstance(desktop,list):
        while len(desktop) > 1 and size() > budget:
            desktop.pop()
    if size() > budget and isinstance(data['browser'],dict):
        data['browser']['text'] = clip(data['browser'].get('text',''),300)
        for key in ('controls','tabs'):
            nodes = data['browser'].get(key,[])
            while len(nodes) > 1 and size() > budget:
                nodes.pop()
    if size() > budget:
        data['history'] = ''
        data['feedback'] = clip(feedback,700)
    data['context_trimmed'] = data['desktop'] != observation or data['history'] != history
    return json.dumps(data,ensure_ascii=False)
