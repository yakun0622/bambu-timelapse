from app.core.config import settings


class CameraManager:
    """Entry point for camera providers.

    This first version wraps existing camera implementation. Provider split
    can be introduced without changing capture/vision services.
    """

    def __init__(self):
        self.provider = None

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
            raise RuntimeError("camera provider not initialized")
        return self.provider.snapshot(*args, **kwargs)

    def status(self):
        if not self.provider:
            return {"connected": False}
        return self.provider.status()


camera_manager = CameraManager()
