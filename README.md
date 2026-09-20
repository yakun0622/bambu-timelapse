# bambu-timelapse

基于 **Bambu Lab Cloud MQTT + 小蚁摄像头 Yi Hack + FFmpeg** 的 3D 打印延时摄影工具。

项目监听拓竹打印机的云端 MQTT 状态，当检测到 `layer_num` 增加时，主动调用小蚁摄像头的 HTTP Snapshot 接口拍照，并按打印任务保存。打印完成后可自动将每层照片合成为 `timelapse.mp4`。

当前主要验证设备：

- Bambu Lab A1
- 中国区 Bambu Cloud
- 小蚁 Yi Home 720P（yi-hack-v5）
- 小蚁 Yi 1080P Home（可使用对应 Yi Hack，具体取决于硬件平台）

---

## 1. 项目原理

工作流程：

```text
Bambu Lab A1
    │
    │ Bambu Cloud MQTT
    │ device/<device_id>/report
    ▼
bambu-timelapse
    │
    ├── 合并 MQTT 增量状态
    ├── 监听 gcode_state
    ├── 监听 layer_num
    │
    └── layer_num 增加
             │
             ▼
       Yi Camera Snapshot
             │
             ▼
       layer_0001.jpg
       layer_0002.jpg
       layer_0003.jpg
             │
             ▼
           FFmpeg
             │
             ▼
       timelapse.mp4
```

Bambu Cloud MQTT 推送的是**增量状态**，不是每一条消息都包含全部字段，因此项目会持续合并收到的 `print` 数据。

例如可能先收到：

```json
{
  "print": {
    "layer_num": 10
  }
}
```

随后才收到：

```json
{
  "print": {
    "gcode_state": "RUNNING",
    "total_layer_num": 502,
    "mc_percent": 21
  }
}
```

项目会自动合并为完整状态。

---

## 2. 功能

- Bambu Cloud MQTT TLS 连接
- 支持中国区 MQTT Broker
- 自动合并增量状态
- 检测 `layer_num` 变化
- 防止同一层重复抓拍
- HTTP 调用小蚁 Snapshot 接口
- 抓拍失败自动重试
- 每个打印任务自动创建目录
- 打印完成自动调用 FFmpeg
- 自动生成 H.264 MP4
- 所有密码、Token、设备 ID 均通过 `.env` 配置

---

## 3. 项目结构

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

模块说明：

| 文件 | 作用 |
| --- | --- |
| `main.py` | 程序入口 |
| `config.py` | 加载 `.env` |
| `mqtt_client.py` | Bambu Cloud MQTT |
| `state_manager.py` | 打印状态、层数与任务管理 |
| `camera.py` | 小蚁 HTTP Snapshot |
| `timelapse.py` | FFmpeg 合成延时视频 |

---

# 4. 小蚁摄像头刷机

本项目依赖摄像头提供 HTTP Snapshot 接口：

```text
http://<CAMERA_IP>/cgi-bin/snapshot.sh?res=high&watermark=no
```

不同年代的小蚁摄像头硬件平台不同，**不要只根据“720P / 1080P”名称刷固件，必须确认型号、固件版本和硬件平台**。

## 4.1 Yi Home 720P / yi-hack-v5

我们实际验证过的设备：

```text
Model: Yi Home
Hardware ID: 17CN
原始固件: 1.8.7.0C_201705091058
Hack: yi-hack-v5 0.4.1
```

yi-hack-v5 对 Yi Home 使用：

```text
rootfs_y18
home_y18
```

官方支持表：

| Camera | rootfs | home | Base Firmware |
| --- | --- | --- | --- |
| Yi Home | `rootfs_y18` | `home_y18` | `1.8.7.0F_201809191400` |
| Yi 1080p Home | `rootfs_y20` | `home_y20` | `2.1.0.0E_201809191630` |

yi-hack-v5 官方仓库：

https://github.com/alienatedsec/yi-hack-v5

Release：

https://github.com/alienatedsec/yi-hack-v5/releases/tag/0.4.1

### SD 卡准备

推荐 16GB 或更小 microSD，FAT32。

