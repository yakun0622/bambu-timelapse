# bambu-timelapse

基于 **Bambu Lab Cloud MQTT + 小蚁摄像头 Yi Hack + FFmpeg** 的 3D 打印延时摄影工具。

项目监听拓竹打印机的云端 MQTT 状态，自动识别打印开始、进度、换层和结束；每次检测到 `layer_num` 增加时调用小蚁摄像头 Snapshot 接口抓拍，任务结束后自动生成延时视频。

当前版本已经升级为完整服务：

- FastAPI 后端
- WebSocket 实时事件
- Vue 3 Web Dashboard
- SQLite 任务记录
- Bambu Cloud MQTT
- Yi Camera Snapshot
- FFmpeg 自动合成
- Docker Compose 一键部署

## 页面

Web 端包含 4 个页面：

- **Dashboard**：当前打印、层数、进度、抓拍状态、实时事件
- **Jobs**：历史打印任务、帧列表、视频下载
- **Devices**：打印机状态、摄像头连接测试
- **Settings**：查看当前 Bambu / Camera / Capture / Video 配置

Docker 默认访问：

```text
http://服务器IP:8000
```

## 自动任务生命周期

```text
Bambu Cloud MQTT
        │
        ▼
 gcode_state=RUNNING
 + 有效 layer_num
        │
        ▼
   自动创建 PrintJob
        │
        ▼
   layer N -> N+1
        │
        ▼
     自动抓拍
        │
        ▼
 mc_percent -> 100%
 等待 FINISH 确认
        │
        ▼
 gcode_state=FINISH
        │
        ▼
   停止抓拍 / 保存任务
        │
        ▼
      FFmpeg
        │
        ▼
   timelapse.mp4
```

暂停时任务保持为 `PAUSED`，恢复后继续原任务；取消或失败时保留已抓拍图片但不自动生成正式成片。

## 文档

- [小蚁摄像头刷机与配置](docs/YI_CAMERA_SETUP.md)
- [Bambu Cloud Token 与关键参数获取](docs/BAMBU_CLOUD_SETUP.md)
- [Docker 部署](docs/DOCKER.md)

## Docker 快速开始

```bash
git clone https://github.com/yakun0622/bambu-timelapse.git
cd bambu-timelapse

cp .env.example .env
nano .env

docker compose up -d --build
docker compose logs -f
```

打开：

```text
http://服务器IP:8000
```

默认持久化数据保存在：

```text
./data/
├── db/
│   └── app.db
└── timelapse/
    ├── layer_XXXX.jpg
    └── timelapse.mp4
```

Docker Compose 对数据库和资源文件使用独立宿主机映射，因此重建容器不会丢失历史数据。

## Python 本地运行

后端：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python main.py
```

前端开发：

```bash
cd web
npm install
npm run dev
```

Vite 开发服务器会代理 `/api` 和 `/ws` 到后端 `127.0.0.1:8000`。

生产环境推荐使用 Docker，镜像构建阶段会自动执行 Vue 构建并由 FastAPI 提供静态页面。

## 配置

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

其中：

- `AUTO_CAPTURE`：自动抓拍开关
- `SNAPSHOT_DELAY`：换层后等待时间
- `CAPTURE_EVERY_LAYERS`：每 N 层抓拍一次
- `AUTO_GENERATE_VIDEO`：打印完成自动生成 MP4
- `TIMELAPSE_FPS`：成片帧率

## 项目结构

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
│       │   └── Settings.vue
│       └── ...
├── docs/
├── Dockerfile
├── docker-compose.yml
├── main.py
└── requirements.txt
```

## API

主要接口：

```text
GET  /api/status
GET  /api/printer
GET  /api/camera
POST /api/camera/test
POST /api/camera/snapshot

GET  /api/jobs
GET  /api/jobs/{id}
GET  /api/jobs/{id}/video

GET  /api/settings

WS   /ws
GET  /health
```

敏感 Token 和摄像头密码不会通过 Settings API 返回给浏览器。

## 任务唯一标识

Cloud 打印任务优先使用 Bambu MQTT 返回的任务 ID 识别同一打印：

```text
subtask_id
   ↓ 不存在
task_id
   ↓ 不存在 / 为 0
本地 fallback key
```

数据库会保存：

```text
bambu_task_id
bambu_subtask_id
job_key
```

Cloud 任务的 `job_key` 形如：

```text
bambu:<device_id>:subtask:<subtask_id>
```

因此服务重启、Docker 重建或 MQTT 重连后，会优先根据同一个 Bambu Task/Subtask 恢复原任务，而不是创建新的 Job。

本地 / SD 卡打印如果 Bambu 返回 `task_id=0`、`subtask_id=0`，则退化为持久化的本地任务 key，并继续结合层数与任务名称判断生命周期。

数据库升级为自动迁移，不需要手动删除现有 `app.db`。

## 抓拍规则

启动服务时如果打印已经进行到第 10 层：

```text
INITIAL = 10
```

不会立即拍一张。

只有真正发生：

```text
10 -> 11
```

才会触发抓拍。

同时要求：

```text
gcode_state == RUNNING
progress < 100
```

这样暂停、完成阶段不会继续产生无效帧。

## 安全

不要提交真实 `.env`。

敏感信息：

```text
BAMBU_ACCESS_TOKEN
Bambu LAN Access Code
YI_PASSWORD
```

如果已经公开，请及时更换。

## 参考项目

- https://github.com/alienatedsec/yi-hack-v5
- https://github.com/roleoroleo/yi-hack-Allwinner
- https://github.com/coelacant1/Bambu-Lab-Cloud-API
- https://github.com/coelacant1/Bambu-Lab-Cloud-API/pull/12

## Disclaimer

本项目依赖非官方公开的 Bambu Cloud API / MQTT 协议实现，以及第三方 Yi Hack 固件。相关云端协议、认证方式或设备固件变化后，本项目可能需要同步调整。
