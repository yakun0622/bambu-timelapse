import queue
import threading
import time
from pathlib import Path

from app.core.config import settings
from app.core.events import event_bus
from app.integrations.yi.camera import camera
from app.storage.database import db


class CaptureService:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.queue.put(None)

    def enqueue(self, job_id: int, job_dir: Path, layer: int, total=None):
        self.queue.put((job_id, job_dir, layer, total))

    def _worker(self):
        while self.running:
            item = self.queue.get()
            if item is None:
                break

            job_id, job_dir, layer, total = item
            time.sleep(settings.snapshot_delay)
            target = job_dir / f"layer_{layer:04d}.jpg"

            if target.exists():
                continue

            event_bus.emit("SNAPSHOT_STARTED", f"Capturing layer {layer}", {"job_id": job_id, "layer": layer})
            ok, duration_ms, error, source = camera.snapshot(target)

            if ok:
                db.add_snapshot(job_id, layer, target, "SUCCESS", duration_ms)
                event_bus.emit(
                    "SNAPSHOT_SUCCESS",
                    f"Snapshot saved for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "path": str(target),
                        "duration_ms": duration_ms,
                        "source": source,
                    },
                )
            else:
                db.add_snapshot(job_id, layer, None, "FAILED", duration_ms, error)
                event_bus.emit(
                    "SNAPSHOT_FAILED",
                    f"Snapshot failed for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "error": error,
                        "source": source,
                    },
                )


capture_service = CaptureService()
