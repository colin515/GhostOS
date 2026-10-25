"""The model must receive DOM-target tools rather than guessed desktop click tools."""
import json
from types import SimpleNamespace
from PIL import Image
from agent.windows_use_engine import WindowsUseBrain
from agent.vision import Frame


def test_browser_target_presence_hides_native_click_action_tools():
    tools=[SimpleNamespace(name=x) for x in
           ('click','ui_click','drag','mouse_move','browser_click_target',
            'browser_click','browser_snapshot','scroll','finish')]
    frame=Frame(Image.new('RGB',(800,450)),(1600,900),source='browser')
    result=WindowsUseBrain.available_tools(tools,frame,json.dumps({
        'transport':'cdp','targets':[{'target_id':0,'tag':'A'}]}))
    assert [t.name for t in result]==[
        'browser_click_target','browser_click','browser_snapshot','scroll','finish']


def test_browser_canvas_without_dom_keeps_pixel_fallback():
    tools=[SimpleNamespace(name='click'),SimpleNamespace(name='browser_click')]
    frame=Frame(Image.new('RGB',(800,450)),(1600,900),source='browser')
    assert WindowsUseBrain.available_tools(tools,frame,'{"targets":[]}')==tools


def test_desktop_ui_keeps_native_actions():
    tools=[SimpleNamespace(name='click')]
    frame=Frame(Image.new('RGB',(800,450)),(1600,900))
    assert WindowsUseBrain.available_tools(tools,frame,'{"targets":[{"target_id":0}]}')==tools
