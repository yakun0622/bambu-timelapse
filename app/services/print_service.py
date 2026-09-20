import re
from datetime import datetime
from pathlib import Path

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

    def update(self, print_data: dict):
        self.state.update(print_data)

        gcode_state = self.state.get("gcode_state")
        layer = self.state.get("layer_num")
        total = self.state.get("total_layer_num")
        progress = self.state.get("mc_percent")

        event_bus.emit(
            "PRINT_PROGRESS",
            f"{gcode_state or '?'} layer {layer or '?'}/{total or '?'}",
            self.status(),
        )

        if gcode_state == "RUNNING" and self.current_job_id is None and isinstance(layer, int):
            self._start_job(layer, total, progress)

        if self.current_job_id is not None:
            db.update_job(
                self.current_job_id,
                current_layer=layer,
                total_layers=total,
                progress=progress,
                status="PAUSED" if gcode_state == "PAUSE" else "PRINTING",
            )

        self._handle_layer(layer, total, gcode_state)

        if (
            self.current_job_id is not None
            and gcode_state in self.TERMINAL_STATES
            and gcode_state != self.last_gcode_state
        ):
            self._finish_job(gcode_state)

        self.last_gcode_state = gcode_state

    def _start_job(self, layer, total, progress):
        name = self._job_name()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = settings.timelapse_dir / f"{stamp}_{name}"
        job_dir.mkdir(parents=True, exist_ok=True)

        self.current_job_id = db.create_job(name, layer, total, progress, job_dir)
        self.current_job_dir = job_dir
        self.last_layer = layer

        event_bus.emit(
            "PRINT_STARTED",
            f"Print started: {name}",
            {"job_id": self.current_job_id, "layer": layer, "total": total},
        )

    def _handle_layer(self, layer, total, gcode_state):
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

        if (
            settings.auto_capture
            and self.current_job_id is not None
            and gcode_state in {None, "RUNNING"}
            and layer % settings.capture_every_layers == 0
        ):
            capture_service.enqueue(self.current_job_id, self.current_job_dir, layer, total)

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
        event_bus.emit("PRINT_FINISHED", f"Print ended: {status}", {"job_id": job_id, "status": status})

        if status == "FINISHED":
            timelapse_service.generate_async(job_id, job_dir)

        self.current_job_id = None
        self.current_job_dir = None
        self.last_layer = None

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
