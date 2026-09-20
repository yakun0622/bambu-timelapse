# bambu-timelapse

A small Python service that listens to **Bambu Lab Cloud MQTT** printer status updates and captures one image from a **Yi camera running yi-hack** whenever the printer advances to the next layer.

The captured frames are stored per print job and automatically assembled into an MP4 with FFmpeg when the printer reports `FINISH`.

## Features

- Connects to Bambu Cloud MQTT over TLS
- Merges Bambu's incremental MQTT status reports
- Detects `layer_num` changes without duplicate captures
- Calls the Yi camera HTTP snapshot endpoint
- Retries failed snapshots
- Creates a directory for each print job
- Generates `timelapse.mp4` automatically after a successful print
- Keeps credentials in `.env`

## Project structure

```text
bambu-timelapse/
├── .env.example
├── .gitignore
├── camera.py
├── config.py
├── main.py
├── mqtt_client.py
├── requirements.txt
├── state_manager.py
└── timelapse.py
```

## Requirements

- Python 3.10+
- FFmpeg
- A Bambu Lab printer accessible through Cloud MQTT
- A Yi camera with a working HTTP snapshot endpoint, such as yi-hack-v5

On Debian/Ubuntu:

```bash
apt update
apt install -y python3-venv ffmpeg

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
BAMBU_MQTT_HOST=cn.mqtt.bambulab.com
BAMBU_USER_ID=your_uid
BAMBU_ACCESS_TOKEN=your_access_token
BAMBU_DEVICE_ID=your_printer_device_id

YI_IP=192.168.2.194
YI_USER=admin
YI_PASSWORD=your_camera_password

SNAPSHOT_DELAY=0.5
SNAPSHOT_RETRIES=3
TIMELAPSE_FPS=30
TIMELAPSE_DIR=./timelapse
```

For a China-region Bambu account, the MQTT broker is normally:

```text
cn.mqtt.bambulab.com:8883
```

The MQTT username is built as:

```text
u_<BAMBU_USER_ID>
```

The Cloud access token is used as the MQTT password.

## Run

```bash
source venv/bin/activate
python main.py
```

Typical output:

```text
[mqtt] connected: Success
[mqtt] subscribed: device/xxxxxxxxxxxx/report
[status] state=RUNNING layer=10/502 progress=21%
[layer] initial: 10/502
[status] state=RUNNING layer=11/502 progress=21%
[layer] changed: 10 -> 11/502
[camera] saved 11/502: timelapse/20260920_120000_model/layer_0011.jpg
```

## Output

```text
timelapse/
└── 20260920_120000_model/
    ├── layer_0011.jpg
    ├── layer_0012.jpg
    ├── layer_0013.jpg
    └── timelapse.mp4
```

The service intentionally does **not** capture a frame for the first layer it sees after startup. That first layer is only used to initialize state, which avoids a false capture after restarting the service in the middle of a print.

## Yi snapshot endpoint

The camera integration uses:

```text
http://<YI_IP>/cgi-bin/snapshot.sh?res=high&watermark=no
```

with HTTP Basic Auth.

## Security

Do not commit your real `.env` file. It contains Bambu and camera credentials.

If a Bambu LAN access code, Cloud access token, or camera password has been exposed, rotate it.