macOS 示例：

```bash
diskutil list
diskutil eraseDisk FAT32 YICAM MBRFormat /dev/diskX
```

> 注意：请确认 `/dev/diskX` 确实是 SD 卡，不要选错系统盘。

将文件放到 SD 卡根目录：

```text
YICAM/
├── rootfs_y18
├── home_y18
└── yi-hack-v5/
```

macOS 建议清理 AppleDouble 文件：

```bash
dot_clean -m /Volumes/YICAM
```

### 刷机

1. 摄像头断电
2. 插入 microSD
3. 重新通电
4. 不要按 Reset
5. 不要中途断电
6. 黄灯闪烁约 30 秒
7. 进入第二阶段刷写
8. 最终蓝灯亮表示 Wi-Fi 正常连接
9. 浏览器打开：

```text
http://摄像头IP/
```

刷机过程中请严格使用与硬件匹配的固件文件。

---

## 4.2 Yi 1080P Home / Allwinner 平台

部分 Yi 1080P Home 并不是 yi-hack-v5 的 `y20` 平台。

例如我们遇到的原厂固件：

```text
8.2.0.0A_201912270941
```

这一类通常属于 **Allwinner 平台**，yi-hack-Allwinner 支持表中对应常见组合包括：

| Camera | Firmware | Prefix |
| --- | --- | --- |
| Yi 1080p Home 9FUS | 8.2.0* | `y20ga` |
| Yi 1080p Home BFUS | 8.2.0* | `y20ga` |
| Yi 1080p Home SFUS | 8.2.0* | `y20ga` |
| Yi 1080p Home BFCN | 8.2.0* | `y20ga` |

项目：

https://github.com/roleoroleo/yi-hack-Allwinner

> 不要将 yi-hack-v5 的 `rootfs_y20/home_y20` 强刷到 Allwinner `8.2.0*` 机器上。  
> 同样叫 “Yi 1080p Home”，内部硬件平台可能完全不同。

Allwinner 版官方建议根据：

```text
序列号前 4 位 + 原厂固件版本
```

共同判断对应固件。

---

# 5. 小蚁刷机后的配置

进入摄像头 WebUI：

```text
http://摄像头IP/
```

针对本项目建议：

| 设置 | 建议 |
| --- | --- |
| HTTPD | 开启 |
| RTSP | 可选 |
| RTSP Stream | High |
| RTSP Audio | 关闭 |
| Snapshot | 开启 |
| ONVIF | 不需要可关闭 |
| FTP | 不需要可关闭 |
| Telnet | 关闭 |
| SSH | 建议保留 |
| Disable Cloud | 如果还需要原 App 则关闭此选项 |
| Authentication | 建议开启 |

对于内存较小的老款摄像头，不建议一次开启所有服务。

Allwinner 平台如果开启 Snapshot 后出现重启，可以考虑按照 yi-hack-Allwinner 文档开启 Swap File。

## 5.1 测试 Snapshot

无认证：

```bash
curl -o test.jpg \
  "http://192.168.2.194/cgi-bin/snapshot.sh?res=high&watermark=no"
```

有 HTTP Basic Auth：

```bash
curl \
  -u 'admin:password' \
  -o test.jpg \
  "http://192.168.2.194/cgi-bin/snapshot.sh?res=high&watermark=no"
```

检查：

```bash
file test.jpg
```

应该得到 JPEG 图片。

---

# 6. 获取 Bambu Cloud Token

本项目为了同时保留 **Bambu Handy App 云端控制能力**，使用的是 **Bambu Cloud MQTT**，而不是让 A1 长期运行 LAN Only Mode。

中国区账号需要注意：

```text
Cloud API:
https://api.bambulab.cn

Cloud MQTT:
cn.mqtt.bambulab.com:8883
```

目前上游 `coelacant1/Bambu-Lab-Cloud-API` 主分支对中国区支持并不完整。

我们实际使用的是 PR #12 对应分支：

https://github.com/coelacant1/Bambu-Lab-Cloud-API/pull/12

分支仓库：

