"""Explicit CI smoke test on a disposable window; restores cursor and previous focus."""
import threading
import time
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
    errors, seen, positions = [], [], []
    class Target(QWidget):
        def mousePressEvent(self, event):
            seen.append(event.button().value)
            positions.append((event.position().x(),event.position().y()))
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
            until = time.monotonic() + 1
            while not required.issubset(seen) and time.monotonic() < until:
                app.processEvents()
                time.sleep(0.01)
            if not required.issubset(seen):
                raise RuntimeError(f'Missing native input events: {required - set(seen)}; received {seen}')
            # Exercise the same crop/resize/origin pipeline as a model click, not
            # just the low-level mouse driver. The widget records actual hit coordinates.
            import queue
            from types import SimpleNamespace
            from config import Settings
            from agent.controller import Controller
            from agent.vision import Vision
            from agent.ui_tree import UITree
            from agent.models import Action
            from agent.targeting import StaleTargetError
            controller = Controller(Settings(tier=3),SimpleNamespace(stop=threading.Event(),
                authorize=lambda a:None,check=lambda:None,events=queue.Queue()),UITree(),Vision(320))
            try:
                controller.frame = controller.vision.capture()
                sx,sy = controller.frame.model_point(x,y)
                controller.execute(Action(kind='click',args={'x':sx,'y':sy,'duration':.05}))
                app.processEvents()
                if abs(positions[-1][0]-160)>3 or abs(positions[-1][1]-100)>3:
                    raise RuntimeError('Screenshot-coordinate click missed the intended client point: ' + str(positions[-1]))
                before = len(positions)
                target.move(target.x()+43,target.y()+31)
                app.processEvents()
                try:
                    controller.execute(Action(kind='click',args={'x':sx,'y':sy,'duration':.05}))
                except StaleTargetError:
                    pass
                else:
                    raise RuntimeError('A stale coordinate was accepted after the window moved')
                if len(positions) != before:
                    raise RuntimeError('A click was sent despite changed window geometry')
            finally:
                controller.close()
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
