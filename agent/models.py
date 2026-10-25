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
    button: Literal['left', 'right', 'middle', 'x1', 'x2'] = 'left'
    clicks: int = Field(default=1, ge=1, le=2)
    duration: float = Field(default=0.35, ge=0.05, le=5)
    coordinate_space: Literal['screenshot', 'normalized_1000'] = 'screenshot'
    target: str = Field(default='', max_length=120, description='Exact accessible label when available')

class Cursor(Args):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    duration: float = Field(default=0.35, ge=0.05, le=5)
    coordinate_space: Literal['screenshot', 'normalized_1000'] = 'screenshot'

class Drag(Click):
    to_x: int = Field(ge=0)
    to_y: int = Field(ge=0)

class Scroll(Args):
    ticks: int = Field(ge=-100, le=100)
    horizontal: bool = False

class Shell(Args):
    script: str = Field(min_length=1, max_length=20000)
    timeout: int = Field(default=30, ge=1, le=120)

class Delay(Args):
    seconds: float = Field(ge=0, le=10)

class App(Args):
    name: str = Field(min_length=1, max_length=80)

class AppQuery(Args):
    query: str = Field(default='', max_length=80)

class WindowHandle(Args):
    hwnd: int = Field(gt=0)

class EnsureApp(App):
    strategy: Literal['focus', 'launch', 'search'] = 'focus'

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

class BrowserOpen(URL):
    new_tab: bool = False
    backend: Literal['auto', 'native', 'cdp'] = 'auto'

class BrowserTarget(Args):
    target_id: int = Field(ge=0, le=150, description='Visible browser target ID from the latest CDP snapshot')


class BrowserSearch(Args):
    query: str = Field(min_length=1,max_length=300)


class BrowserFillTarget(BrowserSearch):
    target_id: int = Field(ge=0,le=150)
    value: str = Field(max_length=16000)
    query: str = Field(default='', max_length=300)


class BrowserPress(Args):
    target_id: int = Field(ge=0,le=150)
    key: Literal['Enter','Tab','Escape','Space','ArrowDown','ArrowUp'] = 'Enter'


class GameMenuClick(Args):
    x: int = Field(ge=0, description='Horizontal pixel in current GAME CLIENT screenshot')
    y: int = Field(ge=0, description='Vertical pixel in current GAME CLIENT screenshot')
    button: Literal['left','right'] = 'left'
    coordinate_space: Literal['screenshot','normalized_1000'] = 'screenshot'


class BrowserTab(Args):
    backend: Literal['auto', 'native', 'cdp'] = 'auto'

class TabId(Args):
    tab_id: int = Field(ge=0, le=500)

class Locator(Args):
    selector: str = Field(min_length=1, max_length=1024)

class Fill(Locator):
    value: str = Field(max_length=16000)

class Media(Args):
    operation: Literal['play', 'pause', 'state']

class Move(Args):
    dx: int = Field(ge=-3000, le=3000)
    dy: int = Field(ge=-3000, le=3000)

class GameKey(Args):
    key: str = Field(min_length=1, max_length=30)
    duration: float = Field(default=0.2, ge=0.01, le=2)

class GameClick(Args):
    button: Literal['left','right','middle'] = 'left'

class GameBind(Args):
    title: str = Field(min_length=3,max_length=200)

class GameAction(Move):
    dx: int = Field(default=0,ge=-3000,le=3000)
    dy: int = Field(default=0,ge=-3000,le=3000)
    keys: list[str] = Field(default_factory=list,max_length=6)
    buttons: list[Literal['left','right','middle']] = Field(default_factory=list,max_length=3)
    duration: float = Field(default=.2,ge=.01,le=2)

class Template(Args):
    name: str = Field(pattern=r'^[A-Za-z0-9_-]+\.png$')
    threshold: float = Field(default=0.85, ge=0.5, le=1)

