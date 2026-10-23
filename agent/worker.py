"""Observe, execute, verify; terminal failure requires a finite recovery history."""
from __future__ import annotations
from pathlib import Path
import os
import queue
import time
from agent.recovery import Recovery


def run_worker(settings, goal, recipe_path, stop, events, answers):
    last_emit = {}
    def emit(kind, **data):
        now = time.monotonic()
        if kind == 'INFERENCE' and now - last_emit.get(kind, 0) < 1:
            return
        last_emit[kind] = now
        try:
            events.put({'kind': kind, **data}, timeout=0.2)
        except queue.Full:
            if kind not in ('FRAME', 'INFERENCE'):
                raise RuntimeError('Event channel overloaded')

    controller = None
    deadline = time.monotonic() + settings.max_runtime if settings.max_runtime else float('inf')
    try:
        from config import enable_dpi_awareness
        enable_dpi_awareness()
        from agent.window_focus import register_ui_process
        register_ui_process(__import__('os').getppid())
        if os.name == 'nt':
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin():
                raise PermissionError('Run GhostOS without Administrator rights. UAC stays under manual control.')
        from agent.safety import WorkerSafety
        from agent.vision import Vision
        from agent.ui_tree import UITree, uia_context
        from agent.controller import Controller
        from agent.brain import Brain
        recovery = Recovery(goal, settings.game_mode)
        if recovery.app == 'chrome' and hasattr(settings, 'browser_channel'):
            from dataclasses import replace
            settings = replace(settings, browser_channel='chrome')
        safety = WorkerSafety(settings, stop, events, answers)
        vision = Vision(settings.screenshot_width, settings.data_dir / 'templates')
        tree = UITree()
        controller = Controller(settings, safety, tree, vision)
        if settings.game_mode:
            emit('PLAN', message='Focus your game now. Starting capture in 3 seconds.')
            if stop.wait(3):
                safety.check()
        recipe = None
        if recipe_path:
            from automation.recipe_parser import load_recipe
            recipe = load_recipe(Path(recipe_path))
        fast = Brain.fast_command(goal or '') if recipe is None else None
        autonomous = recipe is None and fast is None
        feedback, browser_state, inference_errors, stalls = '', '', 0, 0
        last_frame_time = 0.0
        with uia_context():
            if autonomous and recovery.app:
                # Resolve focus/installation before spending tokens analysing the wrong application.
                for _ in range(2):
                    safety.check()
                    if time.monotonic() >= deadline:
                        emit('STATUS', status='MAX_RUNTIME_EXCEEDED')
                        return
                    if recovery.attempt(controller, emit, 'Preparing the application requested in your goal'):
                        break
                feedback = recovery.context()
                if recovery.app in ('chrome', 'edge'):
                    import re
                    match = re.search(r'(?<![\w@./])(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>"\']*)?', goal or '')
                    if match:
                        from agent.models import Action
                        url = match.group(0).rstrip('.,;!?')
                        if not url.startswith(('https://', 'http://')):
                            url = 'https://' + url
                        try:
                            browser_state = str(controller.execute(Action(kind='browser_navigate', args={'url':url})))
                            emit('RESULT', message=browser_state[:4000])
                        except (PermissionError, InterruptedError):
                            raise
                        except Exception as exc:
                            emit('WARNING', message=f'Browser preflight: {exc}. Replanning with native controls.')
            brain = None
            step = -1
            while not stop.is_set():
                step += 1
                if settings.max_steps and step >= settings.max_steps:
                    emit('STATUS', status='MAX_STEPS_EXCEEDED')
                    return
                safety.check()
                if time.monotonic() > deadline:
                    emit('STATUS', status='MAX_RUNTIME_EXCEEDED')
                    return
                frame = vision.capture()
                controller.frame = frame
                emit('FRAME', image=frame.base64(grid=not settings.game_mode), step=step)
                try:
                    ui = tree.snapshot() if not settings.game_mode and not getattr(getattr(controller, 'web', None), 'page', None) else []
                except Exception as exc:
                    ui = []
                    emit('WARNING', message=f'Accessibility provider unavailable; using vision and keyboard navigation: {exc}')
                if recipe is not None:
                    action = recipe.steps[step]
                elif fast:
                    action = fast
                else:
                    try:
                        if brain is None:
                            brain = Brain(settings)
                        decision = brain.next(goal, frame, ui, browser_state, feedback, emit)
                        inference_errors = 0
                    except (InterruptedError, PermissionError):
                        raise
                    except Exception as exc:
                        inference_errors += 1
                        emit('ERROR', message=f'Local model response failed (attempt {inference_errors}): {type(exc).__name__}: {exc}')
                        feedback = 'Return one compact schema-valid decision. The last response was invalid or unavailable.' + recovery.context()
                        if stop.wait(min(30, 2 ** min(inference_errors, 5))):
                            safety.check()
                        continue
                    emit('THOUGHT', message=decision.summary)
                    emit('PLAN', steps=decision.plan)
                    if decision.status == 'GOAL_IMPOSSIBLE':
                        emit('BLOCKED', message=decision.summary)
                        if not recovery.exhausted:
                            recovery.attempt(controller, emit, decision.summary)
                        else:
                            # Re-observe with a cooldown; never replay an uncertain write.
                            if stop.wait(min(15, 1 + stalls)):
                                safety.check()
                            stalls += 1
                        feedback = 'The goal remains active. Inspect fresh evidence, choose another safe strategy, or wait for the user to unblock the desktop. Focus is recoverable. Do not repeat uncertain writes.' + recovery.context()
                        continue
                    if decision.status == 'GOAL_SATISFIED':
                        emit('STATUS', status=decision.status, message=decision.summary)
                        return
                    action = decision.action
                emit('ACTION', step=step + 1, action=action.model_dump())
                try:
                    result = controller.execute(action)
                    if action.kind.startswith('browser_'):
                        browser_state = str(result)
                    feedback = str(result)[:4000]
                    emit('RESULT', message=feedback)
                    if settings.game_mode:
                        until = min(deadline, time.monotonic() + settings.vision_interval)
                        while time.monotonic() < until:
                            if stop.wait(1 / settings.game_poll_hz):
                                safety.check()
                            latest = vision.capture()
                            detections = {}
                            for path in sorted(vision.templates.glob('*.png'))[:5]:
                                hit = vision.match(latest, path.name)
                                if hit:
                                    detections[path.name] = hit
                            if time.monotonic() - last_frame_time >= settings.screenshot_interval:
                                emit('FRAME', image=latest.base64(), matches=detections, step=step)
                                last_frame_time = time.monotonic()
                            if detections:
                                feedback = (feedback + '\nTemplate observations: ' + str(detections))[-4000:]
                    elif autonomous and action.kind in ('click', 'ui_click', 'hotkey', 'type_text', 'browser_navigate', 'open_app', 'ensure_app'):
                        changed = False
                        until = min(deadline, time.monotonic() + 2)
                        while time.monotonic() < until:
                            if stop.wait(0.2):
                                safety.check()
                            if vision.changed(frame, vision.capture()):
                                changed = True
                                break
                        if not changed:
                            stalls += 1
                            emit('RECOVERY', message='No screen change after two seconds. Refreshing targets; the previous action will not be replayed.')
                            if not recovery.exhausted:
                                recovery.attempt(controller, emit, 'Screen did not change')
                            feedback += '\nTargets may be stale. Recalculate coordinates or use keyboard navigation. Never replay a submission or command after an uncertain outcome.'
                        else:
                            stalls = 0
                except (PermissionError, InterruptedError):
                    raise
                except Exception as exc:
                    feedback = f'{type(exc).__name__}: {exc}'
                    emit('ERROR', message=feedback)
                    if not autonomous:
                        raise
                    if recovery.exhausted:
                        if stop.wait(min(15, 1 + stalls)):
                            safety.check()
                        stalls += 1
                    recovery.attempt(controller, emit, feedback)
                if brain:
                    brain.context.add(action.model_dump(), feedback)
                    feedback += recovery.context()
                if recipe is not None and step + 1 >= len(recipe.steps):
                    emit('STATUS', status='RECIPE_COMPLETED', message='All recipe steps executed; goal is not independently verified.')
                    return
                if fast is not None:
                    emit('STATUS', status='COMMAND_COMPLETED')
                    return
            safety.check()
    except InterruptedError:
        emit('STATUS', status='STOPPED')
    except PermissionError as exc:
        emit('STATUS', status='PERMISSION_DENIED', message=str(exc))
    except Exception as exc:
        emit('STATUS', status='ERROR', message=f'{type(exc).__name__}: {exc}')
    finally:
        if controller:
            try:
                controller.close()
            except Exception as exc:
                emit('ERROR', message=f'Cleanup: {exc}')
        emit('WORKER_DONE')
