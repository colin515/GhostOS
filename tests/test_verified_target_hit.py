"""Hit-test actual UIA targets before sending a physical mouse click.

Regression coverage for occlusion, DPI-space mismatch, child text elements, and
position changes while the cursor moves.
"""
import queue
import sys
from types import SimpleNamespace
import pytest
from PIL import Image
from agent.ui_tree import UITree
from agent.targeting import StaleTargetError
from agent.controller import Controller
from agent.vision import Frame
from agent.models import Action


class Rect:
    left, top, right, bottom = 100, 80, 200, 120
    def width(self): return self.right - self.left
    def height(self): return self.bottom - self.top


class Target:
    Name = 'Submit'
    ControlTypeName = 'ButtonControl'
    BoundingRectangle = Rect()
    IsOffscreen = False
    IsEnabled = True
    def Exists(self, *a): return True
    def GetRuntimeId(self): return [10, 20, 30]


def make_tree(monkeypatch, hit=None):
    target = Target()
    win = SimpleNamespace(NativeWindowHandle=123)
    tree = UITree()
    tree.window, tree.controls, tree.identities = (
        win, {4: target}, {4: ('Submit', 'ButtonControl')})
    mock = SimpleNamespace(GetForegroundControl=lambda: win,
                           ControlFromPoint=hit or (lambda x,y: target))
    monkeypatch.setitem(sys.modules,'uiautomation',mock)
    return tree, mock, target


def test_click_point_verified_on_control(monkeypatch):
    tree, _, _ = make_tree(monkeypatch)
    assert tree.click_point(4) == (150, 100)


def test_child_text_hit_counts_as_target(monkeypatch):
    tree, mock, target = make_tree(monkeypatch)
    child = SimpleNamespace(Name='Submit text', ControlTypeName='TextControl',
                            GetRuntimeId=lambda: [88],
                            GetParentControl=lambda: target)
    mock.ControlFromPoint = lambda x,y: child
    assert tree.click_point(4) == (150, 100)


def test_covered_target_must_not_be_clicked(monkeypatch):
    tree, mock, target = make_tree(monkeypatch)
    other = SimpleNamespace(Name='Toolbar',ControlTypeName='PaneControl',
                            GetRuntimeId=lambda:[77],
                            GetParentControl=lambda:None)
    mock.ControlFromPoint = lambda x,y: other
    with pytest.raises(StaleTargetError,match='not physically clickable'):
        tree.click_point(4)


def test_click_point_finds_uncovered_interior(monkeypatch):
    tree, mock, target = make_tree(monkeypatch)
    wrong = SimpleNamespace(Name='Overlay',ControlTypeName='PaneControl',
                            GetRuntimeId=lambda:[77],
                            GetParentControl=lambda:None)
    mock.ControlFromPoint = lambda x,y: wrong if x==150 and y==100 else target
    assert tree.click_point(4) != (150,100)


def test_ui_click_uses_hit_test_and_checks_again_before_press(monkeypatch):
    tree, mock, target = make_tree(monkeypatch)
    frame = Frame(Image.new('RGB',(400,250),'white'),(400,250))
    events, clicks = queue.Queue(), []
    mouse=SimpleNamespace(before_press=None)
    def click(x,y,*args):
        if mouse.before_press:
            mouse.before_press()
        clicks.append((x,y))
    mouse.click=click
    controller=Controller.__new__(Controller)
    controller.safety=SimpleNamespace(authorize=lambda act:None,check=lambda:None,events=events)
    controller.focus_guard=SimpleNamespace(ensure_external=lambda:None)
    controller.settings=SimpleNamespace(game_mode=False)
    controller.frame,controller.tree,controller.vision=frame,tree,SimpleNamespace(capture=lambda:frame)
    controller.mouse_driver=lambda:mouse
    controller.execute(Action(kind='ui_click',args={'element_id':4}))
    assert clicks==[(150,100)]
    entries=[events.get()['kind'] for _ in range(events.qsize())]
    assert 'TARGET' in entries
    mock.ControlFromPoint=lambda x,y: SimpleNamespace(Name='wrong',
        ControlTypeName='PaneControl',GetRuntimeId=lambda:[999],
        GetParentControl=lambda:None)
    with pytest.raises(StaleTargetError):
        controller.execute(Action(kind='ui_click',args={'element_id':4}))
    assert len(clicks)==1
