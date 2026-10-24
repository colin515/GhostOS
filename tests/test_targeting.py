import queue
import threading
from types import SimpleNamespace
import pytest
from PIL import Image
from agent.vision import Frame
from agent.targeting import resolve_point,StaleTargetError
from agent.models import Action
from agent.controller import Controller


@pytest.mark.parametrize('scale',[1.,1.25,1.5,2.])
def test_controller_click_uses_exactly_one_transform_at_nonzero_screen_origin(scale):
    frame = Frame(Image.new('RGB',(800,600)),(round(800*scale),round(600*scale)),origin=(-1400,240))
    tree = [{'id':7,'name':'Play','bounds':[-1400+round(100*scale),240+round(80*scale),
                                          -1400+round(200*scale),240+round(120*scale)]}]
    target = frame.tree_for_model(tree)[0]
    calls = []
    controller = Controller.__new__(Controller)
    controller.settings = SimpleNamespace(game_mode=False)
    controller.safety = SimpleNamespace(authorize=lambda action:None,check=lambda:None,events=queue.Queue())
    controller.focus_guard = SimpleNamespace(ensure_external=lambda:None)
    controller.frame,controller.tree,controller.vision = frame,None,SimpleNamespace(capture=lambda:frame)
    controller.mouse_driver = lambda:SimpleNamespace(click=lambda x,y,*a:calls.append((x,y)))
    controller.execute(Action(kind='click',args={'x':target['x'],'y':target['y']}))
    assert calls == [(-1400+round(150*scale),240+round(100*scale))]


def test_normalized_coordinates_are_explicit_and_reach_the_correct_window_pixel():
    frame = Frame(Image.new('RGB',(1000,500)),(2000,1000),origin=(300,-700))
    assert frame.point(500,500,'normalized_1000') == (1300,-200)
    assert frame.point(500,250,'screenshot') == (1300,-200)
    assert frame.point(1000,1000,'normalized_1000') == (2299,299)
    with pytest.raises(ValueError):
        frame.point(500,500,'screenshot')


def test_changed_click_region_is_rejected_before_any_mouse_input():
    before = Frame(Image.new('RGB',(100,100),'black'),(100,100))
    after = Frame(Image.new('RGB',(100,100),'white'),(100,100))
    with pytest.raises(StaleTargetError,match='changed during inference'):
        resolve_point(before,{'x':50,'y':50},None,SimpleNamespace(capture=lambda:after))


def test_exact_accessible_label_uses_live_bounds_instead_of_estimated_coordinates():
    frame = Frame(Image.new('RGB',(100,100)),(200,200),origin=(400,500))
    actual,source = resolve_point(frame,{'x':0,'y':0,'target':'Play'},
                                  SimpleNamespace(find=lambda label:(510,640)),None)
    assert actual == (510,640) and source == 'accessibility-label'


def test_mouse_drift_before_press_does_not_click():
    from test_mouse import Backend
    from agent.mouse import MouseDriver
    backend = Backend()
    positions = [0]
    position = backend.position
    def drift():
        positions[0] += 1
        return (300,300) if positions[0] >= 3 else position()
    backend.position = drift
    with pytest.raises(RuntimeError,match='before button press'):
        MouseDriver(threading.Event(),backend=backend).click(100,100,duration=.02)
    assert not backend.inputs
