"""Regression checks: open YouTube, search, click result; windowed-game menu targets."""
import json
import queue
from types import SimpleNamespace
from PIL import Image
import pytest
from agent.task_intents import browser_step_action,verified_browser_step
from agent.models import Action
from agent.vision import Frame
from agent.windows_use_engine import WindowsUseBrain
from agent.web_engine import WebEngine
from config import Settings


def test_three_step_youtube_goal_parses_and_resolves_without_reopening():
    from agent.task_progress import TaskProgress
    goal='Open YouTube, search for lo-fi music and click the first video in the results.'
    p=TaskProgress.parse(goal)
    assert len(p.steps)==3, p.steps
    assert browser_step_action(p.steps[0],'https://youtube.com/') is None
    search=browser_step_action(p.steps[1],'https://youtube.com/')
    first=browser_step_action(p.steps[2],'https://www.youtube.com/results?search_query=lo-fi+music')
    assert search==Action(kind='browser_search',args={'query':'lo-fi music'})
    assert first.kind=='browser_first_video'


def test_verified_browser_intents_ignore_model_completions():
    search=Action(kind='browser_search',args={'query':'lo-fi music'})
    good={'verified':True,'action':'browser_search','search_query':'lo-fi music',
          'search_url':'https://www.youtube.com/results?search_query=lo-fi+music'}
    assert verified_browser_step(search,json.dumps(good))
    assert not verified_browser_step(search,json.dumps({**good,'verified':False}))
    first=Action(kind='browser_first_video',args={})
    assert verified_browser_step(first,json.dumps({'verified':True,'action':'browser_first_video',
                                                   'video_url':'https://www.youtube.com/watch?v=123'}))
    assert not verified_browser_step(first,json.dumps({'verified':True,'action':'browser_first_video',
                                                       'video_url':'https://www.youtube.com/'}))


def test_search_uses_existing_cdp_page_not_browser_open():
    class Locator:
        def __init__(self,page):
            self.page=page
        def count(self):return 1
        def fill(self,s):self.page.filled=s
        def press(self,s):
            assert s=='Enter'
            self.page.url='https://www.youtube.com/results?search_query=lo-fi+music'
    class Page:
        url='https://www.youtube.com/'
        def locator(self,selector):
            assert selector=='input[name="search_query"]'
            return Locator(self)
        def wait_for_url(self,*a,**kw):pass
    web=WebEngine(Settings())
    web.page=Page()
    web.snapshot=lambda **e:json.dumps(e)
    result=json.loads(web.search('lo-fi music'))
    assert result['verified'] and result['search_query']=='lo-fi music'
    assert web.page.filled=='lo-fi music'


def test_first_video_clicks_visible_result_and_checks_url():
    class Result:
        def __init__(self,page,visible=True,href='/watch?v=abcd'):
            self.page,self.visible,self.href=page,visible,href
        def is_visible(self):return self.visible
        def get_attribute(self,name):return self.href
        def click(self,timeout=6000):
            self.page.url='https://www.youtube.com/watch?v=abcd'
    class List:
        def __init__(self,page):self.page=page
        def count(self):return 2
        def nth(self,i):return Result(self.page,visible=i==1)
    class Page:
        url='https://www.youtube.com/results?search_query=lo-fi+music'
        def locator(self,selector):
            assert 'ytd-video-renderer' in selector
            return List(self)
        def wait_for_url(self,*a,**kw): pass
    web=WebEngine(Settings())
    web.page=Page()
    web.context=SimpleNamespace(pages=[web.page])
    web.snapshot=lambda **e:json.dumps(e)
    result=json.loads(web.first_video())
    assert result['verified'] and result['clicked_index']==1
    assert result['video_url'].endswith('v=abcd')


def test_first_video_does_not_click_nonavailable_results():
    class Page:
        url='https://www.youtube.com/'
        def locator(self,selector):return SimpleNamespace(count=lambda:0)
    web=WebEngine(Settings())
    web.page=Page()
    with pytest.raises(RuntimeError,match='No visible YouTube video'):
        web.first_video()


def test_planner_hides_reopening_tools_in_browser_search_phase():
    tools=[SimpleNamespace(name=name) for name in ('browser_open','browser_navigate',
          'browser_new_tab','ensure_app','open_app','browser_search','browser_click_target')]
    frame=Frame(Image.new('RGB',(640,400)),(1280,800),source='browser')
    chosen=WindowsUseBrain.filter_navigation_tools(tools,'search for lo-fi music',frame)
    assert {t.name for t in chosen}=={'browser_search','browser_click_target'}
    assert len(WindowsUseBrain.filter_navigation_tools(tools,'open YouTube',frame))==len(tools)


def test_game_menu_pixel_to_physical_windowed_position():
    frame=Frame(Image.new('RGB',(800,450)),(1600,900),origin=(215,151),
                window=543,window_bounds=(200,120,1815,1090),source='game')
    assert frame.point(400,225)==(1015,601)
    with pytest.raises(ValueError,match='outside latest'):
        frame.point(400,800)
    assert frame.source=='game'


def test_game_menu_action_requires_coordinates_but_game_click_does_not():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Action(kind='game_menu_click',args={})
    action=Action(kind='game_menu_click',args={'x':250,'y':120})
    assert action.args['coordinate_space']=='screenshot'
