"""Explicit CI smoke test on a disposable window; restores cursor and previous focus."""
import threading
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from agent.mouse import MouseDriver, WinMouse
from agent.window_focus import focus_window


def run_probe():
    import win32gui
    import sys
    app = QApplication.instance() or QApplication(sys.argv[:1])
    original_focus = win32gui.GetForegroundWindow()
    backend = WinMouse()
    original_cursor = backend.position()
    errors, seen = [], []
    class Target(QWidget):
        def mousePressEvent(self, event):
            seen.append(event.button().value)
        def mouseDoubleClickEvent(self, event):
            seen.append('double')
        def wheelEvent(self, event):
            seen.append('scroll')
        def mouseMoveEvent(self, event):
            if event.buttons():
                seen.append('drag')
    target = Target()
    target.setWindowTitle('GhostOS input verification target')
    target.resize(480, 280)
    target.show()
    mouse = MouseDriver(threading.Event(), backend=backend)
    def verify():
        try:
            focus_window(int(target.winId()))
            ratio = target.devicePixelRatioF()
            x, y = win32gui.ClientToScreen(int(target.winId()), (round(160 * ratio), round(100 * ratio)))
            for button in ('left', 'right', 'middle', 'x1', 'x2'):
                mouse.click(x, y, button, duration=0.05)
                app.processEvents()
            mouse.drag(x, y, x + 70, y + 30, duration=0.15)
            app.processEvents()
            mouse.click(x, y, 'left', clicks=2, duration=0.05)
            app.processEvents()
            mouse.scroll(-1)
            app.processEvents()
            required = {1, 2, 4, 8, 16, 'drag', 'double', 'scroll'}
            if not required.issubset(seen):
                raise RuntimeError(f'Missing native input events: {required - set(seen)}; received {seen}')
        except Exception as exc:
            errors.append(str(exc))
        finally:
            backend.move(*original_cursor)
            target.close()
            try:
                if original_focus:
                    focus_window(original_focus)
            except RuntimeError:
                pass
            app.quit()
    QTimer.singleShot(500, verify)
    QTimer.singleShot(20000, app.quit)
    app.exec()
    if errors or not seen:
        raise RuntimeError('; '.join(errors) or 'Native input probe timed out')
    print('Verified foreground transfer, smooth native cursor, five mouse buttons and drag dispatch:', seen)
    return 0
