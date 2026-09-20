import re
from datetime import datetime

from camera import take_snapshot
from config import TIMELAPSE_DIR
from timelapse import generate_timelapse_async


class PrintStateManager:
    def __init__(self):
        self.state = {}
        self.last_layer = None
        self.current_job_dir = None
        self.current_job_name = None
        self.job_finished = False

    def update(self, print_data: dict) -> None:
        # Bambu Cloud MQTT reports are incremental, so keep a merged state.
        self.state.update(print_data)

        layer = self.state.get("layer_num")
        total = self.state.get("total_layer_num")
        gcode_state = self.state.get("gcode_state")
        percent = self.state.get("mc_percent")

        if layer is not None:
            print(
                "[status] "
                f"state={gcode_state or '?'} "
                f"layer={layer}/{total or '?'} "
                f"progress={percent if percent is not None else '?'}%",
                flush=True,
            )

        self.handle_job_status(gcode_state)
        self.handle_layer_change(layer, total, gcode_state)

    def get_job_name(self) -> str:
        candidates = [
            self.state.get("subtask_name"),
            self.state.get("gcode_file"),
            self.state.get("project_name"),
            self.state.get("task_name"),
        ]

        for value in candidates:
            if value:
                return self.safe_name(value)

        return "unknown"

    @staticmethod
    def safe_name(value) -> str:
        value = str(value).strip()
        value = re.sub(r"[^\w\-.]+", "_", value, flags=re.UNICODE)
        return value[:100] or "unknown"

    def create_job_dir(self, force=False):
        job_name = self.get_job_name()

        if (
            not force
            and self.current_job_dir is not None
            and self.current_job_name == job_name
        ):
            return self.current_job_dir

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_job_name = job_name
        self.current_job_dir = TIMELAPSE_DIR / f"{stamp}_{job_name}"
        self.current_job_dir.mkdir(parents=True, exist_ok=True)
        self.job_finished = False

        print(f"[job] started: {self.current_job_dir}", flush=True)
        return self.current_job_dir

    def handle_job_status(self, gcode_state) -> None:
        if not gcode_state:
            return

        if gcode_state == "RUNNING":
            if self.current_job_dir is None:
                self.create_job_dir()
            return

        if gcode_state == "FINISH":
            if self.current_job_dir is not None and not self.job_finished:
                self.job_finished = True
                finished_dir = self.current_job_dir
                print(f"[job] finished: {finished_dir}", flush=True)
                generate_timelapse_async(finished_dir)
            return

        if gcode_state in ("FAILED", "CANCEL", "CANCELED"):
            if self.current_job_dir is not None:
                print(
                    f"[job] state={gcode_state}; keeping captured images",
                    flush=True,
                )

    def handle_layer_change(self, layer, total, gcode_state) -> None:
        if not isinstance(layer, int):
            return

        if self.last_layer is None:
            self.last_layer = layer
            print(f"[layer] initial: {layer}/{total or '?'}", flush=True)
            return

        if layer == self.last_layer:
            return

        # A lower layer number normally means a new print job started.
        if layer < self.last_layer:
            print(
                f"[layer] reset: {self.last_layer} -> {layer}",
                flush=True,
            )
            self.create_job_dir(force=True)
            self.last_layer = layer
            return

        old_layer = self.last_layer
        self.last_layer = layer

        print(
            f"[layer] changed: {old_layer} -> {layer}/{total or '?'}",
            flush=True,
        )

        if self.current_job_dir is None:
            self.create_job_dir()

        # gcode_state may temporarily be absent because MQTT reports are partial.
        if gcode_state in (None, "RUNNING", "PAUSE"):
            take_snapshot(
                self.current_job_dir,
                layer,
                total,
            )
