"""Resolve names against installed inventory; ambiguous names never become commands."""
import re
from difflib import SequenceMatcher

ALIASES = {'minecraft':('minecraft launcher','minecraft for windows'),
           'roblox':('roblox','roblox player'), 'vs code':('visual studio code',),
           'word':('word','microsoft word'), 'excel':('excel','microsoft excel')}


def normalized(name):
    return ''.join(re.findall(r'\w+',str(name).casefold()))


def resolve_installed(name, names):
    names = list(names)
    wanted = normalized(name)
    exact = [item for item in names if normalized(item) == wanted]
    if len(exact) == 1:
        return exact[0]
    for alias, labels in ALIASES.items():
        if wanted == normalized(alias):
            for label in labels:
                matches = [item for item in names if normalized(item) == normalized(label)]
                if len(matches) == 1:
                    return matches[0]
    scored = []
    for item in names:
        if re.findall(r'\d+',name) != re.findall(r'\d+',item):
            continue  # Never silently turn Portal 2 into Portal 1.
        variants = [item] + [alias for alias, labels in ALIASES.items() if normalized(item) in map(normalized,labels)]
        scored.append((max(SequenceMatcher(None,wanted,normalized(v)).ratio() for v in variants),item))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= .86 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= .12):
        return scored[0][1]
    candidates = ', '.join(item for score,item in scored[:5] if score >= .45)
    raise FileNotFoundError(f'No unambiguous installed app matches {name!r}. Candidates: {candidates or "none"}. Use app_list and an exact installed name.')
