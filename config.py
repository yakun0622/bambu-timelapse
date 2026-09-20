import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MQTT_HOST = os.getenv("BAMBU_MQTT_HOST", "cn.mqtt.bambulab.com")
MQTT_PORT = int(os.getenv("BAMBU_MQTT_PORT", "8883"))

BAMBU_USER_ID = os.environ["BAMBU_USER_ID"]
BAMBU_ACCESS_TOKEN = os.environ["BAMBU_ACCESS_TOKEN"]
BAMBU_DEVICE_ID = os.environ["BAMBU_DEVICE_ID"]

YI_IP = os.environ["YI_IP"]
YI_USER = os.environ["YI_USER"]
YI_PASSWORD = os.environ["YI_PASSWORD"]

SNAPSHOT_DELAY = float(os.getenv("SNAPSHOT_DELAY", "0.5"))
SNAPSHOT_RETRIES = int(os.getenv("SNAPSHOT_RETRIES", "3"))
TIMELAPSE_FPS = int(os.getenv("TIMELAPSE_FPS", "30"))

TIMELAPSE_DIR = Path(os.getenv("TIMELAPSE_DIR", "./timelapse"))
TIMELAPSE_DIR.mkdir(parents=True, exist_ok=True)
