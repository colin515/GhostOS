"""Capture the foreground target with explicit screenshot/virtual-screen transforms."""
from __future__ import annotations
from dataclasses import dataclass, field
import base64
import io
import os
import time
from PIL import Image, ImageDraw, ImageGrab

@dataclass
class Frame:
    image: Image.Image
    original_size: tuple[int, int]
    _jpeg_cache: dict = field(default_factory=dict, repr=False)
    origin: tuple[int, int] = (0, 0)
    window: int | None = None
    window_bounds: tuple[int, int, int, int] | None = None
    captured_at: float = field(default_factory=time.monotonic)
    title: str = ''

    def physical(self, x, y):
        w, h = self.image.size
        if not 0 <= x < w or not 0 <= y < h:
            raise ValueError('Coordinate outside latest screenshot')
        return (self.origin[0] + min(self.original_size[0] - 1, round(x * self.original_size[0] / w)),
                self.origin[1] + min(self.original_size[1] - 1, round(y * self.original_size[1] / h)))

    def model_point(self, x, y):
        x, y = x - self.origin[0], y - self.origin[1]
        if not (0 <= x < self.original_size[0] and 0 <= y < self.original_size[1]):
            raise ValueError('Physical target is outside the captured window')
        return (min(self.image.width - 1, round(x * self.image.width / self.original_size[0])),
                min(self.image.height - 1, round(y * self.image.height / self.original_size[1])))

    def point(self, x, y, coordinate_space='screenshot'):
        if coordinate_space == 'normalized_1000':
            if not (0 <= x <= 1000 and 0 <= y <= 1000):
                raise ValueError('Normalized coordinates must be between 0 and 1000')
            return (self.origin[0]+round(x*(self.original_size[0]-1)/1000),
                    self.origin[1]+round(y*(self.original_size[1]-1)/1000))
        return self.physical(x, y)

    def tree_for_model(self, nodes):
        result = []
        for node in nodes:
            item = dict(node)
            if 'bounds' in item:
                left, top, right, bottom = item['bounds']
                try:
                    item['x'], item['y'] = self.model_point((left + right) // 2, (top + bottom) // 2)
                except ValueError:
                    continue
                item['bounds'] = [round((left - self.origin[0]) * self.image.width / self.original_size[0]),
                                  round((top - self.origin[1]) * self.image.height / self.original_size[1]),
                                  round((right - self.origin[0]) * self.image.width / self.original_size[0]),
                                  round((bottom - self.origin[1]) * self.image.height / self.original_size[1])]
            result.append(item)
        return result

    def annotated(self, x, y, label='Target'):
        copy = self.image.copy()
        draw = ImageDraw.Draw(copy)
        draw.ellipse((x-9,y-9,x+9,y+9),outline='#ffd84d',width=2)
        draw.line((x-15,y,x+15,y),fill='#ffd84d',width=2)
        draw.line((x,y-15,x,y+15),fill='#ffd84d',width=2)
        draw.text((max(0,x+12),max(0,y-20)),label[:80],fill='#ffd84d')
        return Frame(copy,self.original_size,origin=self.origin,window=self.window,window_bounds=self.window_bounds,title=self.title)

    def jpeg(self, grid=False):
        if grid in self._jpeg_cache:
            return self._jpeg_cache[grid]
        image = self.image.copy()
        if grid:
            draw = ImageDraw.Draw(image)
            for x in range(0, image.width, 100):
                draw.line((x, 0, x, image.height), fill='#74819a', width=1)
                draw.text((x + 2, 2), str(x), fill='white')
            for y in range(100, image.height, 100):
                draw.line((0, y, image.width, y), fill='#74819a', width=1)
                draw.text((2, y + 2), str(y), fill='white')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=75)
        self._jpeg_cache[grid] = buffer.getvalue()
        return self._jpeg_cache[grid]

    def base64(self, grid=False):
        return base64.b64encode(self.jpeg(grid)).decode('ascii')


class Vision:
    def __init__(self, width=1280, templates=None):
        self.width, self.templates = width, templates

    def capture(self):
        origin, window, bounds, bbox, title = (0, 0), None, None, None, ''
        if os.name == 'nt':
            import win32gui
            import ctypes
            from agent.window_focus import is_agent_window
            user = ctypes.windll.user32
            left, top, width, height = (user.GetSystemMetrics(i) for i in (76,77,78,79))
            bbox = (left,top,left+width,top+height)
            candidate = win32gui.GetForegroundWindow()
            if candidate and not is_agent_window(candidate) and not win32gui.IsIconic(candidate):
                rect = tuple(win32gui.GetWindowRect(candidate))
                clipped = (max(left,rect[0]),max(top,rect[1]),min(left+width,rect[2]),min(top+height,rect[3]))
                if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
                    window, bounds, bbox = candidate, rect, clipped
                    title = win32gui.GetWindowText(candidate)[:200]
            origin = bbox[:2]
        image = ImageGrab.grab(bbox=bbox,all_screens=os.name == 'nt').convert('RGB')
        original = image.size
        if image.width > self.width:
            image.thumbnail((self.width, self.width * 3), Image.Resampling.LANCZOS)
        return Frame(image, original,origin=origin,window=window,window_bounds=bounds,title=title)

    @staticmethod
    def changed(before, after, threshold=2.0):
        from PIL import ImageChops, ImageStat
        a = before.image.resize((160, 90)).convert('L')
        b = after.image.resize((160, 90)).convert('L')
        return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] >= threshold

    def match(self, frame, name, threshold=0.85):
        import cv2
        import numpy as np
        if not self.templates:
            return None
        path = self.templates / name
        if path.resolve().parent != self.templates.resolve():
            raise ValueError('Invalid template path')
        template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise FileNotFoundError(f'Add a cropped PNG template at {path}')
        template = cv2.resize(template, None, fx=frame.image.width / frame.original_size[0],
                              fy=frame.image.height / frame.original_size[1])
        if template.std() < 1:
            raise ValueError('Template is too uniform to match reliably')
        screen = cv2.cvtColor(np.array(frame.image), cv2.COLOR_RGB2GRAY)
        h, w = template.shape
        if h > screen.shape[0] or w > screen.shape[1]:
            return None
        _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED))
        if score < threshold:
            return None
        return {'x': loc[0] + w // 2, 'y': loc[1] + h // 2, 'score': round(score, 4)}
