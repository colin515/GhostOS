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
        self.identities = {}

    def snapshot(self):
        if os.name != 'nt':
            return []
        import uiautomation as auto
        self.controls = {}
        self.window = auto.GetForegroundControl()
        self.identities = {}
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
                    self.identities[idx] = (control.Name,control.ControlTypeName)
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
        if element_id in self.identities and self.identities[element_id] != (control.Name,control.ControlTypeName):
            raise ValueError('UIA target identity changed; capture a new tree')
        import uiautomation as auto
        if not self.window or self.window.NativeWindowHandle != auto.GetForegroundControl().NativeWindowHandle:
            raise ValueError('Foreground window changed; recapture before clicking')
        rect = control.BoundingRectangle
        return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)

    def nearest_click_target(self, x, y):
        """Return a nearby actionable UIA control's exact physical centre.

        Vision may land just below small controls. Snap only when one live,
        reasonably sized actionable control is unambiguous; never snap to
        parent panes or guess at inaccessible game/canvas content.
        """
        if not self.window:
            return None
        import uiautomation as auto
        try:
            if self.window.NativeWindowHandle != auto.GetForegroundControl().NativeWindowHandle:
                return None
        except Exception:
            return None
        actionable = {'ButtonControl', 'HyperlinkControl', 'CheckBoxControl',
                      'RadioButtonControl', 'TabItemControl', 'MenuItemControl',
                      'ListItemControl', 'EditControl', 'ComboBoxControl'}
        hits = []
        for idx, control in self.controls.items():
            try:
                if control.ControlTypeName not in actionable or not control.Exists(0, 0):
                    continue
                rect = control.BoundingRectangle
                width, height = rect.width(), rect.height()
                if width < 6 or height < 6 or width > 700 or height > 180:
                    continue
                dx = max(rect.left - x, 0, x - rect.right)
                dy = max(rect.top - y, 0, y - rect.bottom)
                outside = (dx * dx + dy * dy) ** 0.5
                tolerance = max(12, min(40, height * 0.8))
                if outside > tolerance:
                    continue
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
                score = outside + 0.08 * ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
                hits.append((score, idx, cx, cy))
            except Exception:
                continue
        hits.sort()
        if not hits or (len(hits) > 1 and hits[1][0] - hits[0][0] < 7):
            return None  # Ambiguous: preserving the model's point is safer.
        _, idx, cx, cy = hits[0]
        return idx, cx, cy

    def find(self, label):
        """Only exact, unique actionable labels can replace a visual coordinate."""
        normalize = lambda text: ' '.join(str(text).casefold().split())
        wanted = normalize(label)
        matches = []
        kinds = {'ButtonControl','HyperlinkControl','CheckBoxControl','RadioButtonControl',
                 'TabItemControl','MenuItemControl','ListItemControl','EditControl','ComboBoxControl'}
        for idx, control in self.controls.items():
            try:
                if control.ControlTypeName in kinds and normalize(control.Name) == wanted:
                    matches.append(idx)
            except Exception:
                continue
        if len(matches) != 1:
            raise ValueError('Target label is missing or ambiguous; use an exact current UIA ID')
        return self.center(matches[0])

    def focus(self):
        if self.window and self.window.Exists(0, 0):
            self.window.SetActive()
