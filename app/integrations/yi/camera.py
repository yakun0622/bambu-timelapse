import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from app.core.config import settings
from app.storage.database import db


class CameraSource:
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
        self._rtsp_stale = False
        self._rtsp_reconnecting = False
        self._rtsp_frames = 0
        self._rtsp_reconnects = 0
        self._rtsp_last_error = None

    def _active_config(self):
        value = db.get_enabled_camera()
        if value:
            return value

        return {
            "name": (
                "小蚁摄像头"
                if settings.camera_type == "yi"
                else settings.camera_name
            ),
            "type": settings.camera_type,
            "rtsp_url": (
                settings.camera_rtsp_url
                or settings.yi_rtsp_url
                or None
            ),
            "username": settings.yi_user,
            "password": settings.yi_password,
            "enabled": 1,
        }

    @property
    def camera_type(self):
        value = str(
            self._active_config().get("type")
            or settings.camera_type
            or "yi"
        ).strip().lower()
        if value not in {"yi", "rtsp"}:
            value = "yi"
        return value

    @property
    def display_name(self):
        value = self._active_config().get("name")
        if value:
            return str(value)
        if self.camera_type == "yi":
            return "小蚁摄像头"
        return settings.camera_name

    @property
    def configured(self):
        config = self._active_config()
        if self.camera_type == "rtsp":
            return bool(
                config.get("rtsp_url")
                or settings.camera_rtsp_url
                or settings.yi_rtsp_url
            )
        return bool(settings.yi_ip)

    @property
    def url(self):
        if self.camera_type != "yi":
            return None

        return (
            f"http://{settings.yi_ip}/cgi-bin/"
            "snapshot.sh?res=high&watermark=no"
        )

    @property
    def rtsp_url(self):
        config = self._active_config()
        configured_url = (
            config.get("rtsp_url")
            or settings.camera_rtsp_url
            or settings.yi_rtsp_url
        )

        if configured_url:
            parsed = urlparse(configured_url)
            username = config.get("username")
            password = config.get("password")
            if (
                parsed.scheme
                and parsed.hostname
                and username
                and parsed.username is None
            ):
                auth = quote(str(username), safe="")
                if password:
                    auth += ":" + quote(str(password), safe="")
                auth += "@"
                port = f":{parsed.port}" if parsed.port else ""
                path = parsed.path or "/"
                query = f"?{parsed.query}" if parsed.query else ""
                return (
                    f"{parsed.scheme}://{auth}{parsed.hostname}"
                    f"{port}{path}{query}"
                )
            return configured_url

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
        config = self._active_config()
        configured_url = (
            config.get("rtsp_url")
            or settings.camera_rtsp_url
            or settings.yi_rtsp_url
        )
        if configured_url:
            parsed = urlparse(configured_url)
            if parsed.scheme and parsed.hostname:
                port = parsed.port or 554
                path = parsed.path or "/"
                return (
                    f"{parsed.scheme}://{parsed.hostname}:"
                    f"{port}{path}"
                )
            return "Custom RTSP URL"

        path = settings.yi_rtsp_path.strip() or "/ch0_0.h264"
        if not path.startswith("/"):
            path = "/" + path

        return (
            f"rtsp://{settings.yi_ip}:"
            f"{settings.yi_rtsp_port}{path}"
        )

    def start(self):
        source = settings.capture_source

        if (
            source not in {"auto", "rtsp"}
            or not self.configured
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
                    self._rtsp_connected = False
                    self._rtsp_stale = False
                    self._rtsp_reconnecting = True
                    self._rtsp_last_error = None
                    self._rtsp_history.clear()

                watchdog = threading.Thread(
                    target=self._watch_rtsp_process,
                    args=(process, time.monotonic()),
                    name="yi-rtsp-watchdog",
                    daemon=True,
                )
                watchdog.start()

                self._read_mjpeg_stream(process)

                if self._rtsp_running:
                    raise RuntimeError(
                        "RTSP stream ended unexpectedly"
                    )

            except Exception as exc:
                with self._rtsp_lock:
                    self._rtsp_connected = False
                    self._rtsp_reconnecting = True
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
                time.sleep(settings.rtsp_reconnect_delay)

    def _watch_rtsp_process(self, process, started_at):
        while self._rtsp_running and process.poll() is None:
            time.sleep(0.5)

            with self._rtsp_lock:
                if self._rtsp_process is not process:
                    return

                latest_at = self._latest_frame_at

            now = time.monotonic()
            no_frame_since_start = (
                latest_at is None
                or latest_at < started_at
            )

            if no_frame_since_start:
                stale = (
                    now - started_at
                    > settings.rtsp_startup_timeout
                )
                reason = "RTSP startup timed out without frames"
            else:
                stale = (
                    now - latest_at
                    > settings.rtsp_stale_timeout
                )
                reason = "RTSP stream stalled; restarting FFmpeg"

            if not stale:
                continue

            with self._rtsp_lock:
                if self._rtsp_process is not process:
                    return
                self._rtsp_connected = False
                self._rtsp_stale = True
                self._rtsp_reconnecting = True
                self._rtsp_last_error = reason
                self._rtsp_history.clear()

            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            return

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
                    self._rtsp_stale = False
                    self._rtsp_reconnecting = False
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
                "stale": self._rtsp_stale,
                "reconnecting": self._rtsp_reconnecting,
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

            if source == "rtsp" or self.camera_type != "yi":
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
                        break

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

    def get_latest_rtsp_frame(self):
        with self._rtsp_lock:
            if self._latest_frame is None or self._latest_frame_at is None:
                return None

            return {
                "seq": self._rtsp_frames,
                "at": self._latest_frame_at,
                "data": self._latest_frame,
                "age_ms": int(
                    (time.monotonic() - self._latest_frame_at)
                    * 1000
                ),
            }

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

        if self.camera_type != "yi" or not self.url:
            return (
                False,
                0,
                "当前摄像头仅支持 RTSP 抓拍",
            )
        deadline = started + settings.http_snapshot_timeout
        last_error = None

        for attempt in range(
            1,
            settings.snapshot_retries + 1,
        ):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                timeout = max(0.5, min(3.0, remaining))
                response = self.session.get(
                    self.url,
                    auth=(
                        self._active_config().get("username")
                        or settings.yi_user,
                        self._active_config().get("password")
                        or settings.yi_password,
                    ),
                    timeout=(timeout, timeout),
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

                if (
                    attempt < settings.snapshot_retries
                    and time.monotonic() + 0.5 < deadline
                ):
                    time.sleep(0.5)

        return (
            False,
            int(
                (time.monotonic() - started)
                * 1000
            ),
            last_error,
        )

    def reload(self):
        was_running = self._rtsp_running
        self.stop()
        with self._rtsp_lock:
            self._latest_frame = None
            self._latest_frame_at = None
            self._rtsp_history.clear()
            self._rtsp_stale = False
            self._rtsp_reconnecting = False
            self._rtsp_last_error = None
        if was_running or settings.capture_source in {"auto", "rtsp"}:
            self.start()

    def start_rtsp(self):
        return self.start()

    def stop_rtsp(self):
        return self.stop()

    def status(self):
        return {
            "type": self.camera_type,
            "name": self.display_name,
            "configured": self.configured,
            "rtsp_display_url": self.rtsp_display_url,
            "rtsp": self.rtsp_status(),
        }

    def test(self):
        """Lightweight LAN reachability check."""
        started = time.monotonic()

        try:
            if self.camera_type == "rtsp":
                parsed = urlparse(self.rtsp_url)
                host = parsed.hostname
                port = parsed.port or 554

                if not host:
                    raise RuntimeError("RTSP 地址未配置")

                check = "rtsp-tcp"
            else:
                host = settings.yi_ip
                port = 80
                check = "tcp"

            with socket.create_connection(
                (host, port),
                timeout=2,
            ):
                pass

            return {
                "online": True,
                "duration_ms": int(
                    (time.monotonic() - started)
                    * 1000
                ),
                "check": check,
                "port": port,
                "camera_type": self.camera_type,
                "name": self.display_name,
                "rtsp": self.rtsp_status(),
            }

        except Exception as exc:
            return {
                "online": False,
                "duration_ms": int(
                    (time.monotonic() - started)
                    * 1000
                ),
                "check": (
                    "rtsp-tcp"
                    if self.camera_type == "rtsp"
                    else "tcp"
                ),
                "error": str(exc),
                "camera_type": self.camera_type,
                "name": self.display_name,
                "rtsp": self.rtsp_status(),
            }


camera = CameraSource()
