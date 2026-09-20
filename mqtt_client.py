import json
import ssl

import paho.mqtt.client as mqtt

from config import (
    BAMBU_ACCESS_TOKEN,
    BAMBU_DEVICE_ID,
    BAMBU_USER_ID,
    MQTT_HOST,
    MQTT_PORT,
)


class BambuMQTTClient:
    def __init__(self, state_manager):
        self.state_manager = state_manager

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bambu-timelapse-{BAMBU_DEVICE_ID[-6:]}",
            clean_session=True,
        )

        self.client.username_pw_set(
            username=f"u_{BAMBU_USER_ID}",
            password=BAMBU_ACCESS_TOKEN,
        )

        self.client.tls_set(
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        print(f"[mqtt] connected: {reason_code}", flush=True)

        topic = f"device/{BAMBU_DEVICE_ID}/report"
        client.subscribe(topic, qos=0)

        print(f"[mqtt] subscribed: {topic}", flush=True)

    def on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        print(f"[mqtt] disconnected: {reason_code}", flush=True)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        print_data = payload.get("print")

        if not isinstance(print_data, dict):
            return

        self.state_manager.update(print_data)

    def run(self):
        print(f"[mqtt] connecting to {MQTT_HOST}:{MQTT_PORT}", flush=True)

        self.client.connect(
            MQTT_HOST,
            MQTT_PORT,
            keepalive=60,
        )

        self.client.loop_forever(
            retry_first_connection=True,
        )

    def stop(self):
        self.client.disconnect()
