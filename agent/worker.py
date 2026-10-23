"""Isolated execution loop: one action, new observation, bounded recovery, explicit terminal status."""
from __future__ import annotations
from pathlib import Path
import os
import queue
import time
from agent.models import Action


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
    deadline = time.monotonic() + settings.max_runtime
    try:
        from config import enable_dpi_awareness
        enable_dpi_awareness()
        if os.name == 'nt':
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin():
                raise PermissionError('Run GhostOS without Administrator rights. UAC stays under manual control.')
        from agent.safety import WorkerSafety
        from agent.vision import Vision
        from agent.ui_tree import UITree, uia_context
        from agent.controller import Controller
        from agent.brain import Brain
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
        brain = Brain(settings) if recipe is None and fast is None else None
        feedback, browser_state, recovery_count = '', '', 0
        last_frame_time = 0.0
        with uia_context():
            for step in range(settings.max_steps):
                safety.check()
                if time.monotonic() > deadline:
                    emit('STATUS', status='MAX_RUNTIME_EXCEEDED')
                    return
                frame = vision.capture()
                controller.frame = frame
                emit('FRAME', image=frame.base64(grid=not settings.game_mode), step=step)
                ui = tree.snapshot() if not settings.game_mode else []
                if recipe is not None:
                    if step >= len(recipe.steps):
                        emit('STATUS', status='RECIPE_COMPLETED', message='All recipe steps executed; goal is not independently verified.')
                        return
                    action = recipe.steps[step]
                elif fast:
                    if step > 0:
                        emit('STATUS', status='COMMAND_COMPLETED')
                        return
                    action = fast
                else:
                    decision = brain.next(goal, frame, ui, browser_state, feedback, emit)
                    emit('THOUGHT', message=decision.summary)  # Public assessment, not chain of thought.
                    emit('PLAN', steps=decision.plan)
                    if decision.status != 'CONTINUE':
                        emit('STATUS', status=decision.status, message=decision.summary)
                        return
                    action = decision.action
                emit('ACTION', step=step + 1, action=action.model_dump())
                try:
                    result = controller.execute(action)
                    if action.kind.startswith('browser_'):
                        browser_state = str(result)
                    feedback = str(result)[:7000]
                    emit('RESULT', message=feedback)
                    if settings.game_mode:
                        # Fast capture/template polling continues between expensive vision model calls.
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
                                feedback += '\nTemplate observations: ' + str(detections)
                                feedback = feedback[-7000:]
                    elif action.kind in ('click', 'ui_click', 'hotkey', 'type_text', 'browser_navigate', 'open_app'):
                        # Observe for two seconds before declaring a visual stall; never replay action.
                        changed = False
                        until = min(deadline, time.monotonic() + 2)
                        while time.monotonic() < until:
                            if stop.wait(0.2):
                                safety.check()
                            if vision.changed(frame, vision.capture()):
                                changed = True
                                break
                        if not changed:
                            recovery_count += 1
                            if recovery_count >= 3:
                                emit('STATUS', status='GOAL_IMPOSSIBLE', message='Three visual stalls; stopping without replaying actions.')
                                return
                            # Focus is a separate permission-checked action. Let the planner decide Tab/Enter.
                            emit('RECOVERY', message='Screen did not change. Re-focus, refresh targets and prefer Tab navigation; do not replay side effects.')
                            controller.execute(Action(kind='focus'))
                            feedback += '\nNo visual change after 2 seconds. Targets may be stale. Recalculate or use Tab; verify before Enter.'
                        else:
                            recovery_count = 0
                except PermissionError:
                    raise
                except InterruptedError:
                    raise
                except Exception as exc:
                    feedback = f'{type(exc).__name__}: {exc}'
                    emit('ERROR', message=feedback)
                    if recipe is not None or fast is not None:
                        raise
                    recovery_count += 1
                    if recovery_count >= 3:
                        emit('STATUS', status='GOAL_IMPOSSIBLE', message=feedback)
                        return
                if brain:
                    brain.context.add(action.model_dump(), feedback)
                if recipe is not None and step + 1 >= len(recipe.steps):
                    emit('STATUS', status='RECIPE_COMPLETED', message='All recipe steps executed; goal is not independently verified.')
                    return
                if fast is not None:
                    emit('STATUS', status='COMMAND_COMPLETED')
                    return
            emit('STATUS', status='MAX_STEPS_EXCEEDED')
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
