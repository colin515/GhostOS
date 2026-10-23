"""Execute explicit navigation first, then observe, act and verify the full goal."""
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

    controller = brain = None
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
        from agent.navigation import Navigation
        navigation = Navigation.parse(goal, settings.game_mode)
        recovery = Recovery(goal, settings.game_mode)
        if navigation.app == 'chrome' and hasattr(settings, 'browser_channel'):
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
            brain = None
            step = -1
            substantive_actions = 0
            completion_challenge = False
            while not stop.is_set():
                step += 1
                if settings.max_steps and step >= settings.max_steps:
                    emit('STATUS', status='MAX_STEPS_EXCEEDED')
                    return
                safety.check()
                if time.monotonic() > deadline:
                    emit('STATUS', status='MAX_RUNTIME_EXCEEDED')
                    return
                if autonomous:
                    prerequisite = navigation.next_action()
                    if prerequisite:
                        emit('PLAN', message='Opening the requested destination directly and verifying the result')
                        emit('ACTION', step=step + 1, action=prerequisite.model_dump(), navigation=True)
                        try:
                            result = controller.execute(prerequisite)
                            navigation.record(result)
                            feedback = str(result)[:4000] + navigation.context()
                            if prerequisite.kind.startswith('browser_'):
                                browser_state = str(result)
                            emit('RESULT', message=str(result)[:4000])
                            if navigation.simple and navigation.verified:
                                emit('STATUS', status='GOAL_SATISFIED', message=navigation.success_message())
                                return
                        except (InterruptedError, PermissionError):
                            raise
                        except Exception as exc:
                            navigation.record(None)
                            feedback = f'Navigation attempt {navigation.attempts}: {type(exc).__name__}: {exc}' + navigation.context()
                            emit('RECOVERY', message=feedback[:1200])
                        continue
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
                            if getattr(settings, 'computer_use_engine', 'native') == 'windows_use' and not settings.game_mode:
                                from agent.windows_use_engine import WindowsUseBrain
                                brain = WindowsUseBrain(settings)
                                emit('ENGINE', message='Windows-Use SDK · local Ollama · GhostOS permissions')
                            else:
                                brain = Brain(settings)
                        decision = brain.next(goal, frame, ui, browser_state, feedback + navigation.context(), emit)
                        inference_errors = 0
                    except (InterruptedError, PermissionError):
                        raise
                    except Exception as exc:
                        inference_errors += 1
                        emit('ERROR', message=f'Local model response failed (attempt {inference_errors}): {type(exc).__name__}: {exc}')
                        feedback = ('DECISION_ACTION_REQUIRED. ' if 'DECISION_ACTION_REQUIRED' in feedback else '') + 'Return one compact schema-valid decision. The last response was invalid or unavailable.' + recovery.context()
                        if stop.wait(min(30, 2 ** min(inference_errors, 5))):
                            safety.check()
                        continue
                    if decision.status == 'GOAL_IMPOSSIBLE':
                        emit('MODEL_VERDICT_REJECTED', status=decision.status, message=decision.summary)
                        emit('RECOVERY', message='The current screen is not a reason to stop. Checking another navigation strategy.')
                        if not recovery.exhausted:
                            recovery.attempt(controller, emit, 'Checking focus and launch while keeping the goal active')
                        else:
                            # Re-observe with a cooldown; never replay an uncertain write.
                            if stop.wait(min(15, 1 + stalls)):
                                safety.check()
                            stalls += 1
                        feedback = 'DECISION_ACTION_REQUIRED. The goal remains active. Inspect fresh evidence, choose another safe strategy, or wait for the user to unblock the desktop. Focus is recoverable. Do not repeat uncertain writes.' + recovery.context()
                        continue
                    if decision.status == 'GOAL_SATISFIED':
                        if navigation.active and not navigation.verified:
                            try:
                                navigation.record(controller.navigation_evidence(navigation))
                            except (InterruptedError, PermissionError):
                                raise
                            except Exception:
                                pass
                        # The model cannot replace requested operations with "Chrome is focused".
                        missing_navigation = navigation.active and not navigation.verified
                        unfinished_work = navigation.active and not navigation.simple and not substantive_actions
                        if missing_navigation or unfinished_work:
                            emit('RECOVERY', message='The complete request is not verified yet. Continuing with an action instead of stopping at app focus.')
                            feedback = ('DECISION_ACTION_REQUIRED. Reject the previous success claim. '
                                        'The full user goal is: ' + (goal or '') + '. '
                                        'Navigation evidence: ' + navigation.context() +
                                        ' Perform the remaining work; focusing/opening an app alone is insufficient. '
                                        'Use browser_open/browser_new_tab for missing navigation. For other work inspect controls and take an action.')
                            continue
                        if navigation.active and not navigation.simple and not completion_challenge:
                            completion_challenge = True
                            feedback = ('Verify the WHOLE original goal against the fresh observation, not just its opening step. '
                                        'Original goal: ' + goal + '. State concrete evidence of the requested result; '
                                        'otherwise return CONTINUE with the next action. Last result: ' + feedback)
                            continue
                        emit('THOUGHT', message=decision.summary)
                        emit('STATUS', status=decision.status, message=decision.summary)
                        return
                    emit('THOUGHT', message=decision.summary)
                    emit('PLAN', steps=decision.plan)
                    action = decision.action
                emit('ACTION', step=step + 1, action=action.model_dump())
                try:
                    result = controller.execute(action)
                    completion_challenge = False
                    executed = not any(marker in str(result) for marker in ('outcome uncertain', 'No form action was executed'))
                    if executed and action.kind not in ('ensure_app', 'open_app', 'focus', 'focus_window', 'app_list', 'wait', 'browser_snapshot', 'browser_tabs',
                                           'browser_open', 'browser_navigate', 'browser_new_tab', 'browser_switch_tab', 'mouse_move'):
                        substantive_actions += 1
                    if navigation.active and action.kind in ('ensure_app', 'open_app', 'browser_open', 'browser_navigate', 'browser_new_tab', 'browser_snapshot'):
                        navigation.record(result)
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
                    elif autonomous and action.kind in ('click', 'ui_click', 'hotkey', 'type_text', 'open_app', 'ensure_app'):
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
        if brain and hasattr(brain, 'close'):
            try:
                brain.close()
            except Exception:
                pass
        if controller:
            try:
                controller.close()
            except Exception as exc:
                emit('ERROR', message=f'Cleanup: {exc}')
        emit('WORKER_DONE')
