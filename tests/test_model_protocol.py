import json
from types import SimpleNamespace
import pytest
from PIL import Image
from agent.vision import Frame
from agent.model_protocol import decision_schema, parse_decision, ModelReplyError, thinking_option


def test_generation_schema_requires_action_and_specific_args_for_continue():
    from jsonschema import Draft202012Validator
    schema = decision_schema()
    continuing, terminal = schema['oneOf']
    assert 'action' in continuing['required']
    choices = continuing['properties']['action']['oneOf']
    click = next(c for c in choices if c['properties']['kind']['const'] == 'click')
    assert click['properties']['args']['required'] == ['x', 'y']
    assert terminal['properties']['action'] == {'type': 'null'}
    assert decision_schema(True)['properties']['status']['const'] == 'CONTINUE'
    validator = Draft202012Validator(schema)
    for invalid in [
        {'status':'CONTINUE','summary':'No action','plan':[],'action':None},
        {'status':'CONTINUE','summary':'No action','plan':[]},
        {'status':'CONTINUE','summary':'Missing coordinates','plan':[],'action':{'kind':'click','args':{}}},
        {'status':'GOAL_SATISFIED','summary':'bad','plan':[],'action':{'kind':'wait','args':{'seconds':0}}},
    ]:
        assert not validator.is_valid(invalid)
    assert validator.is_valid({'status':'CONTINUE','summary':'Wait','plan':[],
                               'action':{'kind':'wait','args':{'seconds':0}}})


def test_missing_action_is_a_format_problem_not_an_ollama_connectivity_error():
    with pytest.raises(ModelReplyError, match='CONTINUE is missing action') as exc:
        parse_decision('{"status":"CONTINUE","summary":"Volume is visible","action":null}')
    assert 'pydantic.dev' not in str(exc.value)
    with pytest.raises(ModelReplyError):
        parse_decision('{"status":"GOAL_SATISFIED","summary":"done"}', True)


def test_fenced_valid_json_keeps_action_validation_intact():
    action = '{"status":"CONTINUE","summary":"Wait","action":{"kind":"wait","args":{"seconds":0}}}'
    assert parse_decision('```json\n' + action + '\n```').action.kind == 'wait'
    with pytest.raises(ModelReplyError):
        parse_decision(action.replace('"seconds":0', '"seconds":-1'))


def test_native_planner_repairs_once_without_duplicating_the_screenshot(monkeypatch):
    from agent.brain import Brain, Context
    calls = []
    replies = ['{"status":"CONTINUE","summary":"I can adjust volume","action":null}',
               '{"status":"CONTINUE","summary":"Wait","action":{"kind":"wait","args":{"seconds":0}}}']
    def chat(**kwargs):
        calls.append({**kwargs, 'messages': list(kwargs['messages'])})
        return iter([SimpleNamespace(message=SimpleNamespace(content=replies.pop(0)))])
    brain = Brain.__new__(Brain)
    brain.settings = SimpleNamespace(model='local-test',game_mode=False,context_tokens=8192,prediction_tokens=512)
    brain.context, brain.thinking, brain.client = Context(), {}, SimpleNamespace(chat=chat)
    result = brain.next('Set volume to 100', Frame(Image.new('RGB',(64,64)),(64,64)), [])
    assert result.action.kind == 'wait'
    assert len(calls) == 2
    assert sum(len(m.get('images',[])) for m in calls[1]['messages']) == 1
    assert 'missing action' in calls[1]['messages'][-1]['content']


def test_thinking_tokens_do_not_consume_the_action_budget():
    assert thinking_option({'capabilities':['vision','thinking']}) == {'think':False}
    assert thinking_option({'thinking':{'values':[False,True]}}) == {'think':False}
    assert thinking_option({'capabilities':['vision']}) == {}
