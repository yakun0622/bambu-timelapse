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
        self.thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.running = False
        self.queue.put(None)

    def enqueue(
        self,
        job_id: int,
        job_dir: Path,
        layer: int,
        total=None,
    ):
        self.queue.put(
            (
                job_id,
                job_dir,
                layer,
                total,
                time.monotonic(),
            )
        )

    def _worker(self):
        while self.running:
            item = self.queue.get()

            if item is None:
                break

            (
                job_id,
                job_dir,
                layer,
                total,
                triggered_at,
            ) = item

            target = (
                job_dir
                / f"layer_{layer:04d}.jpg"
            )

            if target.exists():
                continue

            event_bus.emit(
                "SNAPSHOT_STARTED",
                f"Capturing layer {layer}",
                {
                    "job_id": job_id,
                    "layer": layer,
                },
            )

            runtime = db.get_app_settings(
                (
                    "capture_rewind_mode",
                    "capture_rewind_frames",
                    "capture_rewind_ms",
                    "debug_capture_enabled",
                    "debug_capture_start_ms",
                    "debug_capture_end_ms",
                    "debug_capture_interval_ms",
                )
            )

            rewind_mode = runtime.get(
                "capture_rewind_mode",
                settings.capture_rewind_mode,
            )
            rewind_frames = int(
                runtime.get(
                    "capture_rewind_frames",
                    settings.capture_rewind_frames,
                )
            )
            rewind_ms = int(
                runtime.get(
                    "capture_rewind_ms",
                    settings.capture_rewind_ms,
                )
            )

            debug_enabled = runtime.get(
                "debug_capture_enabled",
                "false",
            ).lower() in {"1", "true", "yes", "on"}
            debug_start_ms = max(
                0,
                int(runtime.get("debug_capture_start_ms", "3000")),
            )
            debug_end_ms = max(
                0,
                int(runtime.get("debug_capture_end_ms", "0")),
            )
            debug_interval_ms = max(
                50,
                int(runtime.get("debug_capture_interval_ms", "500")),
            )

            (
                ok,
                acquisition_ms,
                error,
                source,
                frame_age_ms,
                frame_offset,
                rewind_ms_applied,
                frame_before_trigger_ms,
            ) = camera.snapshot(
                target,
                trigger_at=triggered_at,
                rewind_mode=rewind_mode,
                rewind_frames=rewind_frames,
                rewind_ms=rewind_ms,
            )

            duration_ms = int(
                (time.monotonic() - triggered_at)
                * 1000
            )

            if ok:
                db.add_snapshot(
                    job_id,
                    layer,
                    target,
                    "SUCCESS",
                    duration_ms=duration_ms,
                    source=source,
                    frame_age_ms=frame_age_ms,
                    frame_offset=frame_offset,
                    rewind_ms=rewind_ms_applied,
                    frame_before_trigger_ms=frame_before_trigger_ms,
                )

                event_bus.emit(
                    "SNAPSHOT_SUCCESS",
                    f"Snapshot saved for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "path": str(target),
                        "duration_ms": duration_ms,
                        "acquisition_ms": acquisition_ms,
                        "frame_age_ms": frame_age_ms,
                        "frame_offset": frame_offset,
                        "rewind_mode": rewind_mode,
                        "rewind_ms": rewind_ms_applied,
                        "frame_before_trigger_ms": frame_before_trigger_ms,
                        "source": source,
                    },
                )

            else:
                db.add_snapshot(
                    job_id,
                    layer,
                    None,
                    "FAILED",
                    duration_ms=duration_ms,
                    error=error,
                    source=source,
                    frame_age_ms=frame_age_ms,
                    frame_offset=frame_offset,
                    rewind_ms=rewind_ms_applied,
                    frame_before_trigger_ms=frame_before_trigger_ms,
                )

                event_bus.emit(
                    "SNAPSHOT_FAILED",
                    f"Snapshot failed for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "duration_ms": duration_ms,
                        "acquisition_ms": acquisition_ms,
                        "frame_age_ms": frame_age_ms,
                        "frame_offset": frame_offset,
                        "rewind_mode": rewind_mode,
                        "rewind_ms": rewind_ms_applied,
                        "frame_before_trigger_ms": frame_before_trigger_ms,
                        "error": error,
                        "source": source,
                    },
                )

            if debug_enabled:
                debug_dir = (
                    Path(job_dir)
                    / "debug"
                    / f"layer_{layer:04d}"
                )
                debug_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                high = max(debug_start_ms, debug_end_ms)
                low = min(debug_start_ms, debug_end_ms)
                offsets = list(
                    range(
                        high,
                        low - 1,
                        -debug_interval_ms,
                    )
                )

                if not offsets or offsets[-1] != low:
                    offsets.append(low)

                saved = 0

                for debug_rewind_ms in offsets:
                    debug_target = (
                        debug_dir
                        / f"rewind_{debug_rewind_ms:05d}ms.jpg"
                    )

                    (
                        debug_ok,
                        _debug_duration_ms,
                        _debug_error,
                        actual_before_trigger_ms,
                    ) = camera.capture_history_frame(
                        debug_target,
                        triggered_at,
                        debug_rewind_ms,
                    )

                    if not debug_ok:
                        continue

                    db.add_debug_snapshot(
                        job_id,
                        layer,
                        debug_rewind_ms,
                        actual_before_trigger_ms,
                        debug_target,
                    )
                    saved += 1

                event_bus.emit(
                    "DEBUG_CAPTURE_SET",
                    f"Debug frames saved for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "frames": saved,
                        "start_ms": high,
                        "end_ms": low,
                        "interval_ms": debug_interval_ms,
                    },
                )


capture_service = CaptureService()
