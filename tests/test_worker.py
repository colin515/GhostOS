from contextlib import nullcontext
import queue
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


def test_declared_impossible_dispatches_nothing(harness):
    _, actions, decisions, run = harness
    decisions.append(Decision(status='GOAL_IMPOSSIBLE', summary='blocked'))
    events = run()
    assert not actions
    assert any(e.get('status') == 'GOAL_IMPOSSIBLE' for e in events)
