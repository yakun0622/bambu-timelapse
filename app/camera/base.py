from abc import ABC, abstractmethod


class CameraProvider(ABC):
    """Common camera provider contract."""

    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @abstractmethod
    def snapshot(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def status(self):
        raise NotImplementedError
