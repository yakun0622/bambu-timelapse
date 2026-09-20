# Docker 部署

项目支持 Docker Compose 常驻运行。

Docker 镜像中已经安装：

- Python
- 项目 Python 依赖
- FFmpeg
- CA Certificates
- tzdata

打印照片和最终视频通过 volume 保存到宿主机，不会因为容器重建而丢失。

---

## 1. 准备

确保服务器已经安装 Docker 与 Docker Compose Plugin。

检查：

```bash
docker --version
docker compose version
```

克隆项目：

```bash
git clone https://github.com/yakun0622/bambu-timelapse.git
cd bambu-timelapse
```

---

## 2. 配置 .env

复制配置：

```bash
cp .env.example .env
nano .env
```

至少需要填写：

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
```

Docker Compose 会把容器内输出目录固定为：

```text
/data/timelapse
```

并映射到宿主机：

```text
./timelapse
```

因此不需要在 `.env` 中单独修改 `TIMELAPSE_DIR`。

---

## 3. 构建并启动

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看实时日志：

```bash
docker compose logs -f
```

正常情况下会看到：

```text
[mqtt] connecting to cn.mqtt.bambulab.com:8883
[mqtt] connected: Success
[mqtt] subscribed: device/xxxxxxxxxxxxxxx/report
[status] state=RUNNING layer=10/502 progress=21%
```

---

## 4. 输出目录

宿主机：

```text
./timelapse/
└── 20260920_120000_model/
    ├── layer_0011.jpg
    ├── layer_0012.jpg
    ├── ...
    └── timelapse.mp4
```

容器内对应：

```text
/data/timelapse/
```

---

## 5. 常用命令

启动：

```bash
docker compose up -d
```

停止：

```bash
docker compose down
```

重启：

```bash
docker compose restart
```

查看日志：

```bash
docker compose logs -f --tail=200
```

更新代码并重新构建：

```bash
git pull
docker compose up -d --build
```

进入容器：

```bash
docker compose exec bambu-timelapse bash
```

检查 FFmpeg：

```bash
docker compose exec bambu-timelapse ffmpeg -version
```

---

## 6. 测试摄像头连通性

容器需要能够访问小蚁摄像头所在局域网。

例如摄像头：

```text
192.168.2.194
```

可进入容器测试 Python HTTP 请求：

```bash
docker compose exec bambu-timelapse python - <<'PY'
import os
import requests

ip = os.environ["YI_IP"]
user = os.environ["YI_USER"]
password = os.environ["YI_PASSWORD"]

url = f"http://{ip}/cgi-bin/snapshot.sh?res=high&watermark=no"
r = requests.get(url, auth=(user, password), timeout=10)

print(r.status_code)
print(r.headers.get("Content-Type"))
print(len(r.content))
PY
```

如果出现超时，先检查：

- Docker 主机本身能否访问摄像头 IP
- 摄像头与 Docker 主机之间是否有 VLAN / 防火墙隔离
- `YI_IP` 是否正确
- HTTP Authentication 是否配置正确

Linux Docker 的 bridge 网络通常可以直接访问宿主机所在 LAN，无需使用 host network。

---

## 7. 时区

Compose 默认：

```text
Asia/Shanghai
```

如果需要修改，可在启动前设置：

```bash
export TZ=Asia/Tokyo
docker compose up -d
```

或者创建一个 Compose 专用环境变量：

```bash
TZ=Asia/Tokyo docker compose up -d
```

时区主要影响打印任务目录中的时间戳和日志时间。

---

## 8. 开机自动启动

Compose 中已经设置：

```yaml
restart: unless-stopped
```

只要 Docker 服务开机启动，容器会自动恢复。

Debian / Ubuntu 可确认：

```bash
systemctl enable --now docker
```

---

## 9. 安全

真实 `.env` 已在 `.gitignore` 和 `.dockerignore` 中忽略。

不要把以下内容提交到仓库：

- Bambu Cloud Access Token
- Bambu LAN Access Code
- Yi Camera Password

如果凭据曾经公开，请及时更换。
