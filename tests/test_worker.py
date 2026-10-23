from contextlib import nullcontext
import queue
import json
import threading
from types import SimpleNamespace
import pytest
from PIL import Image
from agent.models import Action, Decision
from agent.vision import Frame
from agent import worker

@pytest.fixture
def harness(monkeypatch, tmp_path):
    import config
    import agent.vision
    import agent.ui_tree
    import agent.controller
    import agent.brain
    monkeypatch.setattr(config, 'enable_dpi_awareness', lambda: None)
    monkeypatch.setattr(worker, 'os', SimpleNamespace(name='posix'))
    settings = SimpleNamespace(data_dir=tmp_path, max_steps=3, max_runtime=10,
                               screenshot_width=1280, game_mode=False, tier=3, approval_timeout=1)
    actions, decisions = [], []
    class Vision:
        def __init__(self, *args):
            pass
        def capture(self):
            return Frame(Image.new('RGB', (50, 50)), (50, 50))
        def changed(self, *args):
            return True
    class Tree:
        def snapshot(self):
            return []
    class Controller:
        def __init__(self, settings, safety, tree, vision):
            self.safety = safety
        def execute(self, action):
            self.safety.authorize(action)
            actions.append(action)
            if action.kind == 'browser_open':
                return json.dumps({'verified': True, 'url': action.args['url'], 'created_tab': action.args['new_tab']})
            if action.kind == 'browser_new_tab':
                return json.dumps({'verified': True, 'created_tab': True})
            if action.kind == 'ensure_app':
                return json.dumps({'verified': True, 'app': action.args['name'], 'foreground': True})
            return 'done'
        def close(self):
            pass
    class Brain:
        fast_command = staticmethod(agent.brain.Brain.fast_command)
        def __init__(self, settings):
            self.context = agent.brain.Context()
        def next(self, *args):
            return decisions.pop(0)
    monkeypatch.setattr(agent.vision, 'Vision', Vision)
    monkeypatch.setattr(agent.ui_tree, 'UITree', Tree)
    monkeypatch.setattr(agent.ui_tree, 'uia_context', nullcontext)
    monkeypatch.setattr(agent.controller, 'Controller', Controller)
    monkeypatch.setattr(agent.brain, 'Brain', Brain)
    def run(goal='goal', recipe=None, stop=None):
        events = queue.Queue()
        worker.run_worker(settings, goal, recipe, stop or threading.Event(), events, queue.Queue())
        result = []
        while not events.empty():
            result.append(events.get_nowait())
        return result
    return settings, actions, decisions, run


def test_loop_observes_executes_and_checks_success(harness):
    _, actions, decisions, run = harness
    decisions.extend([Decision(status='CONTINUE', summary='wait', action=Action(kind='wait', args={'seconds': 0.0})),
                      Decision(status='GOAL_SATISFIED', summary='visible success')])
    events = run()
    assert [a.kind for a in actions] == ['wait']
    assert [e['status'] for e in events if e['kind'] == 'STATUS'] == ['GOAL_SATISFIED']


def test_fast_path_completes_at_exact_step_budget(harness):
    settings, actions, _, run = harness
    settings.max_steps = 1
    events = run('/action {"kind":"wait","args":{"seconds":0.0}}')
    assert len(actions) == 1
    assert any(e.get('status') == 'COMMAND_COMPLETED' for e in events)


def test_recipe_completes_at_exact_step_budget(harness, tmp_path):
    settings, actions, _, run = harness
    settings.max_steps = 1
    path = tmp_path / 'recipe.yaml'
    path.write_text('name: test\nsteps:\n- kind: wait\n  args: {seconds: 0.0}\n')
    events = run(recipe=path)
    assert len(actions) == 1
    assert any(e.get('status') == 'RECIPE_COMPLETED' for e in events)


def test_stopped_loop_dispatches_nothing(harness):
    _, actions, _, run = harness
    stop = threading.Event()
    stop.set()
    events = run(stop=stop)
    assert not actions
    assert any(e.get('status') == 'STOPPED' for e in events)


