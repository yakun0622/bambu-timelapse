"""Camera abstraction layer.

Providers are intentionally separated from print/timelapse logic so different
camera sources (Yi, RTSP phones, IP cameras) can share the same workflow.
"""

from .manager import camera_manager

__all__ = ["camera_manager"]
