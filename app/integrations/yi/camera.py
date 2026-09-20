import time
from pathlib import Path

import requests

from app.core.config import settings


class YiCamera:
    def __init__(self):
        self.session = requests.Session()

    @property
    def url(self):
        return f"http://{settings.yi_ip}/cgi-bin/snapshot.sh?res=high&watermark=no"

    def snapshot(self, target: Path):
        started = time.monotonic()
        last_error = None

        for attempt in range(1, settings.snapshot_retries + 1):
            try:
                response = self.session.get(
                    self.url,
                    auth=(settings.yi_user, settings.yi_password),
                    timeout=10,
                )
                response.raise_for_status()
                if response.content[:2] != b"\xff\xd8":
                    raise RuntimeError("camera response is not JPEG")

                tmp = target.with_suffix(".jpg.tmp")
                tmp.write_bytes(response.content)
                tmp.replace(target)
                elapsed = int((time.monotonic() - started) * 1000)
                return True, elapsed, None
            except Exception as exc:
                last_error = str(exc)
                if attempt < settings.snapshot_retries:
                    time.sleep(1)

        return False, int((time.monotonic() - started) * 1000), last_error

    def test(self):
        try:
            started = time.monotonic()
            response = self.session.get(
                self.url,
                auth=(settings.yi_user, settings.yi_password),
                timeout=10,
            )
            ok = response.ok and response.content[:2] == b"\xff\xd8"
            return {
                "online": ok,
                "status_code": response.status_code,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "content_type": response.headers.get("Content-Type"),
            }
        except Exception as exc:
            return {"online": False, "error": str(exc)}


camera = YiCamera()
