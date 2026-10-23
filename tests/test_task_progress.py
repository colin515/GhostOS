import pytest
from agent.task_progress import TaskProgress, playback_action


def test_youtube_request_keeps_playback_as_a_separate_pending_step():
    progress = TaskProgress.parse('open the opened youtube page and play the video its on')
    assert len(progress.steps) == 2
    progress.complete('Existing YouTube tab verified')
    assert not progress.done
    assert progress.current == 'play the video its on'
    assert 'Original complete request' in progress.prompt()
    assert playback_action(progress.current).args['operation'] == 'play'
    progress.complete('Playback time advanced')
    assert progress.done


def test_typing_payloads_and_negation_are_not_split_into_new_commands():
    assert len(TaskProgress.parse('Type "hello and open Notepad"').steps) == 1
    assert len(TaskProgress.parse("Don't open Chrome and play the video").steps) == 1
    assert len(TaskProgress.parse('/action {"kind":"type_text","args":{"text":"x and open y"}}').steps) == 1


def test_explicit_multiple_apps_remain_separate_but_browser_destination_is_one_operation():
    assert TaskProgress.parse('Open Notepad and open Calculator').steps == ['Open Notepad', 'open Calculator']
    assert len(TaskProgress.parse('Open Chrome and open Netflix').steps) == 1


@pytest.mark.parametrize('goal', ['Play the video named Cats', 'Play the video about cats',
                                  'Find a video and play it', 'Do not play the video', 'Explain how to play a video'])
def test_direct_playback_never_replaces_a_search_or_question(goal):
    assert playback_action(goal) is None
