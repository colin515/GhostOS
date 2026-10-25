"""Conservative, deterministic site-specific tasks; never invent unseen content."""
from __future__ import annotations
import re
from urllib.parse import urlsplit
from agent.models import Action


def browser_step_action(step, url):
    """Recognize a simple step after its website is already open."""
    host=(urlsplit(url or '').hostname or '').lower().removeprefix('www.')
    if host != 'youtube.com':
        return None
    text=' '.join((step or '').strip().split())
    search=re.fullmatch(r'(?:please\s+)?search\s+(?:for\s+)?(.+?)(?:\s+on\s+youtube)?[.!?]?',text,re.I)
    if search:
        query=search.group(1).strip(' .!?')
        return Action(kind='browser_search',args={'query':query}) if query else None
    first=re.fullmatch(
        r'(?:please\s+)?(?:click|open|select|play|watch)\s+(?:on\s+)?(?:the\s+)?first\s+'
        r'(?:video|video result|video in the results?|result(?:ing)? video)'
        r'(?:\s+(?:you\s+see|in\s+the\s+results?|from\s+the\s+results?))?[.!?]?',
        text,re.I)
    if first:
        return Action(kind='browser_first_video',args={})
    return None


def verified_browser_step(action, result):
    """Advance only on backend evidence, not a claimed model outcome."""
    import json
    try:
        data=json.loads(result) if isinstance(result,str) else result
    except (ValueError,TypeError):
        return False
    if not isinstance(data,dict) or not data.get('verified'):
        return False
    return ((action.kind=='browser_search' and data.get('action')=='browser_search'
             and bool(data.get('search_query')) and bool(data.get('search_url')))
            or (action.kind=='browser_first_video' and data.get('action')=='browser_first_video'
                and '/watch?' in str(data.get('video_url',''))))
