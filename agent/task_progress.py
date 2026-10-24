"""Keep explicit sequential requests pending until each step has been verified."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import re
from agent.models import Action

VERBS = r'open|launch|go|navigate|switch|search|find|play|watch|resume|pause|fill|type|click|select|download|upload|save|create|move|copy|paste|rename|delete|close|complete|finish|solve|answer|read|check|send|submit|turn|set|scroll|maximize|minimize|do'
SPLIT = re.compile(r'\s+(?:and\s+then|then|after\s+that)\s+|\s+and\s+(?=(?:' + VERBS + r')\b)|[,.;]\s+(?=(?:' + VERBS + r')\b)', re.I)


@dataclass
class TaskProgress:
    original: str
    steps: list[str]
    index: int = 0
    completed: list[dict] = field(default_factory=list)

    @classmethod
    def parse(cls, goal, game_mode=False):
        text = goal or ''
        if text.startswith('/action ') or re.search(r"\b(?:don't|do not|never|how do|how can|explain)\b", text, re.I):
            return cls(text, [text])
        quoted = [m.span() for m in re.finditer(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'', text)]
        from agent.navigation import DOMAIN
        quoted += [(m.start(), m.start() + len(m.group().rstrip('.,;!?'))) for m in DOMAIN.finditer(text)]
        parts, start = [], 0
        for match in SPLIT.finditer(text):
            if any(a <= match.start() < b for a, b in quoted):
                continue
            part = text[start:match.start()].strip(' ,')
            filler = set('okay ok please i would like want need you to can could will'.split())
            preface = not parts and all(word in filler for word in re.findall(r'[a-z]+', part.lower()))
            if part and not preface:
                parts.append(part)
            start = match.end()
        parts.append(text[start:].strip(' ,'))
        parts = [part for part in parts if part] or [text]
        # "Open Chrome and open Netflix" is one browser destination, not two launches.
        if len(parts) == 2:
            from agent.navigation import Navigation
            first, second = map(Navigation.parse, parts)
            if first.simple and first.app in ('chrome', 'edge', 'firefox') and second.simple and second.url:
                parts = [text]
        return cls(text, parts)

    @property
    def current(self):
        return self.steps[self.index]

    @property
    def done(self):
        return self.index >= len(self.steps)

    @property
    def requires_work(self):
        return bool(re.search(r'\b(?:play|watch|resume|pause|search|find|fill|type|click|select|download|upload|save|create|move|copy|paste|rename|delete|complete|finish|beat|win|solve|answer|send|submit|turn|set|scroll|maximize|minimize|do)\b', self.current, re.I))

    def complete(self, evidence):
        self.completed.append({'step': self.index + 1, 'goal': self.current, 'evidence': str(evidence)[:600]})
        self.index += 1

    def prompt(self):
        if len(self.steps) == 1:
            return self.original
        return ('Original complete request: ' + self.original + '\n'
                + 'Current step ' + str(self.index + 1) + '/' + str(len(self.steps)) + ': ' + self.current
                + '\nComplete ONLY this step now. Earlier steps stay complete; do not reopen their pages or repeat their writes. '
                + 'GhostOS will advance to the remaining steps after verification. Completed: '
                + json.dumps(self.completed[-5:], ensure_ascii=False))


def playback_action(goal):
    text = goal.lower()
    if re.search(r"\b(?:don't|do not|never|how|explain)\b", text):
        return None
    # Only an explicit request for the current media is a direct operation. A named
    # video/search request still goes through the planner to find the requested target.
    if not re.search(r'\b(?:video|clip|media|playback)\b', text):
        return None
    if re.search(r'\b(?:search|find|called|named|titled)\b|https?://', text):
        return None
    allowed = set("please can could would you i want like to just play resume pause the this that current currently already opened open video clip media playback it its it's is on now youtube a an for me".split())
    if any(word not in allowed for word in re.findall(r"[a-z]+(?:'[a-z]+)?", text)):
        return None
    if re.search(r'\b(?:play|resume|pause)\b', text):
        operation = 'pause' if re.search(r'\bpause\b', text) else 'play'
        return Action(kind='browser_media', args={'operation': operation})
    return None
