import threading
from unittest.mock import MagicMock,patch
import pytest
from pydantic import ValidationError
from agent.game_profiles import GameProfile
from agent.gaming_engine import GamingEngine


def test_profile_requires_a_victory_marker_and_cannot_execute_shell_scripts():
    args = dict(name='Demo',window_title='Demo Game',success_template='victory.png',
                rules=[{'template':'start.png','action':{'kind':'shell','args':{'script':'exit'}}}])
    with pytest.raises(ValidationError,match='bounded game input'):
        GameProfile(**args)
    args['rules'][0]['action'] = {'kind':'game_action','args':{'keys':['w'],'duration':.1}}
    assert GameProfile(**args).success_frames >= 2
    args['success_template'] = '../outside.png'
    with pytest.raises(ValidationError):
        GameProfile(**args)


@pytest.mark.parametrize('cancel',[False,True])
def test_game_chord_holds_keys_and_mouse_together_then_releases_everything(cancel):
    stop = threading.Event()
    driver,windows = MagicMock(),MagicMock()
    driver.KEYBOARD_MAPPING = {'shift':42,'w':17}
    windows.GetForegroundWindow.return_value = 1001
    held,packets = set(),[]
    driver.keyDown.side_effect = lambda key:held.add(key)
    driver.keyUp.side_effect = lambda key:held.discard(key)
    def send(events):
        packets.extend(event.mi.dwFlags for event in events)
        if any(event.mi.dwFlags == 1 for event in events):
            assert held == {'shift','w'}
            if cancel:
                stop.set()
    with patch.dict('sys.modules',{'pydirectinput':driver,'win32gui':windows}),patch('agent.gaming_engine.send_input',send):
        engine = GamingEngine(stop)
        if cancel:
            with pytest.raises(InterruptedError):
                engine.action(keys=['shift','w'],buttons=['right'],dx=20,duration=.02)
        else:
            engine.action(keys=['shift','w'],buttons=['right'],dx=20,duration=.02)
    assert not held and not engine.held
    assert packets == [8,1,16]
