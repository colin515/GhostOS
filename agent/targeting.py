"""Reject stale visual targets before sending input; never guess a nearby button."""
from __future__ import annotations
import os
import math
from PIL import ImageChops, ImageStat


class StaleTargetError(ValueError):
    pass


def verify_live_center(point, current):
    if math.dist(point,current) > 3:
        raise StaleTargetError('The accessible target moved while the cursor was travelling. No click was sent.')


def verify_window(frame, geometry=True):
    if os.name != 'nt' or not frame or not frame.window:
        return
    import win32gui
    if not win32gui.IsWindow(frame.window) or win32gui.GetForegroundWindow() != frame.window:
        raise StaleTargetError('The foreground changed after observation. Capture fresh targets before input.')
    if geometry and frame.window_bounds and tuple(win32gui.GetWindowRect(frame.window)) != frame.window_bounds:
        raise StaleTargetError('The target window moved or resized after observation. Recalculate coordinates.')


def verify_patch(before, after, physical):
    if before.origin != after.origin or before.original_size != after.original_size or before.window != after.window:
        raise StaleTargetError('Capture geometry changed; no visual click was sent')
    x,y = before.model_point(*physical)
    box = (max(0,x-18),max(0,y-18),min(before.image.width,x+19),min(before.image.height,y+19))
    a = before.image.crop(box).convert('RGB')
    b = after.image.resize(before.image.size).crop(box).convert('RGB')
    difference = sum(ImageStat.Stat(ImageChops.difference(a,b)).mean) / 3
    if difference > 24:
        raise StaleTargetError('The intended click region changed during inference. Observe again; do not replay the click.')


def resolve_point(frame, args, tree, vision, game_mode=False):
    if frame is None:
        raise StaleTargetError('Capture a screenshot before coordinate input')
    verify_window(frame,geometry=not bool(args.get('target')))
    if args.get('target'):
        return tree.find(args['target']), 'accessibility-label'
    point = frame.point(args['x'],args['y'],args.get('coordinate_space','screenshot'))
    if not game_mode:
        verify_patch(frame,vision.capture(),point)
    return point,'vision-' + args.get('coordinate_space','screenshot')
