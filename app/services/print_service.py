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
        self.current_job_name = None
        self.current_job_key = None
        self.current_task_id = None
        self.current_subtask_id = None

        self.last_layer = None
        self.last_gcode_state = None
        self.last_progress_signature = None
        self.completing_announced = False
        self.restored_from_db = False

        self._restore_active_job()

    @staticmethod
    def _normalize_bambu_id(value):
        if value is None:
            return None

        value = str(value).strip()

        if not value or value == "0" or value.lower() == "none":
            return None

        return value

    def _task_identity(self):
        task_id = self._normalize_bambu_id(
            self.state.get("task_id")
        )
        subtask_id = self._normalize_bambu_id(
            self.state.get("subtask_id")
        )

        if subtask_id:
            job_key = (
                f"bambu:{settings.bambu_device_id}:"
                f"subtask:{subtask_id}"
            )
        elif task_id:
            job_key = (
                f"bambu:{settings.bambu_device_id}:"
                f"task:{task_id}"
            )
        else:
            job_key = None

        return task_id, subtask_id, job_key

    def _fallback_job_key(self, name, stamp):
        safe_name = name or "unknown"
        return (
            f"local:{settings.bambu_device_id}:"
            f"{safe_name}:{stamp}"
        )

    def _restore_active_job(self):
        active = db.get_latest_active_job()

        if not active:
            return

        db.supersede_other_active_jobs(active["id"])
        self._adopt_job(active, resumed=True)

        event_bus.emit(
            "PRINT_RESUMED",
            f"Restored unfinished print job "
            f"#{active['id']}: {active['name']}",
            {
                "job_id": active["id"],
                "job_key": active.get("job_key"),
                "task_id": active.get("bambu_task_id"),
                "subtask_id": active.get("bambu_subtask_id"),
                "layer": active["current_layer"],
                "total": active["total_layers"],
                "progress": active["progress"],
            },
        )

    def _adopt_job(self, job, resumed=False):
        self.current_job_id = job["id"]
        self.current_job_dir = Path(job["output_dir"])
        self.current_job_dir.mkdir(parents=True, exist_ok=True)

        self.current_job_name = job["name"]
        self.current_job_key = job.get("job_key")
        self.current_task_id = job.get("bambu_task_id")
        self.current_subtask_id = job.get("bambu_subtask_id")

        self.last_layer = job["current_layer"]
        self.completing_announced = False
        self.restored_from_db = resumed

    def _sync_task_identity(self):
        task_id, subtask_id, job_key = self._task_identity()

        if not job_key:
            return

        # No active in-memory job: prefer an unfinished row with the exact
        # Bambu job key before creating anything new.
        if self.current_job_id is None:
            matched = db.get_job_by_key(
                job_key,
                active_only=True,
            )

            if matched:
                db.supersede_other_active_jobs(matched["id"])
                self._adopt_job(matched, resumed=True)

                event_bus.emit(
                    "PRINT_RESUMED",
                    f"Matched Bambu task to job "
                    f"#{matched['id']}: {matched['name']}",
                    {
                        "job_id": matched["id"],
                        "job_key": job_key,
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                    },
                )
            return

        # Existing restored job from an older version may not have IDs yet.
        # Attach the Bambu identity as soon as pushall supplies it.
        if not self.current_job_key:
            matched = db.get_job_by_key(
                job_key,
                active_only=True,
            )

            if (
                matched
                and matched["id"] != self.current_job_id
            ):
                old_job_id = self.current_job_id
                db.supersede_job(old_job_id)
                self._adopt_job(matched, resumed=True)

                event_bus.emit(
                    "PRINT_RESUMED",
                    f"Switched duplicate job #{old_job_id} "
                    f"to Bambu task job #{matched['id']}",
                    {
                        "job_id": matched["id"],
                        "job_key": job_key,
                    },
                )
                return

            db.update_job(
                self.current_job_id,
                bambu_task_id=task_id,
                bambu_subtask_id=subtask_id,
                job_key=job_key,
            )

            self.current_task_id = task_id
            self.current_subtask_id = subtask_id
            self.current_job_key = job_key

            event_bus.emit(
                "PRINT_IDENTIFIED",
                "Attached Bambu task identity to current job",
                {
                    "job_id": self.current_job_id,
                    "job_key": job_key,
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                },
            )
            return

        # Strongest possible new-job signal: Bambu's own task identity changed.
        if self.current_job_key != job_key:
            self._interrupt_current_job(
                "Bambu task/subtask ID changed"
            )

            matched = db.get_job_by_key(
                job_key,
                active_only=True,
            )

            if matched:
                self._adopt_job(matched, resumed=True)

                event_bus.emit(
                    "PRINT_RESUMED",
                    f"Resumed Bambu task job "
                    f"#{matched['id']}: {matched['name']}",
                    {
                        "job_id": matched["id"],
                        "job_key": job_key,
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                    },
                )

    def update(self, print_data: dict):
        # Bambu Cloud reports are deltas.
        self.state.update(print_data)

        gcode_state = self.state.get("gcode_state")
        layer = self.state.get("layer_num")
        total = self.state.get("total_layer_num")
        progress = self.state.get("mc_percent")
        incoming_name = self._job_name()

        # task_id/subtask_id may arrive later than layer_num.
        self._sync_task_identity()

        signature = (
            gcode_state,
            layer,
            total,
            progress,
            self.current_job_key,
        )

        if signature != self.last_progress_signature:
            self.last_progress_signature = signature

            event_bus.emit(
                "PRINT_PROGRESS",
                f"{gcode_state or '?'} layer "
                f"{layer if layer is not None else '?'}/"
                f"{total if total is not None else '?'}",
                self.status(),
            )

        # Fallback detection is only used when Bambu task identity is absent,
        # e.g. local/SD-card prints returning task_id/subtask_id = "0".
        if (
            self.current_job_id is not None
            and gcode_state == "RUNNING"
            and not (self.current_job_key or "").startswith("bambu:")
        ):
            layer_reset = (
                isinstance(layer, int)
                and isinstance(self.last_layer, int)
                and layer < self.last_layer
            )

            known_name_changed = (
                incoming_name != "unknown"
                and self.current_job_name not in (None, "unknown")
                and incoming_name != self.current_job_name
            )

            if layer_reset or known_name_changed:
                self._interrupt_current_job(
                    "New local print detected"
                )

        previous_layer = self.last_layer

        if (
            gcode_state == "RUNNING"
            and self.current_job_id is None
            and isinstance(layer, int)
            and (progress is None or progress < 100)
        ):
            self._start_job(
                layer,
                total,
                progress,
                inferred=False,
            )

        elif (
            self.current_job_id is None
            and isinstance(previous_layer, int)
            and isinstance(layer, int)
            and layer > previous_layer
            and (progress is None or progress < 100)
            and gcode_state not in self.TERMINAL_STATES
        ):
            self._start_job(
                previous_layer,
                total,
                progress,
                inferred=True,
            )

        if self.current_job_id is not None:
            status = (
                "PAUSED"
                if gcode_state == "PAUSE"
                else "PRINTING"
            )

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
                {
                    "job_id": self.current_job_id,
                    "progress": progress,
                },
            )

        self._handle_layer(
            layer,
            total,
            gcode_state,
            progress,
        )

        if (
            self.current_job_id is not None
            and gcode_state in self.TERMINAL_STATES
            and gcode_state != self.last_gcode_state
        ):
            self._finish_job(gcode_state)

        self.last_gcode_state = gcode_state

    def _start_job(
        self,
        layer,
        total,
        progress,
        inferred=False,
    ):
        name = self._job_name()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id, subtask_id, job_key = self._task_identity()

        if not job_key:
            job_key = self._fallback_job_key(
                name,
                stamp,
            )

        # If this exact cloud task already exists as active, resume it rather
        # than inserting a second row.
        if job_key.startswith("bambu:"):
            matched = db.get_job_by_key(
                job_key,
                active_only=True,
            )

            if matched:
                db.supersede_other_active_jobs(matched["id"])
                self._adopt_job(matched, resumed=True)

                event_bus.emit(
                    "PRINT_RESUMED",
                    f"Resumed existing Bambu task job "
                    f"#{matched['id']}",
                    {
                        "job_id": matched["id"],
                        "job_key": job_key,
                    },
                )
                return

        job_dir = (
            settings.timelapse_dir
            / f"{stamp}_{name}"
        )
        job_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.current_job_id = db.create_job(
            name,
            layer,
            total,
            progress,
            job_dir,
            bambu_task_id=task_id,
            bambu_subtask_id=subtask_id,
            job_key=job_key,
        )

        self.current_job_dir = job_dir
        self.current_job_name = name
        self.current_job_key = job_key
        self.current_task_id = task_id
        self.current_subtask_id = subtask_id
        self.last_layer = layer
        self.completing_announced = False
        self.restored_from_db = False

        event_bus.emit(
            "PRINT_STARTED",
            f"Print started: {name}"
            + (
                " (inferred from layer change)"
                if inferred
                else ""
            ),
            {
                "job_id": self.current_job_id,
                "job_key": job_key,
                "task_id": task_id,
                "subtask_id": subtask_id,
                "layer": layer,
                "total": total,
                "progress": progress,
                "inferred": inferred,
            },
        )

    def _interrupt_current_job(self, reason):
        if self.current_job_id is None:
            return

        job_id = self.current_job_id

        db.finish_job(
            job_id,
            "INTERRUPTED",
        )

        event_bus.emit(
            "PRINT_INTERRUPTED",
            reason,
            {
                "job_id": job_id,
                "job_key": self.current_job_key,
            },
        )

        self._clear_current_job()

    def _handle_layer(
        self,
        layer,
        total,
        gcode_state,
        progress,
    ):
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
            {
                "job_id": self.current_job_id,
                "job_key": self.current_job_key,
                "layer": layer,
                "total": total,
            },
        )

        should_capture = (
            settings.auto_capture
            and self.current_job_id is not None
            and gcode_state in {None, "RUNNING"}
            and (progress is None or progress < 100)
            and layer > 1
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
        }.get(
            printer_state,
            printer_state,
        )

        db.finish_job(
            job_id,
            status,
        )

        event_bus.emit(
            "PRINT_FINISHED",
            f"Print ended: {status}",
            {
                "job_id": job_id,
                "job_key": self.current_job_key,
                "status": status,
            },
        )

        if status == "FINISHED":
            timelapse_service.generate_async(
                job_id,
                job_dir,
            )

        self._clear_current_job()

    def _clear_current_job(self):
        self.current_job_id = None
        self.current_job_dir = None
        self.current_job_name = None
        self.current_job_key = None
        self.current_task_id = None
        self.current_subtask_id = None
        self.last_layer = None
        self.completing_announced = False
        self.restored_from_db = False

    def _job_name(self):
        for key in (
            "subtask_name",
            "gcode_file",
            "project_name",
            "task_name",
        ):
            value = self.state.get(key)

            if value:
                value = re.sub(
                    r"[^\w\-.]+",
                    "_",
                    str(value).strip(),
                    flags=re.UNICODE,
                )
                return value[:100] or "unknown"

        return "unknown"

    def status(self):
        task_id, subtask_id, incoming_key = self._task_identity()

        return {
            "state": self.state.get("gcode_state"),
            "layer": self.state.get("layer_num"),
            "total_layers": self.state.get("total_layer_num"),
            "progress": self.state.get("mc_percent"),
            "job_id": self.current_job_id,
            "job_name": self.current_job_name,
            "job_key": self.current_job_key or incoming_key,
            "task_id": self.current_task_id or task_id,
            "subtask_id": self.current_subtask_id or subtask_id,
            "resumed": self.restored_from_db,
        }


print_service = PrintService()