def test_first_impossible_verdict_recovers_and_reobserves(harness):
    _, actions, decisions, run = harness
    decisions.extend([Decision(status='GOAL_IMPOSSIBLE', summary='browser is unfocused'),
                      Decision(status='GOAL_SATISFIED', summary='browser is now available')])
    events = run()
    assert actions[0].kind == 'focus'
    assert any(e.get('status') == 'GOAL_SATISFIED' for e in events)
    assert not any(e.get('status') == 'GOAL_IMPOSSIBLE' for e in events)


def test_exhausted_recovery_keeps_goal_active_until_success(harness, monkeypatch):
    settings, actions, decisions, run = harness
    settings.max_steps = 0
    settings.max_runtime = 0
    original = threading.Event.wait
    monkeypatch.setattr(threading.Event, 'wait', lambda self, timeout=None: self.is_set() if timeout else original(self, timeout))
    decisions.extend([Decision(status='GOAL_IMPOSSIBLE', summary='blocked') for _ in range(8)])
    decisions.append(Decision(status='GOAL_SATISFIED', summary='unblocked'))
    events = run()
    assert any(e.get('status') == 'GOAL_SATISFIED' for e in events)
    assert not any(e.get('status') == 'GOAL_IMPOSSIBLE' for e in events)
    assert [a.kind for a in actions] == ['focus', 'wait']


def test_explicit_chrome_url_navigates_and_verifies_before_inference(harness):
    _, actions, decisions, run = harness
    decisions.append(Decision(status='GOAL_SATISFIED', summary='ready'))
    events = run('Open galaxus.ch in Google Chrome')
    assert actions[0].kind == 'browser_open'
    assert actions[0].args['url'] == 'https://galaxus.ch'
    assert len(decisions) == 1  # Does not need a model to navigate.
    assert any(e.get('status') == 'GOAL_SATISFIED' for e in events)


def test_model_transport_errors_are_retried_and_not_called_impossible(harness, monkeypatch):
    _, actions, _, run = harness
    monkeypatch.setattr(threading.Event, 'wait', lambda self, timeout=None: self.is_set())
    events = run()
    assert not actions
    assert any(e.get('status') == 'MAX_STEPS_EXCEEDED' for e in events)
    assert not any(e.get('status') == 'GOAL_IMPOSSIBLE' for e in events)


def test_recovery_respects_declined_approval(harness, monkeypatch):
    import agent.controller
    _, actions, decisions, run = harness
    decisions.append(Decision(status='GOAL_IMPOSSIBLE', summary='unfocused'))
    def decline(self, action):
        raise PermissionError('User declined recovery')
    monkeypatch.setattr(agent.controller.Controller, 'execute', decline)
    events = run()
    assert not actions
    assert any(e.get('status') == 'PERMISSION_DENIED' for e in events)


def test_default_unlimited_allows_more_than_one_thousand_actions(harness):
    settings, actions, decisions, run = harness
    settings.max_steps = settings.max_runtime = 0
    decisions.extend([Decision(status='CONTINUE', summary='working', action=Action(kind='wait', args={'seconds':0.0})) for _ in range(1100)])
    decisions.append(Decision(status='GOAL_SATISFIED', summary='done'))
    events = run()
    assert len(actions) == 1100
    assert events[-2]['status'] == 'GOAL_SATISFIED'


@pytest.mark.parametrize('goal,kind,target', [
    ('I would like you to just open Microsoft Store', 'ensure_app', 'store'),
    ('Could you open a new tab in Google Chrome?', 'browser_new_tab', None),
    ('Okay, Open Google Chrome and Open In Google Chrome, the Netflix website.', 'browser_open', 'https://www.netflix.com/'),
])
def test_logged_failures_execute_without_model_veto(harness, goal, kind, target):
    _, actions, decisions, run = harness
    # Deliberately unusable model: simple navigation must work independently of it.
    decisions.append(Decision(status='GOAL_IMPOSSIBLE', summary='Only YouTube is visible'))
    events = run(goal)
    assert len(actions) == 1 and actions[0].kind == kind
    if target:
        assert target in actions[0].args.values()
    assert len(decisions) == 1
    assert any(e.get('status') == 'GOAL_SATISFIED' for e in events)


