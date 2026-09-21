import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = os.getenv("BAMBU_MQTT_HOST", "cn.mqtt.bambulab.com")
    mqtt_port: int = int(os.getenv("BAMBU_MQTT_PORT", "8883"))
    bambu_user_id: str = os.getenv("BAMBU_USER_ID", "")
    bambu_access_token: str = os.getenv("BAMBU_ACCESS_TOKEN", "")
    bambu_device_id: str = os.getenv("BAMBU_DEVICE_ID", "")

    yi_ip: str = os.getenv("YI_IP", "")
    yi_user: str = os.getenv("YI_USER", "admin")
    yi_password: str = os.getenv("YI_PASSWORD", "")
    yi_rtsp_port: int = int(os.getenv("YI_RTSP_PORT", "554"))
    yi_rtsp_path: str = os.getenv("YI_RTSP_PATH", "/ch0_0.h264")
    yi_rtsp_url: str = os.getenv("YI_RTSP_URL", "")
    capture_source: str = os.getenv("CAPTURE_SOURCE", "auto").strip().lower()
    rtsp_capture_timeout: float = float(
        os.getenv("RTSP_CAPTURE_TIMEOUT", "4")
    )
    rtsp_frame_rate: int = max(
        1,
        int(os.getenv("RTSP_FRAME_RATE", "5")),
    )
    rtsp_frame_max_age: float = float(
        os.getenv("RTSP_FRAME_MAX_AGE", "1.0")
    )
    rtsp_history_frames: int = max(
        10,
        int(os.getenv("RTSP_HISTORY_FRAMES", "60")),
    )
    capture_rewind_mode: str = os.getenv(
        "CAPTURE_REWIND_MODE",
        "time",
    ).strip().lower()
    capture_rewind_frames: int = max(
        0,
        int(os.getenv("CAPTURE_REWIND_FRAMES", "5")),
    )
    capture_rewind_ms: int = max(
        0,
        int(os.getenv("CAPTURE_REWIND_MS", "1000")),
    )

    snapshot_delay: float = float(os.getenv("SNAPSHOT_DELAY", "0.5"))
    snapshot_retries: int = int(os.getenv("SNAPSHOT_RETRIES", "3"))
    capture_every_layers: int = max(1, int(os.getenv("CAPTURE_EVERY_LAYERS", "1")))
    auto_capture: bool = os.getenv("AUTO_CAPTURE", "true").lower() in {"1", "true", "yes", "on"}
    auto_generate_video: bool = os.getenv("AUTO_GENERATE_VIDEO", "true").lower() in {"1", "true", "yes", "on"}

    timelapse_fps: int = int(os.getenv("TIMELAPSE_FPS", "30"))
    timelapse_dir: Path = Path(os.getenv("TIMELAPSE_DIR", "./data/timelapse"))
    database_path: Path = Path(os.getenv("DATABASE_PATH", "./data/app.db"))
    web_dist: Path = Path(os.getenv("WEB_DIST", "./web/dist"))


settings = Settings()
settings.timelapse_dir.mkdir(parents=True, exist_ok=True)
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
