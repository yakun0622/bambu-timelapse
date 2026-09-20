import socket
import subprocess
import time
from pathlib import Path

import requests

from app.core.config import settings


class YiCamera:
    def __init__(self):
        self.session = requests.Session()

    @property
    def url(self):
        return (
            f"http://{settings.yi_ip}/cgi-bin/"
            "snapshot.sh?res=high&watermark=no"
        )

    @property
    def rtsp_url(self):
        if settings.yi_rtsp_url:
            return settings.yi_rtsp_url

        return f"rtsp://{settings.yi_ip}/ch0_0.h264"

    def snapshot(self, target: Path):
        source = settings.capture_source

        if source not in {"auto", "rtsp", "http"}:
            source = "auto"

        if source in {"auto", "rtsp"}:
            ok, duration_ms, error = self._snapshot_rtsp(target)

            if ok:
                return True, duration_ms, None, "rtsp"

            if source == "rtsp":
                return False, duration_ms, error, "rtsp"

        ok, duration_ms, error = self._snapshot_http(target)
        return ok, duration_ms, error, "http"

    def _snapshot_rtsp(self, target: Path):
        started = time.monotonic()
        tmp = target.with_name(target.stem + ".tmp.jpg")

        try:
            tmp.unlink(missing_ok=True)

            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                "tcp",
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
                "-analyzeduration",
                "0",
                "-probesize",
                "64",
                "-i",
                self.rtsp_url,
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-f",
                "image2",
                "-y",
                str(tmp),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.rtsp_capture_timeout,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "ffmpeg RTSP frame capture failed"
                )

            if not tmp.is_file():
                raise RuntimeError(
                    "ffmpeg did not create a frame"
                )

            if tmp.read_bytes()[:2] != b"\xff\xd8":
                raise RuntimeError(
                    "RTSP frame is not JPEG"
                )

            tmp.replace(target)

            return (
                True,
                int((time.monotonic() - started) * 1000),
                None,
            )

        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)
            return (
                False,
                int((time.monotonic() - started) * 1000),
                "RTSP capture timed out",
            )
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return (
                False,
                int((time.monotonic() - started) * 1000),
                str(exc),
            )

    def _snapshot_http(self, target: Path):
        started = time.monotonic()
        last_error = None

        for attempt in range(
            1,
            settings.snapshot_retries + 1,
        ):
            try:
                response = self.session.get(
                    self.url,
                    auth=(
                        settings.yi_user,
                        settings.yi_password,
                    ),
                    timeout=10,
                )
                response.raise_for_status()

                if response.content[:2] != b"\xff\xd8":
                    raise RuntimeError(
                        "camera response is not JPEG"
                    )

                tmp = target.with_name(
                    target.stem + ".tmp.jpg"
                )
                tmp.write_bytes(response.content)
                tmp.replace(target)

                return (
                    True,
                    int(
                        (time.monotonic() - started)
                        * 1000
                    ),
                    None,
                )

            except Exception as exc:
                last_error = str(exc)

                if attempt < settings.snapshot_retries:
                    time.sleep(1)

        return (
            False,
            int((time.monotonic() - started) * 1000),
            last_error,
        )

    def test(self):
        """Lightweight LAN reachability check."""
        started = time.monotonic()

        try:
            with socket.create_connection(
                (settings.yi_ip, 80),
                timeout=2,
            ):
                pass

            return {
                "online": True,
                "duration_ms": int(
                    (time.monotonic() - started) * 1000
                ),
                "check": "tcp",
                "port": 80,
            }

        except Exception as exc:
            return {
                "online": False,
                "duration_ms": int(
                    (time.monotonic() - started) * 1000
                ),
                "check": "tcp",
                "port": 80,
                "error": str(exc),
            }


camera = YiCamera()