def test_complex_goal_cannot_finish_at_site_open(harness):
    settings, actions, decisions, run = harness
    settings.max_steps = 8
    decisions.extend([
        Decision(status='GOAL_SATISFIED', summary='Chrome is ready'),
        Decision(status='CONTINUE', summary='Search for the requested product',
                 action=Action(kind='browser_fill', args={'selector':'#search', 'value':'Powerbank 10000mah'})),
        Decision(status='GOAL_SATISFIED', summary='Search field filled'),
        Decision(status='CONTINUE', summary='Submit search', action=Action(kind='browser_click', args={'selector':'#search-submit'})),
        Decision(status='GOAL_SATISFIED', summary='Matching products visible'),
        Decision(status='GOAL_SATISFIED', summary='Verified matching products visible'),
    ])
    events = run('Open galaxus.ch in Chrome and search for a Powerbank with 10000mah')
    assert [a.kind for a in actions] == ['browser_open', 'browser_fill', 'browser_click']
    assert any(e.get('status') == 'GOAL_SATISFIED' for e in events)
    assert any(e['kind'] == 'RECOVERY' for e in events)


def test_unverified_focus_cannot_finish_new_tab_goal(harness, monkeypatch):
    import agent.controller
    settings, actions, decisions, run = harness
    settings.max_steps = 6
    def focus_only(self, action):
        actions.append(action)
        return json.dumps({'verified': True, 'app':'chrome', 'foreground': True})
    monkeypatch.setattr(agent.controller.Controller, 'execute', focus_only)
    decisions.extend([Decision(status='GOAL_SATISFIED', summary='Chrome is focused') for _ in range(3)])
    events = run('Open a new tab in Chrome')
    assert not any(e.get('status') == 'GOAL_SATISFIED' for e in events)
    assert any(e.get('status') == 'MAX_STEPS_EXCEEDED' for e in events)


def test_navigation_permission_denial_is_not_retried(harness, monkeypatch):
    import agent.controller
    _, actions, _, run = harness
    def decline(self, action):
        actions.append(action)
        raise PermissionError('Declined')
    monkeypatch.setattr(agent.controller.Controller, 'execute', decline)
    events = run('Open Microsoft Store')
    assert len(actions) == 1
    assert any(e.get('status') == 'PERMISSION_DENIED' for e in events)


def test_open_youtube_then_play_cannot_finish_at_navigation(harness, monkeypatch):
    import agent.controller
    settings, actions, decisions, run = harness
    settings.max_steps = 8
    execute = agent.controller.Controller.execute
    def media(self, action):
        if action.kind == 'browser_media':
            self.safety.authorize(action)
            actions.append(action)
            return json.dumps({'operation':action.args['operation'], 'verified':True, 'media':{'paused':False}})
        return execute(self, action)
    monkeypatch.setattr(agent.controller.Controller, 'execute', media)
    events = run('open the opened youtube page and play the video its on')
    assert [a.kind for a in actions] == ['browser_open','browser_media']
    progress = [e for e in events if e['kind'] == 'TASK_PROGRESS']
    assert [e['completed'] for e in progress] == [1,2]
    assert len([e for e in events if e.get('status') == 'GOAL_SATISFIED']) == 1
    assert not decisions  # These verified operations do not need a model to guess.


def test_failed_playback_and_repeated_model_success_claims_never_finish(harness, monkeypatch):
    import agent.controller
    settings, actions, decisions, run = harness
    settings.max_steps = 8
    execute = agent.controller.Controller.execute
    def media(self, action):
        if action.kind == 'browser_media':
            actions.append(action)
            return json.dumps({'operation':action.args['operation'], 'verified':True,
                               'media':{'paused':True}}) if action.args['operation'] == 'state' else json.dumps({'verified':False})
        return execute(self, action)
    monkeypatch.setattr(agent.controller.Controller, 'execute', media)
    decisions.extend([Decision(status='GOAL_SATISFIED',summary='YouTube is open') for _ in range(8)])
    events = run('Open YouTube and play the current video')
    assert not any(e.get('status') == 'GOAL_SATISFIED' for e in events)
    assert any(e['kind'] == 'RECOVERY' and 'Playback' in e.get('message','') for e in events)
