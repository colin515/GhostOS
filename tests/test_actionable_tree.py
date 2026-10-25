"""Actionable controls must survive large non-interactive UIA trees."""
import sys
from types import SimpleNamespace
from unittest.mock import patch
from agent.ui_tree import UITree


class Rect:
    left, top, right, bottom = 0, 0, 400, 300
    def width(self): return self.right-self.left
    def height(self): return self.bottom-self.top


class Node:
    BoundingRectangle=Rect()
    IsOffscreen=False
    NativeWindowHandle=44
    def __init__(self, name, kind, children=()):
        self.Name, self.ControlTypeName, self.children = name, kind, list(children)
    def GetChildren(self): return self.children


def test_snapshot_prioritises_button_after_140_panes(monkeypatch):
    panes=[Node('pane','PaneControl') for _ in range(140)]
    containers=[Node('group','PaneControl',panes[i:i+35]) for i in range(0,140,35)]
    button=Node('Continue','ButtonControl')
    root=Node('Window','WindowControl',containers+[button])
    tree=UITree()
    monkeypatch.setitem(sys.modules,'uiautomation',
                        SimpleNamespace(GetForegroundControl=lambda:root))
    monkeypatch.setattr('agent.window_focus.is_agent_window',lambda hwnd:False)
    with patch('agent.ui_tree.os.name','nt'):
        snapshot=tree.snapshot()
    assert len(snapshot)==1
    assert snapshot[0]['name']=='Continue'
    assert snapshot[0]['id']==0
    assert tree.controls[0] is button
