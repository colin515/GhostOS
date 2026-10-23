"""Bounded event journal; screenshots replace rather than accumulate."""
from collections import deque
from datetime import datetime, timezone
import threading

class EventBus:
    def __init__(self, limit=500):
        self._lock = threading.Lock()
        self._events = deque(maxlen=limit)
        self._sequence = 0
        self.frame = None

    def publish(self, kind, **data):
        with self._lock:
            self._sequence += 1
            event = dict(id=self._sequence, time=datetime.now(timezone.utc).isoformat(), kind=kind, **data)
            if kind == 'FRAME':
                self.frame = event
            else:
                self._events.append(event)
            return event

    def after(self, cursor=0):
        with self._lock:
            return [dict(e) for e in self._events if e['id'] > cursor]

    def latest_frame(self):
        with self._lock:
            return dict(self.frame) if self.frame else None
