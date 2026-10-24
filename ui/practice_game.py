"""A harmless offline game that proves targeting, key chords, camera input and victory."""
from __future__ import annotations
import queue
import random
import tempfile
import threading
from pathlib import Path
from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QWidget
from config import Settings, user_data_dir

TITLE = 'GhostOS Control Practice'
MARKERS = ['practice-gem.png','practice-keys.png','practice-camera.png','practice-finish.png','practice-victory.png']


class PracticeGame(QWidget):
    def __init__(self):
        super().__init__()
        self.stage,self.collected,self.pressed = 0,0,set()
        self.setWindowTitle(TITLE)
        self.resize(640,420)
        self.setMinimumSize(560,360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.patterns = []
        for seed in range(5):
            rng = random.Random(900 + seed)
            pixels = bytearray()
            cells = [[rng.choice([(255,216,64),(36,45,70),(245,245,255),(35,185,150)]) for _ in range(8)] for _ in range(8)]
            for y in range(64):
                for x in range(64):
                    pixels.extend(cells[y//8][x//8])
            self.patterns.append(QImage(bytes(pixels),64,64,192,QImage.Format.Format_RGB888).copy())

    def marker_rect(self):
        positions = [(100,150),(350,110),(200,240)]
        x,y = positions[min(self.collected,2)] if self.stage == 0 else (100 + self.stage * 70,170)
        return QRect(x,y,64,64)

    def paintEvent(self,event):
        painter = QPainter(self)
        painter.fillRect(self.rect(),QColor('#17191f'))
        painter.setPen(QColor('#f4f4fa'))
        painter.drawText(25,40,'GhostOS · Control Practice')
        instructions = ['Collect three markers by clicking them.','Hold Shift + W together.',
                        'Hold the right mouse button and move the camera.','Click the last marker to finish.',
                        'VICTORY · All control stages completed.']
        painter.drawText(25,80,instructions[self.stage])
        painter.drawText(25,self.height()-25,f'Stage {min(self.stage+1,5)} / 5 · Esc closes this practice game')
        painter.drawImage(self.marker_rect(),self.patterns[self.stage])

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton and self.marker_rect().contains(event.position().toPoint()):
            if self.stage == 0:
                self.collected += 1
                if self.collected == 3:
                    self.stage = 1
            elif self.stage == 3:
                self.stage = 4
            self.update()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        self.pressed.add(event.key())
        if self.stage == 1 and {Qt.Key.Key_Shift.value,Qt.Key.Key_W.value}.issubset(self.pressed):
            self.stage = 2
            self.update()

    def keyReleaseEvent(self,event):
        self.pressed.discard(event.key())

    def mouseMoveEvent(self,event):
        if self.stage == 2 and event.buttons() & Qt.MouseButton.RightButton:
            self.stage = 3
            self.update()

    def prepare_profile(self,root):
        import yaml
        templates,profiles = root/'templates',root/'game_profiles'
        templates.mkdir(parents=True,exist_ok=True)
        profiles.mkdir(parents=True,exist_ok=True)
        stage,collected = self.stage,self.collected
        for index,name in enumerate(MARKERS):
            self.stage,self.collected = index,0
            self.grab(self.marker_rect()).save(str(templates/name),'PNG')
        self.stage,self.collected = stage,collected
        self.update()
        data = {'name':'Control Practice','window_title':TITLE,'success_template':MARKERS[4],
                'rules':[{'template':MARKERS[0],'action':{'kind':'template_click','args':{'name':MARKERS[0]}}},
                         {'template':MARKERS[1],'action':{'kind':'game_action','args':{'keys':['shift','w'],'duration':.15}}},
                         {'template':MARKERS[2],'action':{'kind':'game_action','args':{'buttons':['right'],'dx':40,'duration':.15}}},
                         {'template':MARKERS[3],'action':{'kind':'template_click','args':{'name':MARKERS[3]}}}]}
        path = profiles/'control-practice.yaml'
        if not path.exists():
            path.write_text(yaml.safe_dump(data,sort_keys=False),encoding='utf-8')
        return path


def launch_practice(smoke_test=False):
    import sys
    import win32gui
    from agent.window_focus import focus_window
    from agent.mouse import WinMouse
    from ui.widgets import ghost_icon
    app = QApplication.instance() or QApplication(sys.argv[:1])
    target = PracticeGame()
    target.setWindowIcon(ghost_icon())
    original_focus = win32gui.GetForegroundWindow()
    backend = WinMouse()
    original_cursor = backend.position()
    stop,done,results,events = threading.Event(),threading.Event(),[],queue.Queue()
    temporary = tempfile.TemporaryDirectory(prefix='GhostOS-game-check-') if smoke_test else None
    root = Path(temporary.name) if temporary else user_data_dir()
    target.show()
    def run():
        from agent.game_profiles import load_profile,run_profile
        from agent.controller import Controller
        from agent.vision import Vision
        from agent.ui_tree import UITree
        from agent.safety import WorkerSafety
        controller = None
        try:
            settings = Settings(data_dir=root,game_mode=True,tier=3,game_profile='control-practice.yaml')
            controller = Controller(settings,WorkerSafety(settings,stop,events,queue.Queue()),UITree(),Vision(1024,root/'templates'))
            outcome = run_profile(controller,load_profile(root/'game_profiles/control-practice.yaml'),lambda *a,**kw:None,max_steps=15)
            if outcome != 'GOAL_SATISFIED' or target.stage != 4:
                raise RuntimeError('Practice game did not reach verified victory: ' + outcome)
            results.append('success')
        except Exception as exc:
            import traceback
            from agent.startup import log_startup
            log_startup(traceback.format_exc())
            results.append(f'{type(exc).__name__}: {exc}')
        finally:
            if controller:
                controller.close()
            done.set()
    def ready():
        focus_window(int(target.winId()))
        target.prepare_profile(root)
        if smoke_test:
            threading.Thread(target=run,daemon=True,name='GhostOS-game-probe').start()
    poll = QTimer()
    def check():
        # Drain input diagnostics so the smoke test cannot block on logging.
        while not events.empty():
            events.get_nowait()
        if done.is_set():
            target.close()
            app.quit()
    poll.timeout.connect(check)
    poll.start(50)
    QTimer.singleShot(600,ready)
    if smoke_test:
        QTimer.singleShot(25000,stop.set)
        QTimer.singleShot(30000,app.quit)
    app.exec()
    stop.set()
    if smoke_test:
        done.wait(2)
        backend.move(*original_cursor)
        if original_focus:
            try:
                focus_window(original_focus)
            except RuntimeError:
                pass
        temporary.cleanup()
        if results != ['success']:
            raise RuntimeError('Game control probe failed: ' + '; '.join(results or ['timed out']))
        print('Verified complete practice game: three precise clicks, simultaneous Shift+W, held right mouse + relative camera, final click, observed victory')
    return 0
