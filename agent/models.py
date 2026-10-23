"""Untrusted model/recipe/API actions share this validation boundary."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Args(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Empty(Args):
    pass

class Keys(Args):
    keys: list[str] = Field(min_length=1, max_length=6)

class Text(Args):
    text: str = Field(max_length=16000)

class Click(Args):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    button: Literal['left', 'right'] = 'left'

class Shell(Args):
    script: str = Field(min_length=1, max_length=20000)
    timeout: int = Field(default=30, ge=1, le=120)

class Delay(Args):
    seconds: float = Field(ge=0, le=10)

class App(Args):
    name: str = Field(min_length=1, max_length=80)

class Element(Args):
    element_id: int = Field(ge=0, le=200)

class URL(Args):
    url: str = Field(min_length=1, max_length=4096)
    @model_validator(mode='after')
    def validate_url(self):
        from urllib.parse import urlsplit
        parsed = urlsplit(self.url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
            raise ValueError('Only ordinary HTTP(S) URLs are supported')
        return self

class Locator(Args):
    selector: str = Field(min_length=1, max_length=1024)

class Fill(Locator):
    value: str = Field(max_length=16000)

class Move(Args):
    dx: int = Field(ge=-3000, le=3000)
    dy: int = Field(ge=-3000, le=3000)

class GameKey(Args):
    key: str = Field(min_length=1, max_length=30)
    duration: float = Field(default=0.2, ge=0.01, le=2)

class Template(Args):
    name: str = Field(pattern=r'^[A-Za-z0-9_-]+\.png$')
    threshold: float = Field(default=0.85, ge=0.5, le=1)

ARG_TYPES = {
    'hotkey': Keys, 'type_text': Text, 'click': Click, 'shell': Shell, 'wait': Delay,
    'open_app': App, 'ui_click': Element, 'browser_navigate': URL,
    'browser_click': Locator, 'browser_fill': Fill, 'browser_snapshot': Empty,
    'game_move': Move, 'game_key': GameKey, 'game_click': Empty,
    'template_click': Template, 'focus': Empty,
}
ActionKind = Literal[
    'hotkey', 'type_text', 'click', 'shell', 'wait', 'open_app', 'ui_click',
    'browser_navigate', 'browser_click', 'browser_fill', 'browser_snapshot',
    'game_move', 'game_key', 'game_click', 'template_click', 'focus',
]

class Action(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: ActionKind
    args: dict[str, Any] = Field(default_factory=dict)
    @model_validator(mode='after')
    def validate_args(self):
        validated = ARG_TYPES[self.kind].model_validate(self.args).model_dump()
        object.__setattr__(self, 'args', validated)
        return self

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['CONTINUE', 'GOAL_SATISFIED', 'GOAL_IMPOSSIBLE']
    summary: str = Field(max_length=1500, description='Brief user-facing assessment; no private reasoning')
    plan: list[str] = Field(default_factory=list, max_length=5)
    action: Action | None = None
    @model_validator(mode='after')
    def coherent(self):
        if (self.status == 'CONTINUE') != (self.action is not None):
            raise ValueError('CONTINUE requires exactly one action; terminal states require null action')
        return self

ACTION_HELP = '''Action kinds and args:
hotkey {keys:["ctrl","l"]}; type_text {text:"..."}; click {x:200,y:100,button:"left"};
shell {script:"...",timeout:30}; wait {seconds:1.0}; open_app {name:"notepad"};
ui_click {element_id:0}; focus {}; browser_navigate {url:"https://..."};
browser_click {selector:"role=button[name=Submit]"}; browser_fill {selector:"input[name=q]",value:"..."};
browser_snapshot {}; game_move {dx:50,dy:0}; game_key {key:"w",duration:0.2};
game_click {}; template_click {name:"target.png",threshold:0.85}.
Coordinates are pixels in the latest resized screenshot. UIA IDs only apply to current tree.
Use keyboard navigation and open_app before mouse clicks. No arbitrary Python execution.
'''
