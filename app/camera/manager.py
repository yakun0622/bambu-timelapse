from app.core.config import settings
from app.storage.database import db

from .providers.rtsp import RtspCameraProvider
from .providers.yi import YiCameraProvider


class CameraManager:
    """Unified camera entry point used by services and APIs."""

    def __init__(self):
        self.provider = None
        self.provider_type = None

    def _active_type(self):
        config = db.get_enabled_camera()
        value = (
            config.get("type")
            if config
            else settings.camera_type
        )
        value = str(value or "yi").strip().lower()
        return value if value in {"yi", "rtsp"} else "yi"

    def initialize(self, force=False):
        camera_type = self._active_type()

        if (
            not force
            and self.provider is not None
            and self.provider_type == camera_type
        ):
            return self.provider

        if self.provider is not None:
            try:
                self.provider.stop()
            except Exception:
                pass

        if camera_type == "rtsp":
            self.provider = RtspCameraProvider()
        else:
            self.provider = YiCameraProvider()

        self.provider_type = camera_type
        return self.provider

    def bind(self, provider):
        if self.provider is not None and self.provider is not provider:
            try:
                self.provider.stop()
            except Exception:
                pass
        self.provider = provider
        self.provider_type = None

    def start(self):
        return self.initialize().start()

    def stop(self):
        if self.provider:
            return self.provider.stop()

    def reload(self):
        provider = self.initialize(force=True)
        return provider.start()

    def snapshot(self, *args, **kwargs):
        return self.initialize().snapshot(*args, **kwargs)

    def status(self):
        return self.initialize().status()

    def get_frame(self):
        return self.initialize().get_frame()

    def get_history_window(self, *args, **kwargs):
        provider = self.initialize()
        method = getattr(provider, "get_history_window", None)
        if not method:
            return []
        return method(*args, **kwargs)

    def capture_history_frame(self, *args, **kwargs):
        provider = self.initialize()
        method = getattr(provider, "capture_history_frame", None)
        if not method:
            return False, 0, "摄像头不支持历史帧抓拍", None
        return method(*args, **kwargs)

    def test(self):
        provider = self.initialize()
        method = getattr(provider, "test", None)
        if not method:
            return {"online": False, "error": "摄像头不支持连接测试"}
        return method()

    @property
    def camera_type(self):
        return self._active_type()

    @property
    def display_name(self):
        status = self.status()
        return status.get("name") or "摄像头"

    @property
    def configured(self):
        status = self.status()
        return bool(status.get("configured"))

    @property
    def rtsp_display_url(self):
        status = self.status()
        return status.get("rtsp_display_url")

    def rtsp_status(self):
        status = self.status()
        return status.get("rtsp") or {}


camera_manager = CameraManager()
