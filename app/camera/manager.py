from app.core.config import settings

from .providers.rtsp import RtspCameraProvider
from .providers.yi import YiCameraProvider


class CameraManager:
    """Unified camera entry point."""

    def __init__(self):
        self.provider = None

    def initialize(self):
        camera_type = settings.camera_type

        if camera_type == "rtsp":
            self.bind(RtspCameraProvider())
        else:
            self.bind(YiCameraProvider())

    def bind(self, provider):
        self.provider = provider

    def start(self):
        if self.provider:
            return self.provider.start()

    def stop(self):
        if self.provider:
            return self.provider.stop()

    def snapshot(self, *args, **kwargs):
        if not self.provider:
            self.initialize()
        return self.provider.snapshot(*args, **kwargs)

    def status(self):
        if not self.provider:
            self.initialize()
        return self.provider.status()

    def get_frame(self):
        if not self.provider:
            self.initialize()
        return self.provider.get_frame()


camera_manager = CameraManager()
