"""Bounded UIA snapshot. Invoke controls only from the current snapshot."""
from contextlib import contextmanager
import os

@contextmanager
def uia_context():
    if os.name != 'nt':
        yield
        return
    import uiautomation as auto
    with auto.UIAutomationInitializerInThread():
        yield

class UITree:
    def __init__(self):
        self.controls = {}
        self.window = None

    def snapshot(self):
        if os.name != 'nt':
            return []
        import uiautomation as auto
        self.controls = {}
        self.window = auto.GetForegroundControl()
        from agent.window_focus import is_agent_window
        if self.window and is_agent_window(self.window.NativeWindowHandle):
            self.window = None
        output = []
        if not self.window:
            return output
        # UIA APIs can block in broken providers; worker-level timeout bounds the entire run.
        def visit(control, depth):
            if len(output) >= 120 or depth > 5:
                return
            try:
                rect = control.BoundingRectangle
                if not control.IsOffscreen and rect.width() > 0 and rect.height() > 0:
                    idx = len(output)
                    self.controls[idx] = control
                    output.append(dict(id=idx, name=control.Name[:120], type=control.ControlTypeName,
                                       bounds=[rect.left, rect.top, rect.right, rect.bottom]))
                if depth < 5:
                    for child in control.GetChildren()[:40]:
                        visit(child, depth + 1)
            except Exception:
                return
        visit(self.window, 0)
        return output

    def center(self, element_id):
        control = self.controls.get(element_id)
        if control is None or not control.Exists(0, 0):
            raise ValueError('Stale UIA element; capture a new tree')
        import uiautomation as auto
        if not self.window or self.window.NativeWindowHandle != auto.GetForegroundControl().NativeWindowHandle:
            raise ValueError('Foreground window changed; recapture before clicking')
        rect = control.BoundingRectangle
        return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)

    def focus(self):
        if self.window and self.window.Exists(0, 0):
            self.window.SetActive()
