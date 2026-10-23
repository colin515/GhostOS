import json
import pytest
from agent.navigation import Navigation, same_destination


@pytest.mark.parametrize('goal,app,url,new_tab,simple', [
    ('I would like you to just open Microsoft Store', 'store', '', False, True),
    ('Okay, Open Google Chrome and Open In Google Chrome, the Netflix website.', 'chrome', 'https://www.netflix.com/', False, True),
    ('Could you open a new tab in Google Chrome?', 'chrome', '', True, True),
    ("Could you open a new tab in Google Chrome? If Google Chrome, if you can't see Google Chrome, just open a new Google Chrome app or window, whatever.", 'chrome', '', True, True),
    ('Open galaxus.ch in Google Chrome and search for a Powerbank with 10000mah', 'chrome', 'https://galaxus.ch', False, False),
    ('Open Netflix in a new tab in Chrome', 'chrome', 'https://www.netflix.com/', True, True),
    ('Open https://example.com/homework and answer the questions', None, 'https://example.com/homework', False, False),
    ('Open Chrome', 'chrome', '', False, True),
])
def test_user_navigation_intents(goal, app, url, new_tab, simple):
    task = Navigation.parse(goal)
    assert (task.app, task.url, task.new_tab, task.simple) == (app, url, new_tab, simple)


@pytest.mark.parametrize('goal', ["Don't open Chrome", 'Tell me how to open Netflix',
                                   'Explain how to open Microsoft Store', 'Chrome is installed'])
def test_mentions_and_negation_are_not_launch_authority(goal):
    assert not Navigation.parse(goal).active


def test_screen_focus_is_not_new_tab_evidence():
    task = Navigation.parse('Open a new tab in Chrome')
    task.record(json.dumps({'verified': True, 'app': 'chrome', 'foreground': True}))
    assert not task.verified
    task.record(json.dumps({'verified': True, 'created_tab': True}))
    assert task.verified


def test_wrong_current_site_does_not_verify_requested_destination():
    task = Navigation.parse('Open Netflix in Chrome')
    task.record(json.dumps({'verified': True, 'url': 'https://www.youtube.com/watch?v=123'}))
    assert not task.verified
    assert task.next_action().args['url'] == 'https://www.netflix.com/'
    task.record(json.dumps({'verified': True, 'url': 'https://www.netflix.com/browse', 'reused_tab': True}))
    assert task.verified


def test_unverified_dispatch_is_not_success():
    task = Navigation.parse('Open Microsoft Store')
    task.record('launch requested')
    assert not task.verified
    task.record(json.dumps({'verified': True, 'app': 'store', 'foreground': True}))
    assert task.verified


def test_distinct_fallbacks_do_not_exhaust_overall_goal():
    task = Navigation.parse('Open Netflix in Chrome')
    backends = []
    for _ in range(3):
        backends.append(task.next_action().args['backend'])
        task.record(None)
    assert backends == ['auto', 'native', 'cdp']
    assert task.next_action() is None
    assert task.active and not task.verified


def test_destination_checks_host_not_title_or_url_substring():
    assert same_destination('https://netflix.com/browse', 'https://www.netflix.com/')
    assert not same_destination('https://netflix.com.evil.test', 'https://netflix.com/')
    assert not same_destination('https://example.com/?next=netflix.com', 'https://netflix.com/')
    assert not same_destination('https://example.com/two', 'https://example.com/one')
    assert not same_destination('https://example.com:444/', 'https://example.com/')
