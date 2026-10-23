"""Idempotent media control: read state first, never blindly toggle playback."""
from __future__ import annotations
import json
import re
import time
from urllib.parse import urlsplit


def cdp_media(page, operation):
    candidates = [node for node in page.locator('video,audio').element_handles()[:20] if node.is_visible()]
    if len(candidates) != 1:
        return {'operation': operation, 'verified': False,
                'message': f'Found {len(candidates)} visible players. Inspect the page to choose the intended media.'}
    node = candidates[0]
    read = lambda: node.evaluate('e => ({paused:e.paused,ended:e.ended,current_time:e.currentTime,ready_state:e.readyState,error:e.error ? e.error.code : null})')
    before = read()
    if operation == 'state':
        return {'operation': operation, 'verified': True, 'media': before}
    if operation == 'pause':
        node.evaluate('e => e.pause()')
    elif before['paused'] or before['ended']:
        # A real Play click supplies a user gesture when Chromium blocks script play().
        host = (urlsplit(getattr(page,'url','')).hostname or '').lower()
        buttons = (page.locator('button.ytp-play-button') if host in ('youtube.com','www.youtube.com','m.youtube.com') else
                   page.get_by_role('button', name=re.compile(r'^play(?:\s*\(k\)| video)?$', re.I)))
        visible = [button for button in buttons.all()[:20] if button.is_visible()]
        if len(visible) == 1:
            visible[0].click(timeout=3000)
        else:
            node.evaluate('async e => { await Promise.race([e.play(), new Promise((_,reject) => setTimeout(() => reject(new Error("Playback did not start")),2500))]); }')
    until = time.monotonic() + 4
    while time.monotonic() < until:
        state = read()
        verified = state['paused'] if operation == 'pause' else (
            not state['paused'] and not state['ended'] and state['ready_state'] >= 2 and not state['error']
            and state['current_time'] > before['current_time'])
        if verified:
            return {'operation': operation, 'verified': True, 'media': state, 'evidence': 'HTML5 media state and playback time'}
        page.wait_for_timeout(100)
    return {'operation': operation, 'verified': False, 'media': read(),
            'message': 'The player did not reach the requested state. Inspect buffering, login, consent or playback errors.'}


def native_media(native, operation):
    """Read YouTube's actual accessible Play/Pause button; no space-bar guessing."""
    import uiautomation as auto
    native.apps.focus(native.app)
    _, url = native.chrome()
    if (urlsplit(url).hostname or '').lower() not in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        return json.dumps({'operation': operation, 'verified': False,
                           'message': 'Native media control needs the YouTube player. Use the current screenshot/UIA for other sites.'})

    def buttons():
        found, visited = [], 0
        def visit(control, depth):
            nonlocal visited
            native.check()
            visited += 1
            if depth > 24 or visited > 700:
                return
            try:
                name = control.Name
                label = re.sub(r'\s*\(k\)\s*$', '', name).strip().casefold()
                play_labels = {'play','abspielen','wiedergabe','wiedergabe starten','lire','reproducir','riproduci'}
                pause_labels = {'pause','pausa','pausar','anhalten','mettre en pause'}
                if control.ControlTypeName == 'ButtonControl' and re.search(r'\(k\)\s*$', name, re.I) and label in play_labels | pause_labels:
                    found.append((control, label in pause_labels))
                    return
                for child in control.GetChildren()[:100]:
                    visit(child, depth + 1)
            except (InterruptedError, PermissionError):
                raise
            except Exception:
                pass
        visit(auto.GetForegroundControl(), 0)
        return found

    controls = buttons()
    if len(controls) != 1:
        return json.dumps({'operation': operation, 'verified': False,
                           'message': 'Player control is unavailable or ambiguous. Inspect the screenshot; do not assume playback.'})
    control, playing = controls[0]
    desired = operation == 'play'
    if operation != 'state' and playing != desired:
        from agent.mouse import MouseDriver
        rect = control.BoundingRectangle
        MouseDriver(native.stop).click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        until = time.monotonic() + 3
        while time.monotonic() < until:
            native.check()
            current = buttons()
            if len(current) == 1:
                playing = current[0][1]
                if playing == desired:
                    break
            if native.stop.wait(0.15):
                native.check()
    return json.dumps({'transport': 'native', 'url': url, 'operation': operation,
                       'verified': operation == 'state' or playing == desired,
                       'media': {'paused': not playing}, 'evidence': 'YouTube accessible player control'})
