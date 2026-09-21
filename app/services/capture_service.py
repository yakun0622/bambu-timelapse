import queue
import threading
import time
from pathlib import Path

from app.core.config import settings
from app.core.events import event_bus
from app.integrations.yi.camera import camera
from app.services.vision_service import vision_selector
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

    def _runtime_settings(self):
        return db.get_app_settings(
            (
                "capture_rewind_mode",
                "capture_rewind_frames",
                "capture_rewind_ms",
                "debug_capture_enabled",
                "debug_capture_start_ms",
                "debug_capture_end_ms",
                "debug_capture_interval_ms",
                "vision_lookback_ms",
                "vision_match_threshold",
                "vision_stable_px",
                "vision_stable_frames",
                "vision_roi_x",
                "vision_roi_y",
                "vision_roi_w",
                "vision_roi_h",
                "vision_target_x",
                "vision_target_y",
                "vision_target_w",
                "vision_target_h",
                "vision_template_path",
            )
        )

    def _vision_config(self, runtime):
        return {
            "lookback_ms": max(
                500,
                int(runtime.get("vision_lookback_ms", "6000")),
            ),
            "match_threshold": min(
                1.0,
                max(
                    0.0,
                    float(
                        runtime.get(
                            "vision_match_threshold",
                            "0.78",
                        )
                    ),
                ),
            ),
            "stable_px": max(
                0,
                int(runtime.get("vision_stable_px", "8")),
            ),
            "stable_frames": max(
                1,
                int(runtime.get("vision_stable_frames", "2")),
            ),
            "roi": {
                "x": max(0, int(runtime.get("vision_roi_x", "700"))),
                "y": max(0, int(runtime.get("vision_roi_y", "0"))),
                "w": max(1, int(runtime.get("vision_roi_w", "580"))),
                "h": max(1, int(runtime.get("vision_roi_h", "260"))),
            },
            "target": {
                "x": max(0, int(runtime.get("vision_target_x", "760"))),
                "y": max(0, int(runtime.get("vision_target_y", "20"))),
                "w": max(1, int(runtime.get("vision_target_w", "450"))),
                "h": max(1, int(runtime.get("vision_target_h", "180"))),
            },
            "template_path": runtime.get("vision_template_path"),
        }

    def _capture_by_vision(
        self,
        target,
        triggered_at,
        runtime,
        fallback_rewind_ms,
    ):
        started = time.monotonic()
        config = self._vision_config(runtime)

        history = camera.get_history_window(
            triggered_at,
            config["lookback_ms"],
        )

        result, vision_error = vision_selector.select(
            history=history,
            trigger_at=triggered_at,
            template_path=config["template_path"],
            roi=config["roi"],
            target=config["target"],
            match_threshold=config["match_threshold"],
            stable_px=config["stable_px"],
            stable_frames=config["stable_frames"],
        )

        if result:
            tmp = target.with_name(
                target.stem + ".tmp.jpg"
            )
            tmp.write_bytes(result["frame"])
            tmp.replace(target)

            return {
                "ok": True,
                "acquisition_ms": int(
                    (time.monotonic() - started) * 1000
                ),
                "error": None,
                "source": "rtsp",
                "frame_age_ms": int(
                    (time.monotonic() - result["at"]) * 1000
                ),
                "frame_offset": None,
                "rewind_ms": None,
                "frame_before_trigger_ms": result[
                    "before_trigger_ms"
                ],
                "selection_mode": "vision",
                "vision_score": result["match_score"],
                "vision_final_score": result["final_score"],
                "vision_stable": result["stable"],
                "vision_stable_count": result["stable_count"],
                "vision_x": result["x"],
                "vision_y": result["y"],
                "vision_error": None,
            }

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
            rewind_mode="time",
            rewind_ms=fallback_rewind_ms,
        )

        return {
            "ok": ok,
            "acquisition_ms": acquisition_ms,
            "error": error,
            "source": source,
            "frame_age_ms": frame_age_ms,
            "frame_offset": frame_offset,
            "rewind_ms": rewind_ms_applied,
            "frame_before_trigger_ms": frame_before_trigger_ms,
            "selection_mode": "vision-fallback",
            "vision_score": None,
            "vision_final_score": None,
            "vision_stable": None,
            "vision_stable_count": None,
            "vision_x": None,
            "vision_y": None,
            "vision_error": vision_error,
        }

    def _capture_debug_frames(
        self,
        runtime,
        job_id,
        job_dir,
        layer,
        triggered_at,
    ):
        enabled = runtime.get(
            "debug_capture_enabled",
            "false",
        ).lower() in {"1", "true", "yes", "on"}

        if not enabled:
            return

        start_ms = max(
            0,
            int(runtime.get("debug_capture_start_ms", "3000")),
        )
        end_ms = max(
            0,
            int(runtime.get("debug_capture_end_ms", "0")),
        )
        interval_ms = max(
            50,
            int(runtime.get("debug_capture_interval_ms", "500")),
        )

        debug_dir = (
            Path(job_dir)
            / "debug"
            / f"layer_{layer:04d}"
        )
        debug_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        high = max(start_ms, end_ms)
        low = min(start_ms, end_ms)

        offsets = list(
            range(
                high,
                low - 1,
                -interval_ms,
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
                "interval_ms": interval_ms,
            },
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

            runtime = self._runtime_settings()

            rewind_mode = runtime.get(
                "capture_rewind_mode",
                settings.capture_rewind_mode,
            ).strip().lower()

            if rewind_mode not in {"frame", "time", "vision"}:
                rewind_mode = "time"

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

            if rewind_mode == "vision":
                result = self._capture_by_vision(
                    target,
                    triggered_at,
                    runtime,
                    rewind_ms,
                )
            else:
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

                result = {
                    "ok": ok,
                    "acquisition_ms": acquisition_ms,
                    "error": error,
                    "source": source,
                    "frame_age_ms": frame_age_ms,
                    "frame_offset": frame_offset,
                    "rewind_ms": rewind_ms_applied,
                    "frame_before_trigger_ms": frame_before_trigger_ms,
                    "selection_mode": rewind_mode,
                    "vision_score": None,
                    "vision_final_score": None,
                    "vision_stable": None,
                    "vision_stable_count": None,
                    "vision_x": None,
                    "vision_y": None,
                    "vision_error": None,
                }

            duration_ms = int(
                (time.monotonic() - triggered_at)
                * 1000
            )

            if result["ok"]:
                db.add_snapshot(
                    job_id,
                    layer,
                    target,
                    "SUCCESS",
                    duration_ms=duration_ms,
                    source=result["source"],
                    frame_age_ms=result["frame_age_ms"],
                    frame_offset=result["frame_offset"],
                    rewind_ms=result["rewind_ms"],
                    frame_before_trigger_ms=result[
                        "frame_before_trigger_ms"
                    ],
                    selection_mode=result["selection_mode"],
                    vision_score=result["vision_score"],
                    vision_stable=result["vision_stable"],
                )

                event_bus.emit(
                    "SNAPSHOT_SUCCESS",
                    f"Snapshot saved for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "path": str(target),
                        "duration_ms": duration_ms,
                        "acquisition_ms": result["acquisition_ms"],
                        "frame_age_ms": result["frame_age_ms"],
                        "frame_offset": result["frame_offset"],
                        "rewind_mode": rewind_mode,
                        "rewind_ms": result["rewind_ms"],
                        "frame_before_trigger_ms": result[
                            "frame_before_trigger_ms"
                        ],
                        "source": result["source"],
                        "selection_mode": result["selection_mode"],
                        "vision_score": result["vision_score"],
                        "vision_final_score": result[
                            "vision_final_score"
                        ],
                        "vision_stable": result["vision_stable"],
                        "vision_stable_count": result[
                            "vision_stable_count"
                        ],
                        "vision_x": result["vision_x"],
                        "vision_y": result["vision_y"],
                        "vision_error": result["vision_error"],
                    },
                )

            else:
                db.add_snapshot(
                    job_id,
                    layer,
                    None,
                    "FAILED",
                    duration_ms=duration_ms,
                    error=result["error"],
                    source=result["source"],
                    frame_age_ms=result["frame_age_ms"],
                    frame_offset=result["frame_offset"],
                    rewind_ms=result["rewind_ms"],
                    frame_before_trigger_ms=result[
                        "frame_before_trigger_ms"
                    ],
                    selection_mode=result["selection_mode"],
                    vision_score=result["vision_score"],
                    vision_stable=result["vision_stable"],
                )

                event_bus.emit(
                    "SNAPSHOT_FAILED",
                    f"Snapshot failed for layer {layer}",
                    {
                        "job_id": job_id,
                        "layer": layer,
                        "duration_ms": duration_ms,
                        "acquisition_ms": result["acquisition_ms"],
                        "frame_age_ms": result["frame_age_ms"],
                        "frame_offset": result["frame_offset"],
                        "rewind_mode": rewind_mode,
                        "rewind_ms": result["rewind_ms"],
                        "frame_before_trigger_ms": result[
                            "frame_before_trigger_ms"
                        ],
                        "error": result["error"],
                        "source": result["source"],
                        "selection_mode": result["selection_mode"],
                        "vision_error": result["vision_error"],
                    },
                )

            self._capture_debug_frames(
                runtime,
                job_id,
                job_dir,
                layer,
                triggered_at,
            )


capture_service = CaptureService()
