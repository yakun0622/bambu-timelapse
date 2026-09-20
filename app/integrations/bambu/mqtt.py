import json
import ssl
import time

import paho.mqtt.client as mqtt

from app.core.config import settings
from app.core.events import event_bus


class BambuMQTT:
    def __init__(self, on_print_data):
        self.on_print_data = on_print_data
        self.connected = False
        self.sequence_id = 0

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bambu-timelapse-{settings.bambu_device_id[-6:]}",
            clean_session=True,
        )
        self.client.username_pw_set(
            username=f"u_{settings.bambu_user_id}",
            password=settings.bambu_access_token,
        )
        self.client.tls_set(
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self):
        self.client.connect_async(
            settings.mqtt_host,
            settings.mqtt_port,
            keepalive=60,
        )
        self.client.loop_start()
        event_bus.emit(
            "MQTT_CONNECTING",
            f"Connecting to {settings.mqtt_host}:{settings.mqtt_port}",
        )

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def _next_sequence_id(self):
        self.sequence_id += 1
        return str(self.sequence_id)

    def request_full_status(self):
        """Ask the printer for one complete status snapshot after connecting."""
        topic = f"device/{settings.bambu_device_id}/request"
        payload = {
            "pushing": {
                "sequence_id": self._next_sequence_id(),
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            }
        }

        info = self.client.publish(
            topic,
            json.dumps(payload, separators=(",", ":")),
            qos=0,
        )

        event_bus.emit(
            "MQTT_PUSHALL",
            "Requested full printer status",
            {"topic": topic, "mid": info.mid},
        )

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = True
        topic = f"device/{settings.bambu_device_id}/report"
        client.subscribe(topic, qos=0)

        event_bus.emit(
            "MQTT_CONNECTED",
            f"MQTT connected: {reason_code}",
            {"topic": topic},
        )

        # A1/P1 cloud reports are often delta-only. Without a pushall request,
        # a service started halfway through a print may know layer_num but not
        # gcode_state, total_layer_num or mc_percent for a long time.
        time.sleep(0.1)
        self.request_full_status()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.connected = False
        event_bus.emit(
            "MQTT_DISCONNECTED",
            f"MQTT disconnected: {reason_code}",
        )

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        print_data = payload.get("print")
        if isinstance(print_data, dict):
            self.on_print_data(print_data)
