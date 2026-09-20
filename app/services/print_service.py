import re
from datetime import datetime

from app.core.config import settings
from app.core.events import event_bus
from app.services.capture_service import capture_service
from app.services.timelapse_service import timelapse_service
from app.storage.database import db


class PrintService:
    TERMINAL_STATES = {"FINISH", "FAILED", "CANCEL", "CANCELED"}

    def __init__(self):
        self.state = {}
        self.current_job_id = None
        self.current_job_dir = None
        self.last_layer = None
        self.last_gcode_state = None
        self.last_progress_signature = None
        self.completing_announced = False

    def update(self, print_data: dict):
        # Cloud MQTT is delta-based. Keep one merged state in memory.
        self.state.update(print_data)

        gcode_state = self.state.get("gcode_state")
        layer = self.state.get("layer_num")
        total = self.state.get("total_layer_num")
        progress = self.state.get("mc_percent")

        # Do not flood WebSocket/Event UI for fan/temp/wifi delta packets when
        # print progress itself has not changed.
        signature = (gcode_state, layer, total, progress)
        if signature != self.last_progress_signature:
            self.last_progress_signature = signature
            event_bus.emit(
                "PRINT_PROGRESS",
                f"{gcode_state or '?'} layer "
                f"{layer if layer is not None else '?'}/"
                f"{total if total is not None else '?'}",
                self.status(),
            )

        previous_layer = self.last_layer

        # Preferred start condition: explicit RUNNING from the printer.
        if (
            gcode_state == "RUNNING"
            and self.current_job_id is None
            and isinstance(layer, int)
            and (progress is None or progress < 100)
        ):
            self._start_job(layer, total, progress, inferred=False)

        # Fallback for a service started mid-print before a full status arrives:
        # an increasing layer number is itself strong evidence that printing is
        # active. Start from the previous observed layer so this transition can
        # still produce a frame.
        elif (
            self.current_job_id is None
            and isinstance(previous_layer, int)
            and isinstance(layer, int)
            and layer > previous_layer
            and (progress is None or progress < 100)
            and gcode_state not in self.TERMINAL_STATES
        ):
            self._start_job(previous_layer, total, progress, inferred=True)

        if self.current_job_id is not None:
            status = "PAUSED" if gcode_state == "PAUSE" else "PRINTING"
            db.update_job(
                self.current_job_id,
                current_layer=layer,
                total_layers=total,
                progress=progress,
                status=status,
            )

        if (
            self.current_job_id is not None
            and isinstance(progress, (int, float))
            and progress >= 100
            and not self.completing_announced
        ):
            self.completing_announced = True
            event_bus.emit(
                "PRINT_COMPLETING",
                "Print reached 100%; waiting for FINISH state",
                {"job_id": self.current_job_id, "progress": progress},
            )

        self._handle_layer(layer, total, gcode_state, progress)

        if (
            self.current_job_id is not None
            and gcode_state in self.TERMINAL_STATES
            and gcode_state != self.last_gcode_state
        ):
            self._finish_job(gcode_state)

        self.last_gcode_state = gcode_state

    def _start_job(self, layer, total, progress, inferred=False):
        name = self._job_name()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = settings.timelapse_dir / f"{stamp}_{name}"
        job_dir.mkdir(parents=True, exist_ok=True)

        self.current_job_id = db.create_job(name, layer, total, progress, job_dir)
        self.current_job_dir = job_dir
        self.last_layer = layer
        self.completing_announced = False

        event_bus.emit(
            "PRINT_STARTED",
            f"Print started: {name}" + (" (inferred from layer change)" if inferred else ""),
            {
                "job_id": self.current_job_id,
                "layer": layer,
                "total": total,
                "progress": progress,
                "inferred": inferred,
            },
        )

    def _handle_layer(self, layer, total, gcode_state, progress):
        if not isinstance(layer, int):
            return

        if self.last_layer is None:
            self.last_layer = layer
            return

        if layer < self.last_layer:
            self.last_layer = layer
            return

        if layer == self.last_layer:
            return

        previous = self.last_layer
        self.last_layer = layer

        event_bus.emit(
            "LAYER_CHANGED",
            f"Layer changed {previous} -> {layer}",
            {"job_id": self.current_job_id, "layer": layer, "total": total},
        )

        should_capture = (
            settings.auto_capture
            and self.current_job_id is not None
            and gcode_state in {None, "RUNNING"}
            and (progress is None or progress < 100)
            and layer % settings.capture_every_layers == 0
        )

        if should_capture:
            capture_service.enqueue(
                self.current_job_id,
                self.current_job_dir,
                layer,
                total,
            )

    def _finish_job(self, printer_state):
        job_id = self.current_job_id
        job_dir = self.current_job_dir

        status = {
            "FINISH": "FINISHED",
            "FAILED": "FAILED",
            "CANCEL": "CANCELED",
            "CANCELED": "CANCELED",
        }.get(printer_state, printer_state)

        db.finish_job(job_id, status)
        event_bus.emit(
            "PRINT_FINISHED",
            f"Print ended: {status}",
            {"job_id": job_id, "status": status},
        )

        if status == "FINISHED":
            timelapse_service.generate_async(job_id, job_dir)

        self.current_job_id = None
        self.current_job_dir = None
        self.last_layer = None
        self.completing_announced = False

    def _job_name(self):
        for key in ("subtask_name", "gcode_file", "project_name", "task_name"):
            value = self.state.get(key)
            if value:
                value = re.sub(r"[^\w\-.]+", "_", str(value).strip(), flags=re.UNICODE)
                return value[:100] or "unknown"
        return "unknown"

    def status(self):
        return {
            "state": self.state.get("gcode_state"),
            "layer": self.state.get("layer_num"),
            "total_layers": self.state.get("total_layer_num"),
            "progress": self.state.get("mc_percent"),
            "job_id": self.current_job_id,
            "job_name": self._job_name() if self.current_job_id else None,
        }


print_service = PrintService()
