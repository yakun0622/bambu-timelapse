import asyncio
import threading
from datetime import datetime, timezone


class EventBus:
    def __init__(self):
        self._loop = None
        self._subscribers = set()
        self._lock = threading.Lock()
        self._recent = []
        self._sequence = 0

    def bind_loop(self, loop):
        self._loop = loop

    def recent(self, limit=50):
        with self._lock:
            return list(self._recent[-limit:])

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._subscribers.discard(queue)

    def emit(self, event_type, message, data=None):
        with self._lock:
            self._sequence += 1
            event = {
                "id": self._sequence,
                "type": event_type,
                "message": message,
                "data": data or {},
                "time": datetime.now(timezone.utc).isoformat(),
            }
            self._recent.append(event)
            self._recent = self._recent[-200:]

        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._broadcast, event)

    def _broadcast(self, event):
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


event_bus = EventBus()
