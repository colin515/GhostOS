import json
from config import Settings
from agent.context_budget import pack_prompt


def test_large_observations_are_trimmed_without_losing_goal_outcome_or_control_identity():
    goal = 'Open the existing YouTube page and play the video it is on'
    controls = [{'name':'Player ' * 20,'type':'ButtonControl','window':'YouTube','x':i,'y':20} for i in range(100)]
    desktop = {'foreground':'YouTube','windows':[],'controls':controls}
    feedback = 'DECISION_ACTION_REQUIRED. Playback has not started. ' + 'x' * 8000
    raw = pack_prompt(goal,'history ' * 900,desktop,'',feedback,(1024,768),Settings(),4167,5861)
    prompt = json.loads(raw)
    assert prompt['goal'] == goal
    assert prompt['feedback'].startswith('DECISION_ACTION_REQUIRED. Playback has not started.')
    assert prompt['desktop']['controls'][0] == controls[0]
    assert len(prompt['desktop']['controls']) < 100
    assert len(raw) < 9000
    assert len(desktop['controls']) == 100
