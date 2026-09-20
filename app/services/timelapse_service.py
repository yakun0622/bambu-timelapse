import subprocess
import threading
from pathlib import Path

from app.core.config import settings
from app.core.events import event_bus
from app.storage.database import db


class TimelapseService:
    def generate_async(self, job_id: int, job_dir: Path):
        if not settings.auto_generate_video:
            return
        threading.Thread(
            target=self._generate,
            args=(job_id, job_dir),
            daemon=True,
        ).start()

    def _generate(self, job_id: int, job_dir: Path):
        images = sorted(job_dir.glob("layer_*.jpg"))
        if len(images) < 2:
            event_bus.emit("VIDEO_SKIPPED", "Not enough frames to create video", {"job_id": job_id})
            return

        output = job_dir / "timelapse.mp4"
        event_bus.emit("VIDEO_STARTED", "Generating timelapse video", {"job_id": job_id, "frames": len(images)})

        command = [
            "ffmpeg", "-y",
            "-framerate", str(settings.timelapse_fps),
            "-pattern_type", "glob",
            "-i", str(job_dir / "layer_*.jpg"),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0:
            db.update_job(job_id, video_path=str(output))
            event_bus.emit("VIDEO_FINISHED", "Timelapse video created", {"job_id": job_id, "path": str(output)})
        else:
            event_bus.emit("VIDEO_FAILED", "FFmpeg failed", {"job_id": job_id, "error": result.stderr[-1000:]})


timelapse_service = TimelapseService()
