import time
from pathlib import Path

import requests

from config import (
    SNAPSHOT_DELAY,
    SNAPSHOT_RETRIES,
    YI_IP,
    YI_PASSWORD,
    YI_USER,
)


def snapshot_url() -> str:
    return (
        f"http://{YI_IP}/cgi-bin/"
        "snapshot.sh?res=high&watermark=no"
    )


def take_snapshot(job_dir: Path, layer: int, total=None) -> bool:
    filename = job_dir / f"layer_{layer:04d}.jpg"

    if filename.exists():
        print(f"[camera] skip layer {layer}: file already exists", flush=True)
        return True

    time.sleep(SNAPSHOT_DELAY)

    for attempt in range(1, SNAPSHOT_RETRIES + 1):
        try:
            response = requests.get(
                snapshot_url(),
                auth=(YI_USER, YI_PASSWORD),
                timeout=10,
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            is_jpeg = response.content[:2] == b"\xff\xd8"

            if "image" not in content_type and not is_jpeg:
                raise RuntimeError(
                    f"camera returned non-image response ({content_type})"
                )

            tmp_file = filename.with_suffix(".jpg.tmp")
            tmp_file.write_bytes(response.content)
            tmp_file.replace(filename)

            if total:
                print(
                    f"[camera] saved {layer}/{total}: {filename}",
                    flush=True,
                )
            else:
                print(f"[camera] saved layer {layer}: {filename}", flush=True)

            return True

        except Exception as exc:
            print(
                f"[camera] attempt {attempt}/{SNAPSHOT_RETRIES} failed: {exc}",
                flush=True,
            )
            if attempt < SNAPSHOT_RETRIES:
                time.sleep(1)

    return False
