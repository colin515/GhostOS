import json
import sys
import threading
from types import SimpleNamespace
from agent.browser_media import cdp_media, native_media
from agent.models import Action
from agent.safety import requires_approval


def player_page(paused=True, fail=False):
    state = {'paused':paused,'ended':False,'current_time':0.0,'ready_state':4,'error':None}
    calls = []
    class Node:
        def is_visible(self):
            return True
        def evaluate(self, script):
            if 'e.play()' in script:
                calls.append('play')
                if not fail:
                    state['paused'] = False
            elif 'e.pause()' in script:
                calls.append('pause')
                state['paused'] = True
            else:
                if not state['paused']:
                    state['current_time'] += 0.1
                return dict(state)
    page = SimpleNamespace(locator=lambda selector:SimpleNamespace(element_handles=lambda:[Node()]),
                           get_by_role=lambda *a,**kw:SimpleNamespace(all=lambda:[]),wait_for_timeout=lambda ms:None)
    return page, state, calls


def test_playback_requires_time_progress_and_never_toggles_already_playing_media():
    page, state, calls = player_page()
    assert cdp_media(page,'play')['verified']
    assert not state['paused'] and calls == ['play']
    assert cdp_media(page,'play')['verified']
    assert calls == ['play']
    assert cdp_media(page,'pause')['verified']
    assert state['paused'] and calls == ['play','pause']


def test_multiple_visible_players_are_not_guessed():
    page, _, calls = player_page()
    node = page.locator('').element_handles()[0]
    page.locator = lambda selector:SimpleNamespace(element_handles=lambda:[node,node])
    assert not cdp_media(page,'play')['verified']
    assert not calls


def test_native_youtube_click_is_verified_and_does_not_pause_existing_playback(monkeypatch):
    from agent import mouse
    playing, clicks = [False], []
    class Button:
        ControlTypeName = 'ButtonControl'
        BoundingRectangle = SimpleNamespace(left=10,right=30,top=20,bottom=40)
        @property
        def Name(self):
            return 'Pause (k)' if playing[0] else 'Play (k)'
        def GetChildren(self):
            return []
    root = SimpleNamespace(Name='YouTube',ControlTypeName='DocumentControl',GetChildren=lambda:[Button()])
    monkeypatch.setitem(sys.modules,'uiautomation',SimpleNamespace(GetForegroundControl=lambda:root))
    def click(*args):
        clicks.append(args)
        playing[0] = not playing[0]
    monkeypatch.setattr(mouse,'MouseDriver',lambda stop:SimpleNamespace(click=click))
    native = SimpleNamespace(app='chrome',apps=SimpleNamespace(focus=lambda app:None),stop=threading.Event(),
                             check=lambda:None,chrome=lambda:([], 'https://www.youtube.com/watch?v=test'))
    assert json.loads(native_media(native,'play'))['verified']
    assert clicks == [(20,30)] and playing[0]
    assert json.loads(native_media(native,'play'))['verified']
    assert clicks == [(20,30)]


def test_media_permissions_are_still_enforced_in_strict_mode():
    action = Action(kind='browser_media',args={'operation':'play'})
    assert requires_approval(action,1)
    assert not requires_approval(action,2)
    assert not requires_approval(action,3)
