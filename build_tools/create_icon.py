"""Render the repository vector mark into a Windows multi-resolution icon."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtCore import Qt, QRectF
from PIL import Image
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.widgets import draw_ghost


def main():
    app = QApplication.instance() or QApplication([])
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_ghost(painter, QRectF(16, 8, 224, 240))
    painter.end()
    target = ROOT / 'assets' / 'GhostOS.ico'
    target.parent.mkdir(exist_ok=True)
    image = pixmap.toImage().convertToFormat(__import__('PyQt6.QtGui', fromlist=['QImage']).QImage.Format.Format_RGBA8888)
    data = image.bits().asstring(image.sizeInBytes())
    Image.frombytes('RGBA', (256, 256), data).save(target, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    return app is not None


if __name__ == '__main__':
    main()
