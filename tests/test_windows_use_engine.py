import json
import sys
from types import SimpleNamespace
import pytest
from PIL import Image
from config import Settings
from agent.models import Action
from agent.vision import Frame
from agent import windows_use_engine as engine
from ghostos_vendor.windows_use.providers.events import LLMEvent, LLMEventType, ToolCall
from ghostos_vendor.windows_use.providers.views import TokenUsage


def response(kind='browser_open', args=None):
    return LLMEvent(type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(id='local-test', name=kind, params=args or {'url':'https://www.netflix.com/'}),
        usage=TokenUsage())


@pytest.fixture
def planner(monkeypatch, tmp_path):
    calls, responses = [], []
    class LLM:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def invoke(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return responses.pop(0)
    monkeypatch.setattr(engine, 'local_model_metadata', lambda *a: {'capabilities':['vision','tools']})
    monkeypatch.setitem(sys.modules, 'ghostos_vendor.windows_use.providers.ollama', SimpleNamespace(ChatOllama=LLM))
    monkeypatch.setattr(engine, 'local_desktop', lambda: None)
    brain = engine.WindowsUseBrain(Settings(data_dir=tmp_path))
    frame = Frame(Image.new('RGB', (100, 50)), (200, 100))
    return brain, frame, calls, responses


def test_real_upstream_tool_response_is_validated_but_never_executed(planner):
    brain, frame, calls, responses = planner
    responses.append(response())
    decision = brain.next('Open Netflix', frame, [])
    assert decision.action.kind == 'browser_open'
    assert calls[0]['host'] == 'http://127.0.0.1:11434'
    assert calls[0]['timeout'] == 90
    messages, options = calls[1]
    assert len(messages[1].images) == 1
    assert options['tools'] and all(tool.function is None for tool in options['tools'])
    # SDK functions are inference descriptions only; Controller is the sole executor.
    assert decision.action == Action(kind='browser_open', args={'url':'https://www.netflix.com/'})


def test_unknown_upstream_tool_cannot_bypass_ghostos_capabilities(planner):
    brain, frame, _, responses = planner
    responses.append(response('file_tool', {'mode':'delete', 'path':'C:/important'}))
    with pytest.raises(ValueError):
        brain.next('goal', frame, [])


def test_unverified_finish_is_excluded_after_recovery(planner):
    brain, frame, calls, responses = planner
    responses.append(response('finish', {'summary':'already focused'}))
    with pytest.raises(ValueError, match='action is required'):
        brain.next('Open a new tab', frame, [], feedback='DECISION_ACTION_REQUIRED')
    assert 'finish' not in [tool.name for tool in calls[1][1]['tools']]


def test_existing_non_tool_vision_models_use_sdk_structured_path(planner):
    brain, frame, calls, responses = planner
    brain.tools_supported = False
    responses.append(LLMEvent(type=LLMEventType.TEXT, usage=TokenUsage(), content=json.dumps({
        'status':'CONTINUE', 'summary':'Navigate', 'action':{'kind':'browser_new_tab', 'args':{}}})))
    assert brain.next('Open a new tab', frame, []).action.kind == 'browser_new_tab'
    assert 'structured_output' in calls[1][1] and 'tools' not in calls[1][1]


def test_sdk_coordinates_are_scaled_once_and_foreign_screen_targets_excluded(planner):
    brain, frame, _, _ = planner
    node = lambda x,y: SimpleNamespace(center=SimpleNamespace(x=x,y=y),name='Button',control_type='ButtonControl',window_name='App')
    state = SimpleNamespace(active_window=SimpleNamespace(name='App'),windows=[],
        tree_state=SimpleNamespace(interactive_nodes=[node(100,50),node(-10,20),node(500,40)],scrollable_nodes=[],
                                   interactive_elements_to_string=lambda:'App button'),)
    state.active_window.handle = 5
    brain.desktop = SimpleNamespace(get_state=lambda:state)
    observed = brain.observation(frame)
    assert observed['controls'] == [{'name':'Button','type':'ButtonControl','window':'App','x':50,'y':25}]
    assert frame.physical(50,25) == (100,50)


def test_windows_use_is_default_and_old_settings_migrate(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text('{"model":"qwen2.5vl:7b", "setup_complete":true}')
    settings = Settings.load(tmp_path)
    assert settings.computer_use_engine == 'windows_use'
    settings.save()
    assert Settings.load(tmp_path).computer_use_engine == 'windows_use'
    with pytest.raises(ValueError, match='Unknown computer-use'):
        Settings(computer_use_engine='remote-cloud')


def test_upstream_loop_detection_is_bounded_without_a_step_limit():
    from ghostos_vendor.windows_use.agent.loop import LoopGuard
    guard = LoopGuard()
    for index in range(1100):
        state = SimpleNamespace(active_window=SimpleNamespace(handle=index, name=str(index)), tree_state=None)
        guard.record_state(state)
        guard.record_action('mouse_move', {'x':index, 'y':0})
    assert len(guard._visited_states) <= 256
    assert len(guard._hashes) <= 15
