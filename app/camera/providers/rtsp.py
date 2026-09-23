from app.camera.base import CameraProvider
from app.integrations.yi.camera import camera as legacy_camera


class RtspCameraProvider(CameraProvider):
    """Generic RTSP provider backed by the existing stable RTSP engine.

    The RTSP worker, history buffer and rewind logic remain shared during the
    migration. This adapter decouples business code from the old Yi module.
    """

    def start(self):
        return legacy_camera.start_rtsp()

    def stop(self):
        return legacy_camera.stop_rtsp()

    def snapshot(self, *args, **kwargs):
        return legacy_camera.snapshot(*args, **kwargs)

    def status(self):
        return legacy_camera.status()

    def get_frame(self):
        return legacy_camera.get_latest_rtsp_frame()

    def get_history_window(self, *args, **kwargs):
        return legacy_camera.get_history_window(*args, **kwargs)

    def capture_history_frame(self, *args, **kwargs):
        return legacy_camera.capture_history_frame(*args, **kwargs)

    def test(self):
        return legacy_camera.test()
