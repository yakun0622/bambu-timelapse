from mqtt_client import BambuMQTTClient
from state_manager import PrintStateManager


def main():
    print("Bambu Timelapse", flush=True)

    state_manager = PrintStateManager()
    mqtt_client = BambuMQTTClient(state_manager)

    try:
        mqtt_client.run()
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
        mqtt_client.stop()


if __name__ == "__main__":
    main()
