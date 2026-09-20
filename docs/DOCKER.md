# Docker 部署

当前 Docker 镜像包含：

- Python 3.12
- FastAPI / Uvicorn
- FFmpeg
- Vue 3 构建后的 Web UI
- CA Certificates
- tzdata

SQLite、抓拍图片和 MP4 全部保存在宿主机 `./data`，重建容器不会丢失。

## 1. 准备

```bash
docker --version
docker compose version
```

克隆：

```bash
git clone https://github.com/yakun0622/bambu-timelapse.git
cd bambu-timelapse
```

## 2. 配置

```bash
cp .env.example .env
nano .env
```

填写 Bambu 与 Yi 参数。

Docker Compose 会覆盖以下容器内路径：

```text
TIMELAPSE_DIR=/data/timelapse
DATABASE_PATH=/data/app.db
WEB_DIST=/app/web/dist
```

宿主机对应：

```text
./data/
├── app.db
└── timelapse/
```

## 3. 启动

```bash
docker compose up -d --build
```

查看：

```bash
docker compose ps
docker compose logs -f --tail=200
```

打开 Web：

```text
http://服务器IP:8000
```

如果需要修改端口：

```bash
WEB_PORT=8088 docker compose up -d
```

然后访问：

```text
http://服务器IP:8088
```

## 4. Web 页面

- `/` Dashboard
- `/jobs` 历史打印任务
- `/devices` 设备状态与摄像头测试
- `/settings` 当前配置
- `/health` 服务健康状态

## 5. 更新

```bash
git pull
docker compose up -d --build
```

## 6. 常用命令

```bash
docker compose restart
docker compose down
docker compose logs -f
docker compose exec bambu-timelapse bash
docker compose exec bambu-timelapse ffmpeg -version
```

## 7. 摄像头网络

容器需要能访问 `YI_IP`。

Linux Docker bridge 网络一般可以直接访问局域网设备。如果 Web 页面 Devices -> Test camera 失败，再检查：

- Docker 主机能否访问摄像头
- VLAN / 防火墙
- Yi IP
- HTTP 用户名密码
- Snapshot 是否已开启

## 8. 开机启动

Compose 已配置：

```yaml
restart: unless-stopped
```

确认 Docker 服务开机启动：

```bash
systemctl enable --now docker
```

## 9. 安全

`.env` 同时被 `.gitignore` 与 `.dockerignore` 忽略。

不要把 Bambu Token、LAN Access Code 或 Yi 密码写入镜像或提交到仓库。
