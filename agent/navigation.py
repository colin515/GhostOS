"""Deterministic navigation prerequisites and evidence, independent of vision verdicts."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import re
from urllib.parse import urlsplit
from agent.models import Action
from agent.windows_apps import requested_app

# Only names in the user's own request are resolved. Never invent a URL from page text.
SITES = {'netflix': 'https://www.netflix.com/', 'youtube': 'https://www.youtube.com/',
         'galaxus': 'https://www.galaxus.ch/', 'google': 'https://www.google.com/',
         'wikipedia': 'https://www.wikipedia.org/', 'github': 'https://github.com/'}
DOMAIN = re.compile(r'(?<![\w@./])(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d+)?(?:/[^\s<>"\']*)?')


def same_destination(actual, requested):
    """Root requests may reuse a deeper page on the same site; explicit paths stay exact."""
    try:
        a, b = urlsplit(actual), urlsplit(requested)
        host = lambda p: (p.hostname or '').lower().removeprefix('www.')
        return (a.scheme in ('http', 'https') and host(a) == host(b) and a.port == b.port
                and (b.path in ('', '/') or a.path.rstrip('/') == b.path.rstrip('/'))
                and (not b.query or a.query == b.query))
    except ValueError:
        return False


@dataclass
class Navigation:
    goal: str
    app: str | None = None
    url: str = ''
    new_tab: bool = False
    simple: bool = False
    attempts: int = 0
    verified: bool = False
    evidence: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, goal, game_mode=False):
        task = cls(goal or '')
        text = task.goal.lower()
        if game_mode or re.search(r"\b(?:don't|do not|never)\b|\b(?:how (?:do|can|to)|explain|tell me how)\b", text):
            return task
        task.app = requested_app(text)
        task.new_tab = bool(re.search(r'\b(?:new|another)\s+(?:browser\s+)?tab\b', text))
        match = DOMAIN.search(task.goal)
        remaining = text
        # Spoken fallback clauses do not add a second task ("if you can't see Chrome, open it").
        if task.new_tab and re.search(r"\bif\b.*\b(?:can't|cannot|not)\b.*\b(?:see|open|running)\b", text):
            first, tail = re.split(r'\bif\b', remaining, maxsplit=1)
            if not re.search(r'\b(?:search|fill|find|buy|complete|homework|download|send|watch|play)\b', tail):
                remaining = first
        if match:
            task.url = match.group().rstrip('.,;!?')
            if not task.url.startswith(('http://', 'https://')):
                task.url = 'https://' + task.url
            remaining = remaining.replace(match.group().lower(), ' ')
        elif re.search(r'\b(?:open|go|navigate|visit|switch|show|access)\b', text):
            for name, url in SITES.items():
                # "Google Chrome" is an application, not a request for google.com.
                if name == 'google' and 'google chrome' in text:
                    continue
                if re.search(r'\b' + re.escape(name) + r'\b', text):
                    task.url = url
                    remaining = re.sub(r'\b' + name + r'\b', ' ', remaining)
                    break
        if not (task.app or task.url or task.new_tab):
            return task
        if not re.search(r'\b(?:open|launch|start|go|navigate|visit|switch|show|access|bring)\b', text):
            task.app = None  # Mentioning an app is not authorization to launch it.
            task.new_tab = False
            return task
        # Conservative completion grammar. Unknown words mean there is work beyond navigation.
        from agent.windows_apps import ALIASES
        for alias in sorted(ALIASES, key=len, reverse=True):
            remaining = re.sub(r'\b' + re.escape(alias) + r'\b', ' ', remaining)
        allowed = set('i would like want need you to just please could can will okay ok open launch start go navigate visit switch show access bring up a an the in on into of for me my and then website site webpage page home homepage new another browser tab window app application it now thanks thank opened existing already running currently active displayed'.split())
        words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", remaining)
        task.simple = bool(words) and all(word in allowed for word in words)
        return task

    @property
    def active(self):
        return bool(self.app or self.url or self.new_tab)

    def next_action(self):
        # Distinct, bounded navigation remedies; the overall goal loop remains unlimited.
        if self.verified or not self.active or self.attempts >= 3:
            return None
        if self.url:
            return Action(kind='browser_open', args={'url': self.url, 'new_tab': self.new_tab,
                          'backend': ('auto', 'native', 'cdp')[self.attempts]})
        if self.new_tab:
            return Action(kind='browser_new_tab', args={'backend': ('auto', 'native', 'cdp')[self.attempts]})
        return Action(kind='ensure_app', args={'name': self.app, 'strategy': 'launch'})

    def record(self, result):
        self.attempts += 1
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if not isinstance(data, dict):
                return
            self.evidence = data
            # Record fulfillment of the prerequisite; later task steps can legitimately leave it.
            if self.verified:
                return
            if self.url:
                self.verified = bool(data.get('verified') and same_destination(data.get('url', ''), self.url)
                                     and (not self.new_tab or data.get('created_tab')))
            elif self.new_tab:
                self.verified = bool(data.get('verified') and data.get('created_tab'))
            else:
                self.verified = bool(data.get('verified') and data.get('app') == self.app and data.get('foreground'))
        except (ValueError, TypeError):
            pass

    def success_message(self):
        if self.url:
            host = urlsplit(self.url).hostname
            if self.new_tab:
                return f'Opened {host} in a new tab.'
            return f'Switched to the existing {host} tab.' if self.evidence.get('reused_tab') else f'Opened {host}.'
        if self.new_tab:
            return 'Opened a new browser tab.'
        from agent.windows_apps import APPS
        return f'{APPS[self.app].label} is open.'

    def context(self):
        return ('\nNavigation requirements: ' + json.dumps({'app': self.app, 'url': self.url,
                'new_tab': self.new_tab, 'verified': self.verified, 'attempts': self.attempts,
                'navigation_only': self.simple, 'evidence': self.evidence}, ensure_ascii=False)[:3500]
                + '\nFocus alone is not a new tab or website navigation. A different current website is not a blocker. '
                  'Use browser_open to switch to the requested site or enter its URL. '
                  'Opening the app/site is only a prerequisite when the goal includes additional work.')
