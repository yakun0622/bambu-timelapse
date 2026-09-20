# Bambu Timelapse

A self-hosted 3D-print timelapse service built around **Bambu Lab Cloud MQTT**, **Yi Camera / Yi Hack**, **FastAPI**, **Vue 3**, **SQLite**, and **FFmpeg**.

The service listens to printer status updates from Bambu Cloud MQTT, tracks print jobs, detects layer changes, captures snapshots from a Yi camera, stores job history, and can automatically generate an MP4 timelapse when a print finishes.

> This project is an independent community project and is not affiliated with, endorsed by, or sponsored by Bambu Lab or YI Technology.

## Features

- Bambu Lab Cloud MQTT status monitoring
- Automatic print-job discovery and resume after service restart
- Bambu `task_id` / `subtask_id` based job identity
- Layer-change detection and automatic snapshots
- Yi Hack HTTP snapshot integration
- Automatic timelapse generation with FFmpeg
- SQLite persistence for jobs, snapshots, users, and sessions
- Vue 3 management dashboard
- Real-time WebSocket event stream
- Light and dark themes with system-theme detection
- Login protection with forced password change on first sign-in
- Docker Compose deployment
- Persistent database, snapshots, and generated videos

## Web Interface

The web interface currently provides:

- **Dashboard** — printer status, current task, camera status, latest snapshot, and live events
- **Print Jobs** — job history, captured frames, task identifiers, and video downloads
- **Devices** — printer information and Yi camera connectivity checks
- **Settings** — current Bambu, camera, capture, and video configuration

The current frontend UI is primarily Chinese, while this README is maintained in English.

## Default Login

The first installation creates a default administrator account:

```text
Username: admin
Password: admin
```

On the first successful login, the administrator is required to change the default password before accessing the application.

Authentication uses:

- HttpOnly session cookies
- Persistent SQLite sessions
- PBKDF2-SHA256 password hashing
- Forced first-login password change

The password and session data are stored in the persistent SQLite database, so rebuilding the Docker container does not reset the administrator password.

## Architecture

```text
                    Bambu Lab Cloud
                          │
                          │ MQTT / TLS
                          ▼
                 Bambu MQTT Integration
                          │
                          ▼
                    Print Service
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
               SQLite DB   Capture Queue
                                │
                                ▼
                           Yi Camera
                         HTTP Snapshot
                                │
                                ▼
                         Snapshot Files
                                │
                                ▼
                             FFmpeg
                                │
                                ▼
                         Timelapse MP4

                     FastAPI Backend
                    ┌──────┴──────┐
                    │             │
                    ▼             ▼
                 REST API      WebSocket
                    │             │
                    └──────┬──────┘
                           ▼
                       Vue 3 Web UI
```

## Automatic Print Lifecycle

```text
Bambu Cloud MQTT
        │
        ▼
Receive printer state
        │
        ▼
Identify task/subtask
        │
        ▼
Resume existing job
or create a new job
        │
        ▼
layer N -> N+1
        │
        ▼
Capture snapshot
        │
        ▼
progress -> 100%
        │
        ▼
Wait for FINISH
        │
        ▼
Close print job
        │
        ▼
Generate timelapse.mp4
```

Paused jobs stay in a paused state and continue when printing resumes. Canceled or failed jobs keep their captured frames but do not automatically produce a final timelapse.

## Print Job Identity

For cloud-based prints, the service prefers Bambu-provided identifiers instead of guessing task identity from only file names or layer numbers.

Priority:

```text
subtask_id
   ↓ if unavailable
task_id
   ↓ if unavailable or "0"
local fallback key
```

Stored fields include:

```text
bambu_task_id
bambu_subtask_id
job_key
```

A cloud job key is typically shaped like:

```text
bambu:<device_id>:subtask:<subtask_id>
```

This allows the service to reconnect to the same print after:

- application restart
- Docker container rebuild
- MQTT reconnect
- temporary service interruption

For local or SD-card prints where Bambu reports `task_id=0` and `subtask_id=0`, the service falls back to locally generated identity logic.

## Snapshot Logic

The service does not capture immediately just because it starts while a print is already in progress.

For example, if startup discovers:

```text
current layer = 86
```

no frame is captured immediately.

A frame is captured after a real layer transition such as:

```text
86 -> 87
```

Automatic capture also requires the print to be in an active printing state and not already complete.

## Quick Start with Docker

Clone the repository:

```bash
git clone https://github.com/yakun0622/bambu-timelapse.git
cd bambu-timelapse
```

Create the environment file:

```bash
cp .env.example .env
nano .env
```

Start the application:

```bash
docker compose up -d --build
```

Follow logs:

```bash
docker compose logs -f --tail=200
```

Open the web interface:

```text
http://SERVER_IP:8000
```

## Persistent Storage

Docker Compose maps the database and generated media to the host:

```text
./data/
├── db/
│   └── app.db
└── timelapse/
    └── <print-job>/
        ├── layer_0001.jpg
        ├── layer_0002.jpg
        └── timelapse.mp4
```

The container uses:

```text
./data/db          -> /data/db
./data/timelapse   -> /data/timelapse
```

Rebuilding or replacing the application container therefore does not remove the SQLite database, captured frames, or generated videos.

Do not delete the `data/` directory unless you intentionally want to remove persistent application data.

## Configuration

Example:

```env
BAMBU_MQTT_HOST=cn.mqtt.bambulab.com
BAMBU_MQTT_PORT=8883
BAMBU_USER_ID=your_uid
BAMBU_ACCESS_TOKEN=your_access_token
BAMBU_DEVICE_ID=your_printer_device_id

YI_IP=192.168.2.194
YI_USER=admin
YI_PASSWORD=your_camera_password

AUTO_CAPTURE=true
SNAPSHOT_DELAY=0.5
SNAPSHOT_RETRIES=3
CAPTURE_EVERY_LAYERS=1

AUTO_GENERATE_VIDEO=true
TIMELAPSE_FPS=30

TIMELAPSE_DIR=./data/timelapse
DATABASE_PATH=./data/db/app.db
WEB_DIST=./web/dist
WEB_PORT=8000
```

Main options:

| Variable | Description |
| --- | --- |
| `BAMBU_MQTT_HOST` | Bambu Cloud MQTT hostname |
| `BAMBU_MQTT_PORT` | MQTT TLS port |
| `BAMBU_USER_ID` | Bambu account user ID |
| `BAMBU_ACCESS_TOKEN` | Bambu Cloud access token |
| `BAMBU_DEVICE_ID` | Printer device ID |
| `YI_IP` | Yi camera IP address |
| `YI_USER` | Yi Hack HTTP username |
| `YI_PASSWORD` | Yi Hack HTTP password |
| `AUTO_CAPTURE` | Enable automatic layer snapshots |
| `SNAPSHOT_DELAY` | Delay before taking a snapshot |
| `SNAPSHOT_RETRIES` | Number of snapshot retries |
| `CAPTURE_EVERY_LAYERS` | Capture every N layers |
| `AUTO_GENERATE_VIDEO` | Generate MP4 automatically after completion |
| `TIMELAPSE_FPS` | Output video frame rate |
| `DATABASE_PATH` | SQLite database path |
| `TIMELAPSE_DIR` | Snapshot and video storage directory |
| `WEB_PORT` | Host port for the web application |

## Local Development

Backend:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python main.py
```

Frontend:

```bash
cd web
npm install
npm run dev
```

The Vite development server proxies backend API and WebSocket traffic to the local FastAPI service.

For normal deployments, Docker Compose is recommended.

## Project Structure

```text
bambu-timelapse/
├── app/
│   ├── core/
│   │   ├── config.py
│   │   └── events.py
│   ├── integrations/
│   │   ├── bambu/
│   │   │   └── mqtt.py
│   │   └── yi/
│   │       └── camera.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── capture_service.py
│   │   ├── print_service.py
│   │   └── timelapse_service.py
│   ├── storage/
│   │   └── database.py
│   ├── web/
│   │   ├── api.py
│   │   └── websocket.py
│   └── main.py
├── web/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue
│       │   ├── Jobs.vue
│       │   ├── Devices.vue
│       │   ├── Settings.vue
│       │   ├── Login.vue
│       │   └── ChangePassword.vue
│       ├── api.js
│       ├── auth.js
│       └── theme.js
├── docs/
├── Dockerfile
├── docker-compose.yml
├── main.py
└── requirements.txt
```

## API Overview

Authentication:

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/change-password
POST /api/auth/logout
```

Application:

```text
GET  /api/status
GET  /api/printer
GET  /api/camera
POST /api/camera/test
POST /api/camera/snapshot

GET  /api/jobs
GET  /api/jobs/{id}
GET  /api/jobs/{id}/frames/{filename}
GET  /api/jobs/{id}/video

GET  /api/settings

WS   /ws
GET  /health
```

Except for the authentication endpoints required to sign in and change the initial password, application APIs and the WebSocket event stream require an authenticated session.

Sensitive tokens and camera passwords are not returned by the Settings API.

## Security Notes

Do not commit a real `.env` file.

Treat the following values as secrets:

```text
BAMBU_ACCESS_TOKEN
Bambu LAN Access Code
YI_PASSWORD
```

If any credential has been exposed publicly, rotate it before continuing to use the service.

If you expose this project outside your trusted LAN, use HTTPS and review the deployment security carefully before doing so.

## Related and Reference Projects

This project was made possible by public documentation, reverse-engineering work, and community projects around Bambu Lab and Yi cameras.

Useful references include:

- [yi-hack-v5](https://github.com/alienatedsec/yi-hack-v5)
- [yi-hack-Allwinner](https://github.com/roleoroleo/yi-hack-Allwinner)
- [Bambu-Lab-Cloud-API](https://github.com/coelacant1/Bambu-Lab-Cloud-API)
- [OpenBambuAPI](https://github.com/PhilosophersStone/openbambuapi)

These projects may contain broader protocol documentation, device support, reverse-engineering notes, or more complete implementations for their respective areas. Please consult their documentation and licenses independently.

## License

Licensed under the **Apache License 2.0**.

See [LICENSE](LICENSE) for the full license text.

## Learning and Experimental Use Notice

This repository is primarily intended for **learning, research, experimentation, and personal reference**.

It should not be treated as an official Bambu Lab or Yi Camera SDK, a guaranteed production-ready service, or a complete implementation of their cloud/device protocols.

The project relies on unofficially documented or community-researched interfaces. Cloud APIs, MQTT payloads, authentication behavior, camera firmware behavior, and device protocols may change at any time and may break compatibility without notice.

If you need a more complete or production-oriented implementation, use this repository as a reference and also review other established open-source projects in the Bambu Lab, MQTT, camera, and timelapse ecosystems. Compare their protocol handling, security model, device compatibility, error recovery, testing strategy, and licensing before building a production deployment.

You are responsible for evaluating the security, privacy, legal, warranty, network, and device risks of your own deployment. Respect the terms of service, software licenses, network policies, and applicable laws for every third-party service or device you use.
