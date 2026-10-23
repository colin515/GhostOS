"""Primary monitor capture with explicit physical/model coordinate transforms."""
from __future__ import annotations
from dataclasses import dataclass
import base64
import io
from PIL import Image, ImageDraw, ImageGrab

@dataclass
class Frame:
    image: Image.Image
    original_size: tuple[int, int]

    def physical(self, x, y):
        w, h = self.image.size
        if not 0 <= x < w or not 0 <= y < h:
            raise ValueError('Coordinate outside latest screenshot')
        return round(x * self.original_size[0] / w), round(y * self.original_size[1] / h)

    def jpeg(self, grid=False):
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
        return buffer.getvalue()

    def base64(self, grid=False):
        return base64.b64encode(self.jpeg(grid)).decode('ascii')


class Vision:
    def __init__(self, width=1280, templates=None):
        self.width, self.templates = width, templates

    def capture(self):
        image = ImageGrab.grab(all_screens=False).convert('RGB')
        original = image.size
        if image.width > self.width:
            image.thumbnail((self.width, self.width * 3), Image.Resampling.LANCZOS)
        return Frame(image, original)

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
