"""Windows-Use SDK planning/observation, with all execution owned by GhostOS."""
from __future__ import annotations
import json
import os
from pydantic import BaseModel, Field
from agent.brain import Brain, Context, SYSTEM, ensure_local_vision, local_model_metadata
from agent.models import Action, Decision, ARG_TYPES


class Finish(BaseModel):
    summary: str = Field(max_length=1500, description='Public result with evidence that the entire goal was fulfilled')


def local_desktop():
    """Use the upstream cached UIA tree; exclude GhostOS and undocumented desktop APIs."""
    from ghostos_vendor.windows_use.agent.desktop.service import Desktop
    from ghostos_vendor.windows_use.agent.desktop.views import DesktopState
    from agent.window_focus import is_agent_window

    class GhostDesktop(Desktop):
        def get_controls_handles(self, optimized=False):
            import win32gui
            handles = set()
            def visit(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and not is_agent_window(hwnd):
                    handles.add(hwnd)
            win32gui.EnumWindows(visit, None)
            return handles

        def get_state(self, as_bytes=False):
            # Virtual desktop internals vary by Windows build. Only public HWND/UIA reads
            # are needed; avoid the upstream virtual-desktop manager entirely here.
            handles = self.get_controls_handles()
            windows, window_handles = self.get_windows(handles)
            active = self.get_active_window(windows)
            if active and is_agent_window(active.handle):
                active = None
            state = self.tree.get_state(active.handle if active else None, list(handles - window_handles))
            self.desktop_state = DesktopState(active_desktop={'name':'Current desktop'},
                all_desktops=[], windows=windows, active_window=active, tree_state=state)
            return self.desktop_state

    return GhostDesktop(use_vision=False, use_annotation=False, use_accessibility=True)


class WindowsUseBrain:
    """One SDK planning step per GhostOS loop; no upstream tools execute directly.

    Tool-capable Ollama models use native function calling. Existing vision models
    without tool support use SDK structured output with the same rich observation.
    The external worker owns retries, unlimited runs, approvals and completion checks.
    """
    fast_command = staticmethod(Brain.fast_command)

    def __init__(self, settings):
        # This module never imports upstream Agent, cloud providers or telemetry.
        from ghostos_vendor.windows_use.providers.ollama import ChatOllama
        from ghostos_vendor.windows_use.tools import Tool
        from ghostos_vendor.windows_use.agent.loop import LoopGuard
        metadata = local_model_metadata(settings.ollama_host, settings.model)
        ensure_local_vision(metadata)
        self.settings, self.context = settings, Context()
        self.tools_supported = 'tools' in (metadata.get('capabilities') or [])
        self.llm = ChatOllama(model=settings.model, host=settings.ollama_host, timeout=90,
                             temperature=0, options={'num_ctx':settings.context_tokens,
                             'num_predict':settings.prediction_tokens}, keep_alive='3m')
        self.desktop = local_desktop() if os.name == 'nt' else None
        self.loop_guard = LoopGuard()
        self.last_action = None
        self.tools = [Tool(name=name, description=f'GhostOS {name}. Arguments are validated; execution requires the configured permissions.', model=model)
                      for name, model in ARG_TYPES.items() if not name.startswith(('game_', 'template_'))]
        self.tools.append(Tool(name='finish', description='Finish only when the whole original goal is verified.', model=Finish))

    def observation(self, frame):
        if self.desktop is None:
            return {'warning': 'Windows-Use UIA is only available on Windows'}
        state = self.desktop.get_state()
        self.loop_guard.record_state(state)
        width, height = frame.image.size
        original_width, original_height = frame.original_size
        nodes = []
        tree = state.tree_state
        for node in list(tree.interactive_nodes or []) + list(tree.scrollable_nodes or []):
            if len(nodes) >= 100:
                break
            x, y = node.center.x, node.center.y
            if not (0 <= x < original_width and 0 <= y < original_height):
                continue
            nodes.append({'name': node.name[:120], 'type': node.control_type,
                          'window': node.window_name[:100],
                          'x': min(width - 1, round(x * width / original_width)),
                          'y': min(height - 1, round(y * height / original_height))})
        return {'engine': 'Windows-Use', 'foreground': state.active_window.name if state.active_window else '',
                'windows': [{'title': w.name[:160], 'handle':w.handle, 'status':w.status.value}
                            for w in state.windows[:25]], 'controls':nodes}

    def next(self, goal, frame, tree, browser_state='', feedback='', emit=None):
        from ghostos_vendor.windows_use.messages import SystemMessage, ImageMessage
        from ghostos_vendor.windows_use.providers.events import LLMEventType
        if self.last_action:
            failed = any(word in feedback.lower() for word in ('error', 'failed', 'uncertain'))
            self.loop_guard.record_action(self.last_action.kind, self.last_action.args, not failed)
            self.last_action = None
        try:
            desktop = self.observation(frame)
        except Exception as exc:
            desktop = {'warning': f'Windows-Use observation failed: {exc}', 'fallback_ui_tree':tree}
            if emit:
                emit('WARNING', message='Windows-Use accessibility provider unavailable; using the current screenshot and fallback UIA.')
        nudge = self.loop_guard.check() or ''
        prompt = json.dumps({'goal':goal, 'history':self.context.text(), 'desktop':desktop,
                             'browser':browser_state[:7000], 'feedback':feedback, 'recovery_hint':nudge,
                             'screenshot_size':frame.image.size}, ensure_ascii=False)
        messages = [SystemMessage(content=SYSTEM + '\nWindows-Use supplies the window inventory and cached accessibility controls. '
                    'Their x/y coordinates are already resized screenshot pixels, as are all mouse tool arguments. '
                    'Use app_list for installed apps and focus_window with a listed handle for background windows. '
                    'Use direct navigation before visual guessing. Tool finish requires full-goal evidence. '
                    'Use short public summaries; never output private reasoning.'),
                    ImageMessage(content=prompt, images=[frame.image], mime_type='image/jpeg')]
        if emit:
            emit('INFERENCE', message='Windows-Use is inspecting windows and choosing an action locally')
        if self.tools_supported:
            tools = [tool for tool in self.tools if tool.name != 'finish' or 'DECISION_ACTION_REQUIRED' not in feedback]
            response = self.llm.invoke(messages, tools=tools)
            if response.type != LLMEventType.TOOL_CALL or not response.tool_call:
                raise ValueError('Windows-Use expected one tool call; the goal remains active')
            call = response.tool_call
            if call.name == 'finish':
                if 'DECISION_ACTION_REQUIRED' in feedback:
                    raise ValueError('Completion is not yet verified; an action is required')
                return Decision(status='GOAL_SATISFIED', summary=Finish.model_validate(call.params).summary)
            action = Action(kind=call.name, args=call.params)
            decision = Decision(status='CONTINUE', summary='Next: ' + action.kind.replace('_', ' '), action=action)
        else:
            response = self.llm.invoke(messages, structured_output=Decision)
            decision = Decision.model_validate_json(response.content)
            if 'DECISION_ACTION_REQUIRED' in feedback and decision.status != 'CONTINUE':
                raise ValueError('Completion is not yet verified; choose an action')
        self.last_action = decision.action
        return decision

    def close(self):
        # Ollama's synchronous SDK client wraps httpx; no browser or user app is closed.
        client = getattr(getattr(self.llm, 'client', None), '_client', None)
        if client:
            client.close()
