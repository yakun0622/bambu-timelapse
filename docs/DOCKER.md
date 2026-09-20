# Docker 部署

当前 Docker 镜像包含：

- Python 3.12
- FastAPI / Uvicorn
- FFmpeg
- Vue 3 构建后的 Web UI
- CA Certificates
- tzdata

## 持久化说明

Docker 重建、升级或删除容器后，以下数据必须保留在宿主机：

- SQLite 数据库
- 每层抓拍图片
- 自动生成的 MP4

Compose 使用显式目录映射：

```yaml
volumes:
  - ./data/db:/data/db
  - ./data/timelapse:/data/timelapse
```

对应关系：

```text
宿主机                           容器
./data/db/              ->       /data/db/
./data/timelapse/       ->       /data/timelapse/
```

数据库文件：

```text
./data/db/app.db
```

抓拍和视频：

```text
./data/timelapse/
└── 20260920_120000_model/
    ├── layer_0041.jpg
    ├── layer_0042.jpg
    └── timelapse.mp4
```

因此执行：

```bash
docker compose down
docker compose up -d --build
```

不会删除历史数据库、图片或视频。

> 不要执行 `rm -rf data`，否则持久化数据也会被删除。

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

建议先创建持久化目录：

```bash
mkdir -p data/db data/timelapse
```

## 2. 配置

```bash
cp .env.example .env
nano .env
```

Docker Compose 会在容器内使用：

```text
TIMELAPSE_DIR=/data/timelapse
DATABASE_PATH=/data/db/app.db
WEB_DIST=/app/web/dist
```

其中 Web 静态资源属于应用镜像的一部分，会随版本更新重新构建；用户产生的数据不会放在镜像里。

## 3. 从旧版本迁移

如果你之前使用旧目录结构：

```text
./data/app.db
./data/timelapse/
```

升级前执行：

```bash
mkdir -p data/db
mv data/app.db data/db/app.db
```

如果 `data/app.db` 不存在则无需执行。

原来的：

```text
./data/timelapse/
```

不需要移动。

## 4. 启动

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

修改端口：

```bash
WEB_PORT=8088 docker compose up -d
```

## 5. 备份

只需要备份：

```text
data/db/
data/timelapse/
.env
```

例如：

```bash
tar czf bambu-timelapse-backup.tar.gz \
  data/db \
  data/timelapse \
  .env
```

恢复时把这些文件放回项目目录，再启动容器即可。

## 6. 更新

```bash
git pull
docker compose up -d --build
```

数据库和资源目录不会因为镜像更新而改变。

## 7. 常用命令

```bash
docker compose restart
docker compose down
docker compose logs -f
docker compose exec bambu-timelapse bash
docker compose exec bambu-timelapse ffmpeg -version
```

## 8. 摄像头网络

容器需要能访问 `YI_IP`。

Linux Docker bridge 网络一般可以直接访问局域网设备。如果 Web 页面 Devices -> Test camera 失败，再检查：

- Docker 主机能否访问摄像头
- VLAN / 防火墙
- Yi IP
- HTTP 用户名密码
- Snapshot 是否已开启

## 9. 开机启动

Compose 已配置：

```yaml
restart: unless-stopped
```

确认 Docker 服务开机启动：

```bash
systemctl enable --now docker
```

## 10. 安全

`.env` 同时被 `.gitignore` 与 `.dockerignore` 忽略。

不要把 Bambu Token、LAN Access Code 或 Yi 密码写入镜像或提交到仓库。
