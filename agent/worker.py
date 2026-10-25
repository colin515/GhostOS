"""Execute explicit navigation first, then observe, act and verify the full goal."""
from __future__ import annotations
from pathlib import Path
import json
import re
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
        from agent.task_progress import TaskProgress, playback_action
        progress = TaskProgress.parse(goal, settings.game_mode)
        navigation = Navigation.parse(goal, settings.game_mode)
        recovery = Recovery(goal, settings.game_mode)
        if navigation.app == 'chrome' and hasattr(settings, 'browser_channel'):
            from dataclasses import replace
            settings = replace(settings, browser_channel='chrome')
        safety = WorkerSafety(settings, stop, events, answers)
        vision = Vision(settings.screenshot_width, settings.data_dir / 'templates')
        tree = UITree()
        controller = Controller(settings, safety, tree, vision)
        controller.original_goal = goal or ''
        controller.browser_explicit = navigation.app in ('chrome', 'edge', 'firefox')
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
            pending_phase, media_attempted = True, False

            def complete_phase(summary):
                progress.complete(summary)
                emit('TASK_PROGRESS', message=f'Completed step {progress.index}/{len(progress.steps)}: {summary}',
                     completed=progress.index, total=len(progress.steps))
                if progress.done:
                    message = summary if len(progress.steps) == 1 else f'Completed all {len(progress.steps)} requested steps. {summary}'
                    emit('STATUS', status='GOAL_SATISFIED', message=message)
                    return True
                return False

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
                    if pending_phase:
                        navigation = Navigation.parse(progress.current, settings.game_mode)
                        recovery = Recovery(progress.current, settings.game_mode)
                        substantive_actions, completion_challenge, media_attempted = 0, False, False
                        pending_phase = False
                        emit('PLAN', message=f'Step {progress.index + 1}/{len(progress.steps)}: {progress.current}')
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
                                if complete_phase(navigation.success_message()):
                                    return
                                pending_phase = True
                        except (InterruptedError, PermissionError):
                            raise
                        except Exception as exc:
                            navigation.record(None)
                            feedback = f'Navigation attempt {navigation.attempts}: {type(exc).__name__}: {exc}' + navigation.context()
                            emit('RECOVERY', message=feedback[:1200])
                        continue
                    profile = None
                    if settings.game_mode and getattr(settings,'game_profile',''):
                        from agent.game_profiles import load_profile, applies_to
                        profile = load_profile(settings.data_dir/'game_profiles'/settings.game_profile)
                        if not applies_to(profile,progress.original,progress.current):
                            profile = None
                    if profile:
                        from agent.game_profiles import run_profile
                        outcome = run_profile(controller,profile,emit,settings.max_steps,deadline)
                        if outcome == 'GOAL_SATISFIED':
                            if complete_phase('The configured game victory marker is visible.'):
                                return
                            pending_phase = True
                            continue
                        emit('STATUS',status=outcome)
                        return
                    media = playback_action(progress.current)
                    if media and not media_attempted:
                        media_attempted = True
                        emit('ACTION', step=step + 1, action=media.model_dump())
                        try:
                            result = controller.execute(media)
                            feedback = browser_state = str(result)
                            emit('RESULT', message=feedback[:4000])
                            data = json.loads(result)
                            if data.get('verified') and data.get('operation') == media.args['operation']:
                                if complete_phase(f"Media {media.args['operation']} verified."):
                                    return
                                pending_phase = True
                            else:
                                feedback += '\nDECISION_ACTION_REQUIRED. Opening the page did not complete playback. Inspect the player and take the remaining action.'
                        except (InterruptedError, PermissionError):
                            raise
                        except Exception as exc:
                            feedback = 'DECISION_ACTION_REQUIRED. Playback is not verified: ' + str(exc)[:700]
                            emit('RECOVERY', message='Could not verify playback directly; inspecting the player controls instead.')
                        continue
                frame = vision.capture()
                controller.frame = frame
                emit('FRAME', image=frame.base64(grid=not settings.game_mode), step=step)
                try:
                    ui = tree.snapshot() if not settings.game_mode else []
                except Exception as exc:
                    ui = []
                    emit('WARNING', message=f'Accessibility provider unavailable; using vision and keyboard navigation: {exc}')
                if autonomous and getattr(controller.web, 'page', None) and not controller.web.native_fallback:
                    try:
                        browser_state = controller.web.snapshot()
                    except Exception:
                        pass  # A browser tab may have closed; use the fresh desktop frame.
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
                        decision = brain.next(progress.prompt(), frame, ui, browser_state, feedback + navigation.context(), emit)
                        inference_errors = 0
                    except (InterruptedError, PermissionError):
                        raise
                    except Exception as exc:
                        inference_errors += 1
                        from agent.model_protocol import ModelReplyError
                        invalid = isinstance(exc, (ModelReplyError, ValueError))
                        message = ('Ollama responded, but its action was incomplete. Requesting a corrected action.' if invalid else
                                   f'Could not reach or run the local model: {str(exc)[:500]}')
                        emit('ERROR', message=message, attempt=inference_errors)
                        feedback = ('DECISION_ACTION_REQUIRED. Return one compact schema-valid decision with one executable action. '
                                    + str(exc)[:650] + recovery.context())
                        if stop.wait(min(30, 2 ** min(inference_errors, 5))):
                            safety.check()
                        continue
                    if decision.status == 'GOAL_IMPOSSIBLE':
                        emit('MODEL_VERDICT_REJECTED', verdict=decision.status, message=decision.summary)
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
                        if settings.game_mode and re.search(r'\b(?:finish|complete|beat|win)\b',progress.current,re.I):
                            try:
                                fresh = vision.capture()
                                pinned = getattr(getattr(controller,'game',None),'target',None)
                                game_won = (not pinned or fresh.window == pinned) and brain.verify_game_win(progress.current,fresh)
                            except Exception:
                                game_won = False
                            if not game_won:
                                emit('RECOVERY',message='No visible game-completion evidence was verified. Continuing instead of stopping after input or app focus.')
                                feedback = 'DECISION_ACTION_REQUIRED. The game/level is not visibly won. Continue playing; do not claim success from input being sent.'
                                continue
                            substantive_actions = max(1,substantive_actions)
                        media_goal = playback_action(progress.current)
                        if media_goal:
                            try:
                                from agent.models import Action
                                evidence = controller.execute(Action(kind='browser_media', args={'operation': 'state'}))
                                data = json.loads(evidence)
                                state = data.get('media') or {}
                                desired_paused = media_goal.args['operation'] == 'pause'
                                media_verified = (data.get('verified') and state.get('paused') is desired_paused
                                                  and (desired_paused or not state.get('ended', False)))
                            except (InterruptedError, PermissionError):
                                raise
                            except Exception:
                                media_verified = False
                            if not media_verified:
                                feedback = ('DECISION_ACTION_REQUIRED. The player has not verified the requested playback state. '
                                            'Opening the page or clicking without observing playback is insufficient. '
                                            'Inspect the player, buffering, consent or login controls and continue.')
                                emit('RECOVERY', message='Playback is not verified yet. Continuing with the player controls.')
                                continue
                            substantive_actions = max(1, substantive_actions)
                        if navigation.active and not navigation.verified:
                            try:
                                navigation.record(controller.navigation_evidence(navigation))
                            except (InterruptedError, PermissionError):
                                raise
                            except Exception:
                                pass
                        # The model cannot replace requested operations with "Chrome is focused".
                        missing_navigation = navigation.active and not navigation.verified
                        unfinished_work = ((navigation.active and not navigation.simple) or progress.requires_work) and not substantive_actions
                        if missing_navigation or unfinished_work:
                            emit('RECOVERY', message='The complete request is not verified yet. Continuing with an action instead of stopping at app focus.')
                            feedback = ('DECISION_ACTION_REQUIRED. Reject the previous success claim. '
                                        'The full user goal and pending step are: ' + progress.prompt() + '. '
                                        'Navigation evidence: ' + navigation.context() +
                                        ' Perform the remaining work; focusing/opening an app alone is insufficient. '
                                        'Use browser_open/browser_new_tab for missing navigation. For other work inspect controls and take an action.')
                            continue
                        if ((navigation.active and not navigation.simple) or progress.requires_work) and not completion_challenge:
                            completion_challenge = True
                            feedback = ('Verify the WHOLE original goal against the fresh observation, not just its opening step. '
                                        'Original goal and pending step: ' + progress.prompt() + '. State concrete evidence of the requested result; '
                                        'otherwise return CONTINUE with the next action. Last result: ' + feedback)
                            continue
                        emit('THOUGHT', message=decision.summary)
                        if complete_phase(decision.summary):
                            return
                        pending_phase = True
                        continue
                    emit('THOUGHT', message=decision.summary)
                    emit('PLAN', steps=decision.plan)
                    action = decision.action
                emit('ACTION', step=step + 1, action=action.model_dump())
                try:
                    result = controller.execute(action)
                    completion_challenge = False
                    executed = not any(marker in str(result) for marker in ('outcome uncertain', 'No form action was executed'))
                    try:
                        observed_result = json.loads(result)
                        if isinstance(observed_result, dict) and observed_result.get('verified') is False:
                            executed = False
                    except (ValueError, TypeError):
                        pass
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
