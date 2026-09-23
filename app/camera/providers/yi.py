from app.camera.base import CameraProvider
from app.integrations.yi.camera import camera as legacy_camera


class YiCameraProvider(CameraProvider):
    """Compatibility adapter for Yi Hack cameras."""

    def start(self):
        return legacy_camera.start()

    def stop(self):
        return legacy_camera.stop()

    def snapshot(self, *args, **kwargs):
        return legacy_camera.snapshot(*args, **kwargs)

    def status(self):
        return legacy_camera.status()

    def get_frame(self):
        return legacy_camera.get_latest_rtsp_frame()
