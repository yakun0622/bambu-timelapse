import subprocess
import threading
from pathlib import Path

from config import TIMELAPSE_FPS


def generate_timelapse(job_dir: Path) -> None:
    images = sorted(job_dir.glob("layer_*.jpg"))

    if len(images) < 2:
        print("[ffmpeg] not enough images, skipping video", flush=True)
        return

    output = job_dir / "timelapse.mp4"
    input_pattern = str(job_dir / "layer_*.jpg")

    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(TIMELAPSE_FPS),
        "-pattern_type",
        "glob",
        "-i",
        input_pattern,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]

    print(f"[ffmpeg] generating from {len(images)} frames", flush=True)

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except Exception as exc:
        print(f"[ffmpeg] error: {exc}", flush=True)
        return

    if result.returncode == 0:
        print(f"[ffmpeg] created: {output}", flush=True)
    else:
        print("[ffmpeg] failed", flush=True)
        print(result.stderr[-3000:], flush=True)


def generate_timelapse_async(job_dir: Path) -> None:
    thread = threading.Thread(
        target=generate_timelapse,
        args=(job_dir,),
        daemon=True,
    )
    thread.start()
