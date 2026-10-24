"""Local template policies run between model decisions and require observed victory."""
from __future__ import annotations
from pathlib import Path
import time
from pydantic import BaseModel, ConfigDict, Field, model_validator
from agent.models import Action

PNG = r'^[A-Za-z0-9_-]+\.png$'
ALLOWED = {'game_action','game_key','game_move','game_click','template_click','wait'}


class Rule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template: str = Field(pattern=PNG)
    threshold: float = Field(default=.92,ge=.7,le=1)
    cooldown: float = Field(default=.2,ge=.05,le=10)
    action: Action
    @model_validator(mode='after')
    def bounded_game_input(self):
        if self.action.kind not in ALLOWED:
            raise ValueError('Game profiles allow bounded game input, template clicks and waits only')
        return self


class GameProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=100)
    window_title: str = Field(min_length=3,max_length=160)
    success_template: str = Field(pattern=PNG)
    success_threshold: float = Field(default=.95,ge=.8,le=1)
    success_frames: int = Field(default=3,ge=2,le=30)
    rules: list[Rule] = Field(min_length=1,max_length=100)


def load_profile(path):
    import yaml
    path = Path(path)
    if path.suffix.lower() not in ('.yaml','.yml') or path.stat().st_size > 128 * 1024:
        raise ValueError('Game profile must be YAML smaller than 128 KB')
    return GameProfile.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))


def run_profile(controller, profile, emit, max_steps=0):
    from agent.gaming_engine import GamingEngine
    from agent.window_focus import focus_window, is_agent_window
    import win32gui
    matches = []
    def visit(hwnd,_):
        if win32gui.IsWindowVisible(hwnd) and not is_agent_window(hwnd) and profile.window_title.casefold() in win32gui.GetWindowText(hwnd).casefold():
            matches.append(hwnd)
    win32gui.EnumWindows(visit,None)
    foreground = win32gui.GetForegroundWindow()
    if foreground in matches:
        matches = [foreground]
    if len(matches) != 1:
        raise ValueError('Game profile target is missing or ambiguous. Open the game and use its exact window title.')
    focus_window(matches[0],controller.safety.stop)
    controller.game = GamingEngine(controller.safety.stop,target=matches[0])
    seen, actions, last_frame, last_wait = 0,0,0.,0.
    fired = {}
    emit('PLAN',message=f'Running game profile: {profile.name}. Completion requires its visible victory marker.')
    while not controller.safety.stop.is_set():
        controller.safety.check()
        try:
            controller.game.check_focus()
        except RuntimeError:
            emit('RECOVERY',message='The game lost focus. Restoring only the pinned game; no game input will go to another app.')
            try:
                controller.execute(Action(kind='focus'))
            except RuntimeError:
                controller.safety.stop.wait(.5)
            continue
        frame = controller.vision.capture()
        controller.frame = frame
        if frame.window != controller.game.target:
            controller.safety.stop.wait(.1)
            continue
        now = time.monotonic()
        if now - last_frame >= controller.settings.screenshot_interval:
            emit('FRAME',image=frame.base64())
            last_frame = now
        hit = controller.vision.match(frame,profile.success_template,profile.success_threshold)
        seen = seen + 1 if hit else 0
        if seen >= profile.success_frames:
            emit('RESULT',message=f'Victory marker verified across {seen} fresh frames.',profile=profile.name)
            return 'GOAL_SATISFIED'
        for index,rule in enumerate(profile.rules):
            if now - fired.get(index,0) < rule.cooldown or not controller.vision.match(frame,rule.template,rule.threshold):
                continue
            if max_steps and actions >= max_steps:
                return 'MAX_STEPS_EXCEEDED'
            result = controller.execute(rule.action)
            fired[index] = time.monotonic()
            actions += 1
            emit('RESULT',message=str(result),profile=profile.name,rule=index + 1)
            break
        else:
            if now - last_wait > 3:
                emit('PLAN',message='Waiting for a configured game marker; no speculative input is being sent.')
                last_wait = now
        controller.safety.stop.wait(1 / controller.settings.game_poll_hz)
    controller.safety.check()
    return 'STOPPED'
