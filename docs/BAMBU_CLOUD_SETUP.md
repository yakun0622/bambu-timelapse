# Bambu Cloud Token 与关键参数获取

本项目使用 **Bambu Cloud MQTT**，这样可以继续保留 Bambu Handy App 的云端控制能力，不需要让 A1 长期运行 LAN Only Mode。

---

## 1. 中国区关键地址

```text
Cloud API:
https://api.bambulab.cn

Cloud MQTT:
cn.mqtt.bambulab.com:8883
```

中国区账号需要支持手机号和短信验证码的登录流程。

当前我们实际使用：

https://github.com/coelacant1/Bambu-Lab-Cloud-API/pull/12

兼容分支：

https://github.com/sparkwj/Bambu-Lab-Cloud-API/tree/feature/china_login_server

该分支增加：

- 中国区手机号登录
- 短信验证码
- `api.bambulab.cn`
- `cn.mqtt.bambulab.com`

---

## 2. 获取 Cloud Access Token

下载工具：

```bash
git clone \
  -b feature/china_login_server \
  https://github.com/sparkwj/Bambu-Lab-Cloud-API.git

cd Bambu-Lab-Cloud-API

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

中国区登录：

```bash
python cli_tools/login.py --region china
```

按提示输入：

```text
Phone:
Password:
SMS Code:
```

登录成功后会获得 Cloud Access Token。

不要把 Token 上传 GitHub，也不要贴到公开 Issue、日志或聊天中。

---

## 3. 获取 DEVICE_ID

先保存 Token：

```bash
export BBL_TOKEN='你的Access Token'
```

查询设备：

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

将 `dev_id` 写入：

```env
BAMBU_DEVICE_ID=xxxxxxxxxxxxxxx
```

`dev_access_code` 是 LAN Access Code，本项目 Cloud MQTT 不需要它，不要公开。

---

## 4. 获取 USER_ID / UID

执行：

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

写入：

```env
BAMBU_USER_ID=123456789
```

程序会自动使用：

```text
u_<BAMBU_USER_ID>
```

作为 MQTT Username。

---

## 5. Cloud MQTT 参数

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

---

## 6. 常用 MQTT 字段

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

典型完整消息：

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

实际 Cloud MQTT 经常只推送增量字段，例如：

```json
{
  "print": {
    "layer_num": 11
  }
}
```

所以程序必须持续合并状态，不能假设每条 MQTT 消息都完整。

---

## 7. .env 对应关系

```env
BAMBU_MQTT_HOST=cn.mqtt.bambulab.com
BAMBU_USER_ID=your_uid
BAMBU_ACCESS_TOKEN=your_access_token
BAMBU_DEVICE_ID=your_printer_device_id
```

其中：

| 参数 | 来源 |
| --- | --- |
| `BAMBU_MQTT_HOST` | 中国区使用 `cn.mqtt.bambulab.com` |
| `BAMBU_USER_ID` | `query.py --profile` 返回的 `uid` |
| `BAMBU_ACCESS_TOKEN` | `login.py --region china` 获取 |
| `BAMBU_DEVICE_ID` | 设备列表中的 `dev_id` |

---

## 8. 安全提醒

以下都属于敏感凭据：

```text
BAMBU_ACCESS_TOKEN
Bambu LAN Access Code
```

不要提交到 GitHub。

如果已经泄露，请及时重新登录、刷新凭据或更换 LAN Access Code。
