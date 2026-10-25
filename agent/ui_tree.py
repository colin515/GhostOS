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
        # The first 120 raw nodes are often window chrome, panes and labels;
        # previously this exhausted the budget before the actual buttons
        # (especially inside Chrome's deep document accessibility tree).
        # Keep bounded traversal but assign stable IDs ONLY to actionable items.
        kinds = {'ButtonControl', 'HyperlinkControl', 'CheckBoxControl',
                 'RadioButtonControl', 'TabItemControl', 'MenuItemControl',
                 'ListItemControl', 'EditControl', 'ComboBoxControl',
                 'SplitButtonControl', 'SpinnerControl', 'TreeItemControl'}
        visited = 0
        def visit(control, depth):
            nonlocal visited
            if len(output) >= 120 or depth > 12 or visited >= 700:
                return
            visited += 1
            try:
                kind = control.ControlTypeName
                rect = control.BoundingRectangle
                if (kind in kinds and not control.IsOffscreen
                        and rect.width() >= 3 and rect.height() >= 3):
                    idx = len(output)
                    name = str(control.Name or '')[:120]
                    self.controls[idx] = control
                    self.identities[idx] = (control.Name, kind)
                    output.append(dict(id=idx, name=name, type=kind,
                                       bounds=[rect.left, rect.top, rect.right, rect.bottom]))
                if depth < 12:
                    for child in control.GetChildren()[:80]:
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


    @staticmethod
    def _same_control(a, b):
        """Match UIA wrappers by runtime identity, not Python object identity."""
        try:
            ida = a.GetRuntimeId()
            idb = b.GetRuntimeId()
            if ida and idb:
                return tuple(ida) == tuple(idb)
        except (AttributeError, RuntimeError, ValueError):
            pass
        try:
            ar, br = a.BoundingRectangle, b.BoundingRectangle
            return (a.ControlTypeName == b.ControlTypeName and
                    a.Name == b.Name and
                    (ar.left, ar.top, ar.right, ar.bottom) ==
                    (br.left, br.top, br.right, br.bottom))
        except Exception:
            return False

    def _hit_matches(self, control, x, y):
        """Check the UIA element under a *physical* point is the target/descendant."""
        import uiautomation as auto
        hit = auto.ControlFromPoint(int(x), int(y))
        visited = set()
        for _ in range(14):
            if not hit:
                return False
            if self._same_control(hit, control):
                return True
            try:
                runtime_id = tuple(hit.GetRuntimeId())
            except Exception:
                runtime_id = id(hit)
            if runtime_id in visited:
                return False
            visited.add(runtime_id)
            try:
                hit = hit.GetParentControl()
            except Exception:
                return False
        return False

    def click_point(self, element_id):
        """Find a physically hittable point on the *requested* live UIA control.

        The bounding-box centre is only a candidate: labels, overlays, clipped
        controls, DPI mistakes and neighboring elements can redirect its click.
        Test the actual hit control before any OS input, and never click a
        different control just because it is nearby.
        """
        from agent.targeting import StaleTargetError
        control = self.controls.get(element_id)
        cx, cy = self.center(element_id)  # validates current window and identity
        if getattr(control, 'IsOffscreen', False):
            raise StaleTargetError('UIA target is offscreen; scroll into view and recapture')
        if getattr(control, 'IsEnabled', True) is False:
            raise StaleTargetError('UIA target is disabled; no click sent')
        rect = control.BoundingRectangle
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if right - left < 3 or bottom - top < 3:
            raise StaleTargetError('UIA target has no usable clickable area')
        # Sample interior points. Use fixed fractions to avoid a child icon or an
        # overlapping menu, and keep all positions strictly inside the bounds.
        candidates = [(cx, cy)]
        for fx, fy in ((0.35, 0.5), (0.65, 0.5), (0.5, 0.35),
                       (0.5, 0.65), (0.25, 0.25), (0.75, 0.75)):
            p = (int(left + (right - left) * fx),
                 int(top + (bottom - top) * fy))
            if p not in candidates:
                candidates.append(p)
        for x, y in candidates:
            try:
                if self._hit_matches(control, x, y):
                    return x, y
            except Exception as exc:
                raise StaleTargetError('Could not hit-test the intended UIA control; '
                                       'capture a fresh screenshot instead') from exc
        raise StaleTargetError('Requested control is not physically clickable at its '
                               'visible bounds (covered, clipped or inaccurate DPI). '
                               'No mouse click was sent; refresh the UI tree.')

    def find_id(self, label):
        """Resolve an exact *unique* actionable name to the current UIA ID."""
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
        return matches[0]

    def find_click_point(self, label):
        return self.click_point(self.find_id(label))

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
        """Compatibility centre lookup; mouse clicks use find_click_point."""
        return self.center(self.find_id(label))

    def focus(self):
        if self.window and self.window.Exists(0, 0):
            self.window.SetActive()