https://github.com/sparkwj/Bambu-Lab-Cloud-API/tree/feature/china_login_server

该分支增加：

- 中国区手机号登录
- 短信验证码
- `api.bambulab.cn`
- `cn.mqtt.bambulab.com`

## 6.1 下载登录工具

```bash
git clone \
  -b feature/china_login_server \
  https://github.com/sparkwj/Bambu-Lab-Cloud-API.git

cd Bambu-Lab-Cloud-API

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## 6.2 中国区登录

```bash
python cli_tools/login.py --region china
```

按照提示输入：

```text
Phone:
Password:
SMS Code:
```

登录成功后会生成并保存 Cloud Access Token。

> Cloud Access Token 属于敏感凭据，不要上传 GitHub，不要发到公开聊天、Issues 或日志系统。

---

# 7. 获取 Bambu USER_ID / DEVICE_ID

拿到 Access Token 后，可以使用 `query.py`。

假设：

```bash
export BBL_TOKEN='你的Access Token'
```

## 7.1 获取设备 ID

```bash
python cli_tools/query.py \
  "$BBL_TOKEN" \
  --region china \
  --json
```

典型返回：

```json
[
  {
    "dev_id": "xxxxxxxxxxxxxxx",
    "name": "A1",
    "online": true,
    "print_status": "RUNNING",
    "dev_model_name": "N2S",
    "dev_product_name": "A1",
    "nozzle_diameter": 0.4,
    "dev_structure": "I3"
  }
]
```

这里最重要的是：

```text
dev_id
```

填入：

```env
BAMBU_DEVICE_ID=xxxxxxxxxxxxxxx
```

> `dev_access_code` 是 LAN Access Code，本项目 Cloud MQTT 不需要它。不要公开。

## 7.2 获取 UID

```bash
python cli_tools/query.py \
  "$BBL_TOKEN" \
  --profile \
  --region china \
  --json
```

返回中找到：

```json
{
  "uid": 123456789
}
```

填入：

```env
BAMBU_USER_ID=123456789
```

MQTT 实际用户名会自动构造成：

```text
u_<BAMBU_USER_ID>
```

例如：

```text
u_123456789
```

MQTT Password 则是：

```text
BAMBU_ACCESS_TOKEN
```

---

# 8. Bambu MQTT 关键参数

中国区：

```text
Host: cn.mqtt.bambulab.com
Port: 8883
TLS: Yes
Username: u_<uid>
Password: <Cloud Access Token>
Topic: device/<dev_id>/report
```

例如：

```text
device/xxxxxxxxxxxxxxx/report
```

常用打印字段：

| 字段 | 含义 |
| --- | --- |
| `gcode_state` | 打印状态，例如 RUNNING / FINISH |
| `layer_num` | 当前层 |
| `total_layer_num` | 总层数 |
| `mc_percent` | 打印进度 |
| `subtask_name` | 打印任务名称 |
| `gcode_file` | G-code 文件 |
| `bed_temper` | 热床温度 |
| `nozzle_temper` | 喷嘴温度 |
| `wifi_signal` | Wi-Fi 信号 |

典型 MQTT 数据：

```json
{
  "print": {
    "gcode_state": "RUNNING",
    "layer_num": 11,
    "total_layer_num": 502,
    "mc_percent": 21
  }
}
```

但实际消息经常只有部分字段，例如：

```json
{
  "print": {
    "layer_num": 11
  }
}
```

因此不能假设每条消息都是完整状态。

---

# 9. 安装 bambu-timelapse

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

复制配置：

```bash
cp .env.example .env
nano .env
```

---

# 10. 配置 .env

示例：

```env
# Bambu Cloud MQTT
BAMBU_MQTT_HOST=cn.mqtt.bambulab.com
BAMBU_USER_ID=your_uid
BAMBU_ACCESS_TOKEN=your_access_token
BAMBU_DEVICE_ID=your_printer_device_id

# Yi Camera
YI_IP=192.168.2.194
YI_USER=admin
YI_PASSWORD=your_camera_password

# Capture
SNAPSHOT_DELAY=0.5
SNAPSHOT_RETRIES=3

