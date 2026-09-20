# 小蚁摄像头刷机与配置

本项目需要小蚁摄像头提供 HTTP Snapshot 接口：

```text
http://<CAMERA_IP>/cgi-bin/snapshot.sh?res=high&watermark=no
```

不同年代的小蚁摄像头虽然名称接近，但内部硬件平台可能不同。刷机前必须确认型号、序列号前缀和原厂固件版本。

---

## 1. Yi Home 720P / yi-hack-v5

实际验证设备：

```text
Model: Yi Home
Hardware ID: 17CN
原始固件: 1.8.7.0C_201705091058
Hack: yi-hack-v5 0.4.1
```

对应文件：

```text
rootfs_y18
home_y18
```

yi-hack-v5 官方支持表中：

| Camera | rootfs | home | Base Firmware |
| --- | --- | --- | --- |
| Yi Home | `rootfs_y18` | `home_y18` | `1.8.7.0F_201809191400` |
| Yi 1080p Home | `rootfs_y20` | `home_y20` | `2.1.0.0E_201809191630` |

项目：

https://github.com/alienatedsec/yi-hack-v5

Release：

https://github.com/alienatedsec/yi-hack-v5/releases/tag/0.4.1

### SD 卡准备

推荐 16GB 或更小 microSD，格式化为 FAT32。

macOS 示例：

```bash
diskutil list
diskutil eraseDisk FAT32 YICAM MBRFormat /dev/diskX
```

注意确认 `/dev/diskX` 是 SD 卡。

将文件放到 SD 卡根目录：

```text
YICAM/
├── rootfs_y18
├── home_y18
└── yi-hack-v5/
```

macOS 可清理 AppleDouble 文件：

```bash
dot_clean -m /Volumes/YICAM
```

### 刷机步骤

1. 摄像头断电
2. 插入 microSD
3. 重新通电
4. 不要按 Reset
5. 不要中途断电
6. 黄灯闪烁约 30 秒
7. 等待第二阶段刷写
8. 最终蓝灯亮表示 Wi-Fi 正常连接
9. 浏览器打开：

```text
http://摄像头IP/
```

刷写时务必使用与硬件匹配的固件文件。

---

## 2. Yi 1080P Home / Allwinner 平台

部分 Yi 1080P Home 不是 yi-hack-v5 的 `y20` 平台。

例如原厂固件：

```text
8.2.0.0A_201912270941
```

这类常见为 Allwinner 平台。

yi-hack-Allwinner 支持表中常见组合：

| Camera | Firmware | Prefix |
| --- | --- | --- |
| Yi 1080p Home 9FUS | 8.2.0* | `y20ga` |
| Yi 1080p Home BFUS | 8.2.0* | `y20ga` |
| Yi 1080p Home SFUS | 8.2.0* | `y20ga` |
| Yi 1080p Home BFCN | 8.2.0* | `y20ga` |

项目：

https://github.com/roleoroleo/yi-hack-Allwinner

判断时使用：

```text
序列号前 4 位 + 原厂固件版本
```

不要将 yi-hack-v5 的 `rootfs_y20/home_y20` 强刷到 Allwinner `8.2.0*` 机器。

---

## 3. 刷机后的推荐配置

进入：

```text
http://摄像头IP/
```

建议：

| 设置 | 建议 |
| --- | --- |
| HTTPD | 开启 |
| Snapshot | 开启 |
| RTSP | 可选 |
| RTSP Stream | High |
| RTSP Audio | 关闭 |
| ONVIF | 不需要可关闭 |
| FTP | 不需要可关闭 |
| Telnet | 关闭 |
| SSH | 建议保留 |
| Disable Cloud | 需要原 App 时不要开启 |
| Authentication | 建议开启 |

老款摄像头 RAM 很小，不建议把所有服务都打开。

Allwinner 平台如果启用 Snapshot 后出现重启，可按项目文档启用 Swap File。

---

## 4. 测试 Snapshot

无认证：

```bash
curl -o test.jpg \
  "http://192.168.2.194/cgi-bin/snapshot.sh?res=high&watermark=no"
```

Basic Auth：

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

应识别为 JPEG 图片。

---

## 5. 安全提醒

不要把摄像头密码提交到 GitHub。

不建议把摄像头 HTTP / RTSP 端口直接暴露到公网。

第三方固件存在刷机风险，请确认设备型号与固件匹配后再操作。
