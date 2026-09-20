# bambu-timelapse

基于 **Bambu Lab Cloud MQTT + 小蚁摄像头 Yi Hack + FFmpeg** 的 3D 打印延时摄影工具。

项目监听拓竹打印机的云端 MQTT 状态，当检测到 `layer_num` 增加时，主动调用小蚁摄像头的 HTTP Snapshot 接口拍照；打印完成后可自动把每层照片合成为 `timelapse.mp4`。

当前主要验证：

- Bambu Lab A1
- 中国区 Bambu Cloud
- Yi Home 720P + yi-hack-v5
- Yi 1080P Home + 对应 Yi Hack

## 工作原理

```text
Bambu A1
   │
   │ Cloud MQTT
   ▼
bambu-timelapse
   │
   ├── 合并 MQTT 增量状态
   ├── 检测 layer_num
   └── 换层
        │
        ▼
   Yi Snapshot
        │
        ▼
   layer_XXXX.jpg
        │
        ▼
      FFmpeg
        │
        ▼
   timelapse.mp4
```

## 文档

完整准备工作拆分为独立说明：

- [小蚁摄像头刷机与配置](docs/YI_CAMERA_SETUP.md)
- [Bambu Cloud Token 与关键参数获取](docs/BAMBU_CLOUD_SETUP.md)

## 快速开始

### 1. 准备小蚁摄像头

刷入与你的硬件平台匹配的 Yi Hack，并确认以下接口可以正常返回 JPEG：

```text
http://<YI_IP>/cgi-bin/snapshot.sh?res=high&watermark=no
```

详细步骤：

[docs/YI_CAMERA_SETUP.md](docs/YI_CAMERA_SETUP.md)

### 2. 获取 Bambu Cloud 参数

需要：

```text
BAMBU_USER_ID
BAMBU_ACCESS_TOKEN
BAMBU_DEVICE_ID
```

中国区默认 MQTT：

```text
cn.mqtt.bambulab.com:8883
```

详细获取方法：

[docs/BAMBU_CLOUD_SETUP.md](docs/BAMBU_CLOUD_SETUP.md)

### 3. 安装

Debian / Ubuntu：

```bash
apt update
apt install -y python3-venv ffmpeg

git clone https://github.com/yakun0622/bambu-timelapse.git
cd bambu-timelapse

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 配置

```bash
cp .env.example .env
nano .env
```

示例：

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

### 5. 运行

```bash
source venv/bin/activate
python main.py
```

正常日志：

```text
[mqtt] connected: Success
[mqtt] subscribed: device/xxxxxxxxxxxxxxx/report
[status] state=RUNNING layer=10/502 progress=21%
[layer] initial: 10/502
[status] state=RUNNING layer=11/502 progress=21%
[layer] changed: 10 -> 11/502
[camera] saved 11/502: timelapse/.../layer_0011.jpg
```

第一次看到的层数只用于初始化，不会马上抓拍；之后只有真正发生层数增加时才拍照。

## 输出

```text
timelapse/
└── 20260920_120000_model/
    ├── layer_0011.jpg
    ├── layer_0012.jpg
    ├── layer_0013.jpg
    └── timelapse.mp4
```

## 项目结构

```text
bambu-timelapse/
├── docs/
│   ├── BAMBU_CLOUD_SETUP.md
│   └── YI_CAMERA_SETUP.md
├── .env.example
├── camera.py
├── config.py
├── main.py
├── mqtt_client.py
├── state_manager.py
├── timelapse.py
└── requirements.txt
```

## 当前拍摄逻辑

```text
检测 layer_num 增加
        ↓
等待 SNAPSHOT_DELAY
        ↓
抓拍
```

当前项目只读取 Cloud MQTT，不主动控制打印机运动，因此不会改变打印流程。

后续如果要实现更接近 Octolapse 的效果，可以增加“每层结束后喷头移动到固定位置再拍照”的模式。

## 安全

不要提交真实 `.env`。

敏感信息包括：

```text
BAMBU_ACCESS_TOKEN
Bambu LAN Access Code
YI_PASSWORD
```

如果这些凭据已经公开，请及时更换。

## 参考项目

- https://github.com/alienatedsec/yi-hack-v5
- https://github.com/roleoroleo/yi-hack-Allwinner
- https://github.com/coelacant1/Bambu-Lab-Cloud-API
- https://github.com/coelacant1/Bambu-Lab-Cloud-API/pull/12

## Disclaimer

本项目依赖非官方公开的 Bambu Cloud API / MQTT 协议实现，以及第三方 Yi Hack 固件。

Bambu Lab 或 Yi 后续固件、认证方式、MQTT 协议或 Cloud API 发生变化时，本项目可能需要同步调整。刷写第三方摄像头固件也存在风险，请确认硬件与固件匹配后再操作。