# Video
TIMELAPSE_FPS=30
TIMELAPSE_DIR=./timelapse
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `BAMBU_MQTT_HOST` | Bambu MQTT Broker |
| `BAMBU_USER_ID` | Bambu UID，不带 `u_` |
| `BAMBU_ACCESS_TOKEN` | Cloud Access Token |
| `BAMBU_DEVICE_ID` | 打印机 `dev_id` |
| `YI_IP` | 小蚁摄像头 IP |
| `YI_USER` | 小蚁 HTTP 用户名 |
| `YI_PASSWORD` | 小蚁 HTTP 密码 |
| `SNAPSHOT_DELAY` | 换层后延迟多少秒抓拍 |
| `SNAPSHOT_RETRIES` | 抓拍失败重试次数 |
| `TIMELAPSE_FPS` | 成片 FPS |
| `TIMELAPSE_DIR` | 输出目录 |

---

# 11. 运行

```bash
source venv/bin/activate
python main.py
```

正常日志：

```text
[mqtt] connecting to cn.mqtt.bambulab.com:8883
[mqtt] connected: Success
[mqtt] subscribed: device/xxxxxxxxxxxxxxx/report

[status] state=RUNNING layer=10/502 progress=21%
[layer] initial: 10/502

[status] state=RUNNING layer=11/502 progress=21%
[layer] changed: 10 -> 11/502

[camera] saved 11/502:
timelapse/20260920_120000_model/layer_0011.jpg
```

第一次启动时：

```text
[layer] initial: 10/502
```

只用于初始化，不会马上拍照。

只有真正发生：

```text
10 -> 11
```

时才会抓拍。

---

# 12. 输出

```text
timelapse/
└── 20260920_120000_model/
    ├── layer_0011.jpg
    ├── layer_0012.jpg
    ├── layer_0013.jpg
    ├── ...
    └── timelapse.mp4
```

FFmpeg 默认使用：

```text
H.264
CRF 18
yuv420p
faststart
```

---

# 13. 关于拍摄时机

当前逻辑是：

```text
检测 layer_num 增加
        ↓
等待 SNAPSHOT_DELAY
        ↓
抓拍
```

这已经适合普通打印延时。

如果需要类似 Octolapse 的稳定效果，则还需要进一步实现：

```text
一层完成
   ↓
喷头移动到固定位置
   ↓
等待机械振动停止
   ↓
摄像头拍照
   ↓
继续打印
```

目前项目**不会主动控制打印机运动**，只读取 Cloud MQTT 状态，因此不会改变现有打印流程。

---

# 14. 安全注意事项

以下参数都属于敏感信息：

```text
BAMBU_ACCESS_TOKEN
Bambu LAN Access Code
YI_PASSWORD
```

不要提交到 GitHub。

本项目已经在 `.gitignore` 中忽略：

```text
.env
```

建议只提交：

```text
.env.example
```

如果 Cloud Token、LAN Access Code 或摄像头密码已经公开，请及时更换。

另外，不建议将 Yi 摄像头的 HTTP / RTSP 端口直接暴露到公网。

---

# 15. 参考项目

Yi Hack v5:

https://github.com/alienatedsec/yi-hack-v5

Yi Hack Allwinner:

https://github.com/roleoroleo/yi-hack-Allwinner

Bambu Lab Cloud API:

https://github.com/coelacant1/Bambu-Lab-Cloud-API

中国区支持 PR:

https://github.com/coelacant1/Bambu-Lab-Cloud-API/pull/12

中国区兼容分支:

https://github.com/sparkwj/Bambu-Lab-Cloud-API/tree/feature/china_login_server

---

## Disclaimer

本项目依赖 Bambu Lab 非官方公开的 Cloud API / MQTT 协议实现，以及第三方 Yi Hack 固件。

Bambu Lab 或 Yi 后续固件、认证方式、MQTT 协议或 Cloud API 发生变化时，本项目可能需要同步调整。

刷写第三方摄像头固件存在风险，请自行确认摄像头具体硬件型号、原厂固件版本以及对应 Hack 项目是否支持。
