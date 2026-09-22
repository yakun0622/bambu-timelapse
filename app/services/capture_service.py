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
                "vision_bed_match_threshold",
                "vision_bed_locator_mode",
                "vision_aruco_id",
                "vision_aruco_dictionary",
                "vision_reference_similarity_threshold",
                "vision_reference_start_layer",
                "vision_reference_max_shift_px",
                "vision_model_roi_x",
                "vision_model_roi_y",
                "vision_model_roi_w",
                "vision_model_roi_h",
                "vision_stable_px",
                "vision_bed_stable_px",
                "vision_stable_frames",
                "vision_align_enabled",
                "vision_align_max_shift_px",
                "vision_roi_x",
                "vision_roi_y",
                "vision_roi_w",
                "vision_roi_h",
                "vision_target_x",
                "vision_target_y",
                "vision_target_w",
                "vision_target_h",
                "vision_bed_roi_x",
                "vision_bed_roi_y",
                "vision_bed_roi_w",
                "vision_bed_roi_h",
                "vision_bed_target_x",
                "vision_bed_target_y",
                "vision_bed_target_w",
                "vision_bed_target_h",
                "vision_template_path",
                "vision_bed_template_path",
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
                    float(runtime.get("vision_match_threshold", "0.78")),
                ),
            ),
            "bed_match_threshold": min(
                1.0,
                max(
                    0.0,
                    float(
                        runtime.get(
                            "vision_bed_match_threshold",
                            "0.78",
                        )
                    ),
                ),
            ),
            "bed_locator_mode": runtime.get(
                "vision_bed_locator_mode",
                "reference",
            ).strip().lower(),
            "aruco_id": max(
                0,
                int(runtime.get("vision_aruco_id", "23")),
            ),
            "aruco_dictionary": runtime.get(
                "vision_aruco_dictionary",
                "DICT_4X4_50",
            ).strip().upper(),
            "reference_similarity_threshold": min(
                1.0,
                max(
                    0.0,
                    float(
                        runtime.get(
                            "vision_reference_similarity_threshold",
                            "0.80",
                        )
                    ),
                ),
            ),
            "reference_start_layer": max(
                2,
                int(
                    runtime.get(
                        "vision_reference_start_layer",
                        "2",
                    )
                ),
            ),
            "reference_max_shift_px": max(
                1,
                int(
                    runtime.get(
                        "vision_reference_max_shift_px",
                        "60",
                    )
                ),
            ),
            "model_roi": {
                "x": max(0, int(runtime.get("vision_model_roi_x", "80"))),
                "y": max(0, int(runtime.get("vision_model_roi_y", "150"))),
                "w": max(1, int(runtime.get("vision_model_roi_w", "1120"))),
                "h": max(1, int(runtime.get("vision_model_roi_h", "520"))),
            },
            "stable_px": max(
                0,
                int(runtime.get("vision_stable_px", "8")),
            ),
            "bed_stable_px": max(
                0,
                int(runtime.get("vision_bed_stable_px", "8")),
            ),
            "stable_frames": max(
                1,
                int(runtime.get("vision_stable_frames", "2")),
            ),
            "align_enabled": runtime.get(
                "vision_align_enabled",
                "true",
            ).lower() in {"1", "true", "yes", "on"},
            "align_max_shift_px": max(
                0,
                int(
                    runtime.get(
                        "vision_align_max_shift_px",
                        "30",
                    )
                ),
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
                "w": max(1, int(runtime.get("vision_target_w", "180"))),
                "h": max(1, int(runtime.get("vision_target_h", "100"))),
            },
            "bed_roi": {
                "x": max(0, int(runtime.get("vision_bed_roi_x", "0"))),
                "y": max(0, int(runtime.get("vision_bed_roi_y", "250"))),
                "w": max(1, int(runtime.get("vision_bed_roi_w", "1280"))),
                "h": max(1, int(runtime.get("vision_bed_roi_h", "470"))),
            },
            "bed_target": {
                "x": max(0, int(runtime.get("vision_bed_target_x", "0"))),
                "y": max(0, int(runtime.get("vision_bed_target_y", "250"))),
                "w": max(1, int(runtime.get("vision_bed_target_w", "1280"))),
                "h": max(1, int(runtime.get("vision_bed_target_h", "470"))),
            },
            "template_path": runtime.get("vision_template_path"),
            "bed_template_path": runtime.get(
                "vision_bed_template_path"
            ),
        }

    def _capture_by_vision(
        self,
        job_id,
        layer,
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

        if config["bed_locator_mode"] == "reference":
            previous = db.get_previous_snapshot(
                job_id,
                layer,
            )
            if (
                layer < config["reference_start_layer"]
                or not previous
                or not previous.get("file_path")
            ):
                result = None
                vision_error = (
                    f"第 {layer} 层尚无可用上一帧参考图"
                )
            else:
                result, vision_error = (
                    vision_selector.select_reference(
                        history=history,
                        trigger_at=triggered_at,
                        reference_path=previous["file_path"],
                        model_roi=config["model_roi"],
                        head_template_path=config["template_path"],
                        head_roi=config["roi"],
                        head_target=config["target"],
                        head_match_threshold=config["match_threshold"],
                        similarity_threshold=config[
                            "reference_similarity_threshold"
                        ],
                        max_shift_px=config[
                            "reference_max_shift_px"
                        ],
                        align_enabled=config["align_enabled"],
                    )
                )
        else:
            result, vision_error = vision_selector.select(
                history=history,
                trigger_at=triggered_at,
                head_template_path=config["template_path"],
                head_roi=config["roi"],
                head_target=config["target"],
                bed_template_path=config["bed_template_path"],
                bed_roi=config["bed_roi"],
                bed_target=config["bed_target"],
                bed_locator_mode=config["bed_locator_mode"],
                aruco_id=config["aruco_id"],
                aruco_dictionary=config["aruco_dictionary"],
                head_match_threshold=config["match_threshold"],
                bed_match_threshold=config["bed_match_threshold"],
                stable_px=config["stable_px"],
                bed_stable_px=config["bed_stable_px"],
                stable_frames=config["stable_frames"],
                align_enabled=config["align_enabled"],
                align_max_shift_px=config["align_max_shift_px"],
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
                "vision_score": result["head_score"],
                "bed_score": result.get("bed_score"),
                "bed_locator_mode": config["bed_locator_mode"],
                "aruco_id": result.get("aruco_id"),
                "similarity_score": result.get("similarity_score"),
                "vision_final_score": result.get("final_score"),
                "vision_stable": True,
                "bed_stable": (
                    result.get("stable")
                    if config["bed_locator_mode"] != "reference"
                    else None
                ),
                "vision_stable_count": result.get("stable_count"),
                "vision_x": result["head_x"],
                "vision_y": result["head_y"],
                "bed_x": result.get("bed_x"),
                "bed_y": result.get("bed_y"),
                "align_dx": result["align_dx"],
                "align_dy": result["align_dy"],
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
            "bed_score": None,
            "bed_locator_mode": config["bed_locator_mode"],
            "aruco_id": (
                config["aruco_id"]
                if config["bed_locator_mode"] == "aruco"
                else None
            ),
            "similarity_score": None,
            "vision_final_score": None,
            "vision_stable": None,
            "bed_stable": None,
            "vision_stable_count": None,
            "vision_x": None,
            "vision_y": None,
            "bed_x": None,
            "bed_y": None,
            "align_dx": None,
            "align_dy": None,
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
                    job_id,
                    layer,
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
                    "bed_score": None,
                    "bed_locator_mode": None,
                    "aruco_id": None,
                    "similarity_score": None,
                    "vision_final_score": None,
                    "vision_stable": None,
                    "bed_stable": None,
                    "vision_stable_count": None,
                    "vision_x": None,
                    "vision_y": None,
                    "bed_x": None,
                    "bed_y": None,
                    "align_dx": None,
                    "align_dy": None,
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
                    bed_score=result["bed_score"],
                    bed_stable=result["bed_stable"],
                    bed_locator_mode=result["bed_locator_mode"],
                    aruco_id=result["aruco_id"],
                    similarity_score=result["similarity_score"],
                    align_dx=result["align_dx"],
                    align_dy=result["align_dy"],
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
                        "bed_score": result["bed_score"],
                        "bed_locator_mode": result["bed_locator_mode"],
                        "aruco_id": result["aruco_id"],
                        "similarity_score": result["similarity_score"],
                        "vision_final_score": result[
                            "vision_final_score"
                        ],
                        "vision_stable": result["vision_stable"],
                        "bed_stable": result["bed_stable"],
                        "vision_stable_count": result[
                            "vision_stable_count"
                        ],
                        "vision_x": result["vision_x"],
                        "vision_y": result["vision_y"],
                        "bed_x": result["bed_x"],
                        "bed_y": result["bed_y"],
                        "align_dx": result["align_dx"],
                        "align_dy": result["align_dy"],
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
                    bed_score=result["bed_score"],
                    bed_stable=result["bed_stable"],
                    align_dx=result["align_dx"],
                    align_dy=result["align_dy"],
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
