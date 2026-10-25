"""Regression tests for centring mistaken clicks on live UI Automation controls."""
import queue
import sys
from types import SimpleNamespace
from PIL import Image
from agent.controller import Controller
from agent.models import Action
from agent.ui_tree import UITree
from agent.vision import Frame


class Rect:
    left, top, right, bottom = 180, 80, 300, 120

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class Control:
    Name = 'Continue'
    ControlTypeName = 'ButtonControl'
    BoundingRectangle = Rect()

    def Exists(self, *args):
        return True


def live_tree(monkeypatch):
    tree = UITree()
    tree.window = SimpleNamespace(NativeWindowHandle=17)
    tree.controls = {4: Control()}
    import types
    monkeypatch.setitem(sys.modules, 'uiautomation',
                        types.SimpleNamespace(GetForegroundControl=lambda: tree.window))
    return tree


def test_ui_tree_snaps_under_button_to_its_centre(monkeypatch):
    tree = live_tree(monkeypatch)
    assert tree.nearest_click_target(245, 139) == (4, 240, 100)
    assert tree.nearest_click_target(245, 240) is None


def test_ambiguous_buttons_do_not_attract_mouse(monkeypatch):
    tree = live_tree(monkeypatch)
    tree.controls[7] = Control()
    assert tree.nearest_click_target(240, 125) is None


def test_controller_centres_nearby_visual_click(monkeypatch):
    tree = live_tree(monkeypatch)
    frame = Frame(Image.new('RGB', (500, 300), 'white'), (500, 300))
    clicks = []
    mouse = SimpleNamespace(before_press=None)
    def click(x, y, *args):
        if mouse.before_press:
            mouse.before_press()
        clicks.append((x, y))
    mouse.click = click
    controller = Controller.__new__(Controller)
    controller.settings = SimpleNamespace(game_mode=False)
    controller.safety = SimpleNamespace(authorize=lambda action: None,
                                         check=lambda: None, events=queue.Queue())
    controller.focus_guard = SimpleNamespace(ensure_external=lambda: None)
    controller.tree, controller.vision, controller.frame = (tree, SimpleNamespace(capture=lambda: frame), frame)
    controller.mouse_driver = lambda: mouse
    controller.execute(Action(kind='click', args={'x': 245, 'y': 139}))
    assert clicks == [(240, 100)]
    assert controller.safety.events.get()['kind'] == 'EXECUTING'
    target = controller.safety.events.get()
    assert target['kind'] == 'TARGET' and target['source'] == 'accessibility-snap'