ARG_TYPES = {
    'mouse_move': Cursor, 'drag': Drag, 'scroll': Scroll, 'hotkey': Keys, 'type_text': Text, 'click': Click, 'shell': Shell, 'wait': Delay,
    'open_app': App, 'ensure_app': EnsureApp, 'app_list': AppQuery, 'focus_window': WindowHandle, 'ui_click': Element, 'browser_navigate': URL,
    'browser_click': Locator, 'browser_first_video': Empty, 'browser_click_target': BrowserTarget, 'browser_fill_target': BrowserFillTarget, 'browser_press_target': BrowserPress, 'browser_search': BrowserSearch, 'browser_fill': Fill, 'browser_snapshot': Empty, 'browser_media': Media,
    'browser_open': BrowserOpen, 'browser_new_tab': BrowserTab, 'browser_tabs': Empty, 'browser_switch_tab': TabId,
    'game_move': Move, 'game_menu_click': GameMenuClick, 'game_key': GameKey, 'game_click': GameClick, 'game_action': GameAction, 'game_bind':GameBind,
    'template_click': Template, 'focus': Empty,
}
ActionKind = Literal[
    'mouse_move', 'drag', 'scroll', 'hotkey', 'type_text', 'click', 'shell', 'wait', 'open_app', 'ui_click', 'app_list', 'focus_window',
    'browser_navigate', 'browser_click', 'browser_first_video', 'browser_click_target', 'browser_fill_target', 'browser_press_target', 'browser_search', 'browser_fill', 'browser_snapshot', 'browser_media',
    'browser_open', 'browser_new_tab', 'browser_tabs', 'browser_switch_tab',
    'game_move', 'game_menu_click', 'game_key', 'game_click', 'game_action', 'game_bind', 'template_click', 'focus', 'ensure_app',
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
browser_click {selector:"role=button[name=Submit]"}; browser_click_target {target_id:0} uses the exact current browser snapshot target ID and verifies its DOM identity;
browser_fill {selector:"input[name=q]",value:"..."}; browser_first_video {} clicks and verifies first real YouTube result; browser_fill_target {target_id:0,value:"..."} fills the observed textbox; browser_press_target {target_id:0,key:"Enter"} presses a key on the element; browser_search {query:"lo-fi music"} searches in the current site and verifies the result;

browser_open {url:"https://www.netflix.com/",new_tab:false,backend:"auto"} reuses a matching tab or navigates directly;
browser_new_tab {backend:"auto"} actually creates and verifies a new tab;
browser_tabs {} lists CDP tab IDs, titles and URLs; browser_switch_tab {tab_id:0} activates a listed tab;
browser_media {operation:"play"|"pause"|"state"} controls the current HTML5 video/audio and verifies its state; opening YouTube is not evidence of playback;
browser_snapshot {}; game_move {dx:50,dy:0}; game_key {key:"w",duration:0.2};
game_click {button:"left"} clicks at CURRENT CURSOR only; NEVER use it for visual menu buttons. game_menu_click {x:300,y:180} first moves to a pixel in the game CLIENT screenshot and clicks there safely; template_click {name:"target.png",threshold:0.85}.
game_action {keys:["shift","w"],buttons:["right"],dx:35,dy:0,duration:0.2} holds a chord and moves the camera together; all held input releases afterward.
game_bind {title:"Exact captured game window title"} binds the current captured foreground game after a launcher/window transition; never bind an unrelated app.
Coordinates are pixels in the latest resized screenshot. UIA IDs only apply to current tree.
For click/drag/mouse_move, coordinate_space defaults to "screenshot". Explicit "normalized_1000" means 0..1000 on both axes; do not infer a space from the numbers.
click/drag target:"Exact button label" uses unique live accessibility bounds. Prefer this or ui_click to estimated coordinates.
ensure_app {name:"chrome",strategy:"focus"|"launch"|"search"} focuses/maximizes a running app,
launches an installed app, or launches natively (legacy search maps to direct launch). Apps: chrome, edge, firefox, notepad, calculator, explorer, paint, store (Microsoft Store).
app_list {query:"word"} reads installed Windows app names; open_app {name:"exact installed name"} launches them directly.
focus_window {hwnd:12345} focuses an external window from the current window inventory.
Use native app launch, browser DOM actions and actual mouse control. Keyboard shortcuts are a fallback.
mouse_move {x:200,y:100,duration:0.35}; drag {x:100,y:100,to_x:300,to_y:300,button:"left",duration:0.8}; scroll {ticks:-3,horizontal:false}.
click supports left/right/middle/x1/x2 buttons and clicks:2 for double click. No arbitrary Python execution.
'''
