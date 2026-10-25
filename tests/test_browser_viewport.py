"""Regression tests for the logged 769px click and browser/desktop coordinate mixup."""
import io
import json
import queue
from types import SimpleNamespace
from PIL import Image
import pytest
from agent.controller import Controller
from agent.vision import Frame
from agent.web_engine import WebEngine
from agent.models import Action
from config import Settings


class FakeMouse:
    def __init__(self):
        self.clicks=[]
        self.moves=[]
        self.wheels=[]
    def click(self, x,y,**kw): self.clicks.append((x,y,kw))
    def move(self,x,y): self.moves.append((x,y))
    def wheel(self,x,y): self.wheels.append((x,y))


class FakePage:
    url='https://www.youtube.com/'
    def __init__(self):
        self.mouse=FakeMouse()
        self.evaluate_results=[]
        self.screens=[]
    def evaluate(self,script,arg=None):
        return self.evaluate_results.pop(0)
    def screenshot(self,**kw):
        self.screens.append(kw)
        buff=io.BytesIO()
        Image.new('RGB',(1600,900),'white').save(buff,format='JPEG')
        return buff.getvalue()
    def is_closed(self): return False
    def title(self): return 'YouTube'


def web_setup():
    web=WebEngine(Settings(screenshot_width=800))
    page=FakePage()
    web.page=page
    web.context=SimpleNamespace(pages=[page])
    return web,page


def test_cdp_browser_screenshot_uses_css_pixels_without_desktop_offset():
    web,page=web_setup()
    frame=web.capture_frame()
    assert frame.source=='browser'
    assert frame.image.size==(800,450)
    assert frame.original_size==(1600,900)
    assert frame.origin==(0,0)
    assert page.screens[0]['scale']=='css'
    assert frame.point(400,225)==(800,450)


def controller_setup():
    web,page=web_setup()
    frame=web.capture_frame()
    controller=Controller.__new__(Controller)
    controller.web,controller.frame=web,frame
    controller.settings=SimpleNamespace(game_mode=False)
    controller.safety=SimpleNamespace(authorize=lambda a:None,check=lambda:None,events=queue.Queue())
    controller.focus_guard=SimpleNamespace(ensure_external=lambda:pytest.fail('Browser must not focus desktop'))
    controller.mouse_driver=lambda:pytest.fail('Browser must not use native cursor')
    return controller,page


def test_browser_click_is_cdp_viewport_not_physical_desktop():
    controller,page=controller_setup()
    page.evaluate_results=[{'tag':'A','href':'/watch?v=abc','label':'Video'}]
    result=json.loads(controller.execute(Action(kind='click',args={'x':400,'y':225})))
    assert result['transport']=='cdp'
    assert result['click_dispatched']
    assert page.mouse.clicks==[(800,450,{'button':'left','click_count':1})]


def test_logged_y_769_is_rejected_before_any_input():
    controller,page=controller_setup()
    with pytest.raises(ValueError,match=r'800x450 browser screenshot'):
        controller.execute(Action(kind='click',args={'x':538,'y':769}))
    assert page.mouse.clicks==[]


def test_browser_click_refuses_unrelated_blank_overlay():
    controller,page=controller_setup()
    page.evaluate_results=[{'error':'not_interactive','tag':'DIV','label':'YouTube'}]
    with pytest.raises(ValueError,match='did not hit a clickable'):
        controller.execute(Action(kind='click',args={'x':250,'y':100}))
    assert page.mouse.clicks==[]


def test_browser_move_and_wheel_always_use_cdp():
    controller,page=controller_setup()
    controller.execute(Action(kind='mouse_move',args={'x':400,'y':225}))
    controller.execute(Action(kind='scroll',args={'ticks':-2}))
    assert page.mouse.moves==[(800,450)]
    assert page.mouse.wheels==[(0,240)]


def test_browser_target_uses_fresh_snapshot_identity():
    web,page=web_setup()
    calls=[]
    class Target:
        def count(self): return 1
        def evaluate(self,script): return {'tag':'A','href':'/watch?v=abc','id':'','name':'','text':'A'}
        def click(self): calls.append('clicked')
    class Locator:
        def nth(self,i):
            assert i==17
            return Target()
    page.locator=lambda q:Locator()
    web._targets_page=page
    web._targets={3:{'dom_index':17,'tag':'A','href':'/watch?v=abc','id':''}}
    web.snapshot=lambda **extra:json.dumps(extra)
    result=json.loads(web.click_target(3))
    assert calls==['clicked'] and result['clicked_target_id']==3


def test_browser_target_rejects_changed_link_without_click():
    web,page=web_setup()
    clicks=[]
    class Target:
        def count(self):return 1
        def evaluate(self,script):return {'tag':'A','href':'/watch?v=evil','id':'','name':'','text':'A'}
        def click(self): clicks.append(True)
    page.locator=lambda s:SimpleNamespace(nth=lambda i:Target())
    web._targets_page=page
    web._targets={3:{'dom_index':17,'tag':'A','href':'/watch?v=abc','id':''}}
    with pytest.raises(ValueError,match='changed identity'):
        web.click_target(3)
    assert clicks==[]


def test_normal_desktop_frames_do_not_change_coordinate_semantics():
    frame=Frame(Image.new('RGB',(800,450)),(1600,900),origin=(100,200))
    assert frame.source=='desktop'
    assert frame.point(400,225)==(900,650)
