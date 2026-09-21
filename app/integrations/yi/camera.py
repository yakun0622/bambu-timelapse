import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import quote

import requests

from app.core.config import settings


class YiCamera:
    def __init__(self):
        self.session = requests.Session()

        self._rtsp_lock = threading.Lock()
        self._rtsp_thread = None
        self._rtsp_process = None
        self._rtsp_running = False

        self._latest_frame = None
        self._latest_frame_at = None
        self._rtsp_history = deque(
            maxlen=settings.rtsp_history_frames
        )
        self._rtsp_connected = False
        self._rtsp_frames = 0
        self._rtsp_reconnects = 0
        self._rtsp_last_error = None

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

        path = settings.yi_rtsp_path.strip() or "/ch0_0.h264"
        if not path.startswith("/"):
            path = "/" + path

        auth = ""
        if settings.yi_user:
            user = quote(settings.yi_user, safe="")
            password = quote(settings.yi_password, safe="")
            auth = f"{user}:{password}@"

        return (
            f"rtsp://{auth}{settings.yi_ip}:"
            f"{settings.yi_rtsp_port}{path}"
        )

    @property
    def rtsp_display_url(self):
        path = settings.yi_rtsp_path.strip() or "/ch0_0.h264"
        if not path.startswith("/"):
            path = "/" + path

        if settings.yi_rtsp_url:
            return "Custom RTSP URL"

        return (
            f"rtsp://{settings.yi_ip}:"
            f"{settings.yi_rtsp_port}{path}"
        )

    def start(self):
        source = settings.capture_source

        if (
            source not in {"auto", "rtsp"}
            or not settings.yi_ip
            or self._rtsp_running
        ):
            return

        self._rtsp_running = True
        self._rtsp_thread = threading.Thread(
            target=self._rtsp_worker,
            name="yi-rtsp-buffer",
            daemon=True,
        )
        self._rtsp_thread.start()

    def stop(self):
        self._rtsp_running = False

        process = self._rtsp_process
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        if self._rtsp_thread:
            self._rtsp_thread.join(timeout=3)

        self._rtsp_thread = None
        self._rtsp_process = None

        with self._rtsp_lock:
            self._rtsp_connected = False

    def _rtsp_worker(self):
        while self._rtsp_running:
            process = None

            try:
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
                    "-i",
                    self.rtsp_url,
                    "-map",
                    "0:v:0",
                    "-an",
                    "-vf",
                    f"fps={settings.rtsp_frame_rate}",
                    "-q:v",
                    "2",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "pipe:1",
                ]

                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                self._rtsp_process = process

                with self._rtsp_lock:
                    self._rtsp_last_error = None

                self._read_mjpeg_stream(process)

                if self._rtsp_running:
                    raise RuntimeError(
                        "RTSP stream ended unexpectedly"
                    )

            except Exception as exc:
                with self._rtsp_lock:
                    self._rtsp_connected = False
                    self._rtsp_last_error = str(exc)
                    self._rtsp_reconnects += 1

            finally:
                self._rtsp_process = None

                if process and process.poll() is None:
                    try:
                        process.terminate()
                    except Exception:
                        pass

            if self._rtsp_running:
                time.sleep(1)

    def _read_mjpeg_stream(self, process):
        buffer = bytearray()
        stdout = process.stdout

        if stdout is None:
            raise RuntimeError(
                "FFmpeg RTSP stdout is unavailable"
            )

        while self._rtsp_running:
            chunk = stdout.read(65536)

            if not chunk:
                break

            buffer.extend(chunk)

            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 4 * 1024 * 1024:
                        buffer.clear()
                    break

                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    if start > 0:
                        del buffer[:start]
                    break

                frame = bytes(buffer[start:end + 2])
                del buffer[:end + 2]

                now = time.monotonic()

                with self._rtsp_lock:
                    self._latest_frame = frame
                    self._latest_frame_at = now
                    self._rtsp_frames += 1
                    self._rtsp_history.append(
                        {
                            "seq": self._rtsp_frames,
                            "at": now,
                            "data": frame,
                        }
                    )
                    self._rtsp_connected = True
                    self._rtsp_last_error = None

    def rtsp_status(self):
        with self._rtsp_lock:
            latest_at = self._latest_frame_at
            age_ms = (
                int(
                    (time.monotonic() - latest_at)
                    * 1000
                )
                if latest_at is not None
                else None
            )

            return {
                "enabled": settings.capture_source
                in {"auto", "rtsp"},
                "connected": self._rtsp_connected,
                "ready": (
                    self._latest_frame is not None
                    and age_ms is not None
                    and age_ms
                    <= int(
                        settings.rtsp_frame_max_age
                        * 1000
                    )
                ),
                "frame_age_ms": age_ms,
                "frames": self._rtsp_frames,
                "history_frames": len(self._rtsp_history),
                "history_capacity": settings.rtsp_history_frames,
                "capture_rewind_mode": settings.capture_rewind_mode,
                "capture_rewind_frames": settings.capture_rewind_frames,
                "capture_rewind_ms": settings.capture_rewind_ms,
                "reconnects": self._rtsp_reconnects,
                "last_error": self._rtsp_last_error,
            }

    def snapshot(
        self,
        target: Path,
        trigger_at=None,
        rewind_mode=None,
        rewind_frames=None,
        rewind_ms=None,
    ):
        source = settings.capture_source

        if source not in {"auto", "rtsp", "http"}:
            source = "auto"

        if source in {"auto", "rtsp"}:
            (
                ok,
                duration_ms,
                error,
                frame_age_ms,
                frame_offset,
                requested_rewind_ms,
                frame_before_trigger_ms,
            ) = self._snapshot_rtsp_buffer(
                target,
                trigger_at=trigger_at,
                rewind_mode=rewind_mode,
                rewind_frames=rewind_frames,
                rewind_ms=rewind_ms,
            )

            if ok:
                return (
                    True,
                    duration_ms,
                    None,
                    "rtsp",
                    frame_age_ms,
                    frame_offset,
                    requested_rewind_ms,
                    frame_before_trigger_ms,
                )

            if source == "rtsp":
                return (
                    False,
                    duration_ms,
                    error,
                    "rtsp",
                    frame_age_ms,
                    frame_offset,
                    requested_rewind_ms,
                    frame_before_trigger_ms,
                )

        ok, duration_ms, error = self._snapshot_http(
            target
        )

        return (
            ok,
            duration_ms,
            error,
            "http",
            None,
            None,
            None,
            None,
        )

    def _snapshot_rtsp_buffer(
        self,
        target: Path,
        trigger_at=None,
        rewind_mode=None,
        rewind_frames=None,
        rewind_ms=None,
    ):
        started = time.monotonic()
        deadline = started + min(
            0.5,
            settings.rtsp_frame_max_age,
        )

        mode = (rewind_mode or settings.capture_rewind_mode).strip().lower()
        if mode not in {"frame", "time"}:
            mode = "time"

        requested_frames = (
            settings.capture_rewind_frames
            if rewind_frames is None
            else max(0, int(rewind_frames))
        )
        requested_rewind_ms = (
            settings.capture_rewind_ms
            if rewind_ms is None
            else max(0, int(rewind_ms))
        )

        while True:
            with self._rtsp_lock:
                history = list(self._rtsp_history)
                latest_at = self._latest_frame_at

            latest_age_ms = (
                int(
                    (time.monotonic() - latest_at)
                    * 1000
                )
                if latest_at is not None
                else None
            )

            if (
                history
                and latest_age_ms is not None
                and latest_age_ms
                <= settings.rtsp_frame_max_age * 1000
            ):
                if trigger_at is None:
                    anchor_index = len(history) - 1
                else:
                    anchor_index = None
                    for index in range(
                        len(history) - 1,
                        -1,
                        -1,
                    ):
                        if history[index]["at"] <= trigger_at:
                            anchor_index = index
                            break

                    if anchor_index is None:
                        anchor_index = 0

                if mode == "frame":
                    selected_index = max(
                        0,
                        anchor_index - requested_frames,
                    )
                    selected = history[selected_index]
                    frame_offset = selected_index - anchor_index
                    effective_rewind_ms = None
                else:
                    if trigger_at is None:
                        target_at = history[anchor_index]["at"]
                    else:
                        target_at = (
                            trigger_at
                            - requested_rewind_ms / 1000.0
                        )

                    selected_index = min(
                        range(len(history)),
                        key=lambda index: abs(
                            history[index]["at"] - target_at
                        ),
                    )
                    selected = history[selected_index]
                    frame_offset = selected_index - anchor_index
                    effective_rewind_ms = requested_rewind_ms

                selected_at = selected["at"]
                frame = selected["data"]

                frame_age_ms = int(
                    (time.monotonic() - selected_at)
                    * 1000
                )

                frame_before_trigger_ms = None
                if trigger_at is not None:
                    frame_before_trigger_ms = int(
                        (trigger_at - selected_at)
                        * 1000
                    )

                tmp = target.with_name(
                    target.stem + ".tmp.jpg"
                )
                tmp.write_bytes(frame)
                tmp.replace(target)

                return (
                    True,
                    int(
                        (time.monotonic() - started)
                        * 1000
                    ),
                    None,
                    frame_age_ms,
                    frame_offset,
                    effective_rewind_ms,
                    frame_before_trigger_ms,
                )

            if time.monotonic() >= deadline:
                break

            time.sleep(0.02)

        status = self.rtsp_status()
        error = status.get("last_error")

        if not error:
            error = "RTSP frame history is not ready"

        return (
            False,
            int(
                (time.monotonic() - started)
                * 1000
            ),
            error,
            status.get("frame_age_ms"),
            None,
            requested_rewind_ms if mode == "time" else None,
            None,
        )

    def get_history_window(
        self,
        trigger_at,
        lookback_ms,
    ):
        start_at = trigger_at - max(0, int(lookback_ms)) / 1000.0

        with self._rtsp_lock:
            return [
                {
                    "seq": item["seq"],
                    "at": item["at"],
                    "data": item["data"],
                }
                for item in self._rtsp_history
                if start_at <= item["at"] <= trigger_at
            ]

    def capture_history_frame(
        self,
        target: Path,
        trigger_at,
        rewind_ms,
    ):
        started = time.monotonic()

        with self._rtsp_lock:
            history = list(self._rtsp_history)
            latest_at = self._latest_frame_at

        latest_age_ms = (
            int((time.monotonic() - latest_at) * 1000)
            if latest_at is not None
            else None
        )

        if (
            not history
            or latest_age_ms is None
            or latest_age_ms
            > settings.rtsp_frame_max_age * 1000
        ):
            return (
                False,
                int((time.monotonic() - started) * 1000),
                "RTSP frame history is not ready",
                None,
            )

        target_at = trigger_at - max(0, int(rewind_ms)) / 1000.0
        selected = min(
            history,
            key=lambda item: abs(item["at"] - target_at),
        )

        tmp = target.with_name(target.stem + ".tmp.jpg")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(selected["data"])
        tmp.replace(target)

        actual_before_trigger_ms = int(
            (trigger_at - selected["at"]) * 1000
        )

        return (
            True,
            int((time.monotonic() - started) * 1000),
            None,
            actual_before_trigger_ms,
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
            int(
                (time.monotonic() - started)
                * 1000
            ),
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
                    (time.monotonic() - started)
                    * 1000
                ),
                "check": "tcp",
                "port": 80,
                "rtsp": self.rtsp_status(),
            }

        except Exception as exc:
            return {
                "online": False,
                "duration_ms": int(
                    (time.monotonic() - started)
                    * 1000
                ),
                "check": "tcp",
                "port": 80,
                "error": str(exc),
                "rtsp": self.rtsp_status(),
            }


camera = YiCamera()
