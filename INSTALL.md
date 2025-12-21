# 🚂 Train Detection System - 安装和部署指南

## 📦 文件清单

```
train_detection_system/
├── witmotion_device_model_clean.py  # 设备驱动模型
├── train_detector.py                # 核心检测系统
├── test_detector.py                 # 测试脚本
├── witmotion_config.json            # 设备配置（树莓派MAC地址）
├── requirements.txt                 # Python依赖
├── start.sh                         # 快速启动脚本
├── README_DETECTOR.md               # 详细使用文档
└── INSTALL.md                       # 本文件
```

---

## 🚀 快速部署（树莓派）

### 1️⃣ 上传文件到树莓派

```bash
# 在你的电脑上
scp -r train_detection_system/ pi@raspberrypi.local:~/

# 或使用U盘/SD卡复制
```

### 2️⃣ SSH登录树莓派

```bash
ssh pi@raspberrypi.local
cd ~/train_detection_system
```

### 3️⃣ 安装依赖

```bash
# 更新系统
sudo apt update

# 安装Python3和pip（如果没有）
sudo apt install python3 python3-pip -y

# 安装蓝牙相关
sudo apt install bluetooth bluez libbluetooth-dev -y

# 安装Python依赖
pip3 install -r requirements.txt
```

### 4️⃣ 配置蓝牙

```bash
# 启用蓝牙
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# 扫描设备（可选，验证MAC地址）
sudo bluetoothctl
# 在bluetoothctl中：
# > scan on
# > 等待看到你的设备
# > scan off
# > exit
```

### 5️⃣ 编辑配置文件

```bash
nano witmotion_config.json
```

确认MAC地址正确，根据实际情况启用/禁用设备：

```json
{
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true    ← 改成false可以禁用
    }
  ]
}
```

### 6️⃣ 运行测试

```bash
# 使用启动脚本（推荐）
./start.sh
# 选择 1) Run tests

# 或直接运行
python3 test_detector.py
```

### 7️⃣ 启动检测

```bash
# 前台运行（可以看到实时输出）
python3 train_detector.py

# 或后台运行
nohup python3 train_detector.py > detector.log 2>&1 &

# 查看日志
tail -f detector.log

# 停止后台运行
pkill -f train_detector.py
```

---

## 🔧 配置说明

### 调整检测参数

编辑 `train_detector.py`，找到 `TrainDetector.__init__()`：

```python
# 第40-42行
self.threshold = 2.0                # 加速度阈值(g) - 降低=更敏感
self.min_duration = 1.0             # 最短持续时间(秒)
self.post_trigger_duration = 5.0    # 触发后记录时间(秒)
```

**建议调整流程**：
1. 先运行测试，观察静止时的加速度值（应该接近1.0g）
2. 手动晃动设备，看触发时的峰值
3. 根据实际火车震动情况调整阈值

---

## 📊 查看数据

### 数据存储位置

```bash
cd train_events/

# 查看事件数据库
sqlite3 events.db "SELECT * FROM events;"

# 查看最新事件
ls -lt event_*/
```

### 下载数据到电脑

```bash
# 在你的电脑上
scp -r pi@raspberrypi.local:~/train_detection_system/train_events/ ./
```

---

## ⚙️ 开机自启动（可选）

### 创建systemd服务

```bash
sudo nano /etc/systemd/system/train-detector.service
```

内容：

```ini
[Unit]
Description=Train Detection System
After=bluetooth.target network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/train_detection_system
ExecStart=/usr/bin/python3 /home/pi/train_detection_system/train_detector.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 启用服务

```bash
# 重载配置
sudo systemctl daemon-reload

# 启用开机自启
sudo systemctl enable train-detector

# 启动服务
sudo systemctl start train-detector

# 查看状态
sudo systemctl status train-detector

# 查看日志
sudo journalctl -u train-detector -f
```

### 管理服务

```bash
# 停止
sudo systemctl stop train-detector

# 重启
sudo systemctl restart train-detector

# 禁用自启
sudo systemctl disable train-detector
```

---

## 🐛 常见问题

### 问题1: 蓝牙权限错误

```bash
# 错误：Permission denied
# 解决：添加用户到蓝牙组
sudo usermod -a -G bluetooth $USER
# 需要重新登录生效
```

### 问题2: 找不到设备

```bash
# 检查蓝牙状态
sudo systemctl status bluetooth

# 手动扫描确认MAC地址
sudo bluetoothctl
> scan on
> devices
```

### 问题3: bleak安装失败

```bash
# 安装编译依赖
sudo apt install build-essential libdbus-1-dev libglib2.0-dev -y

# 重新安装
pip3 install --upgrade bleak
```

### 问题4: 内存不足

```bash
# 查看内存使用
free -h

# 如果内存紧张，减少缓冲区大小
# 编辑 train_detector.py，第109行：
# self.buffer = CircularBuffer(max_seconds=3, sample_rate=50)  # 从5秒改为3秒
```

---

## 📈 性能优化

### 树莓派Zero/1/2 (低性能)

```python
# 降低采样率和缓冲区
self.buffer = CircularBuffer(max_seconds=3, sample_rate=20)
```

### 树莓派3/4 (正常)

```python
# 默认配置即可
self.buffer = CircularBuffer(max_seconds=5, sample_rate=50)
```

---

## 🔜 下一步

1. ✅ 完成基础部署和测试
2. ⏳ 采集真实火车数据
3. ⏳ 根据数据优化阈值
4. ⏳ 开发Web API和Dashboard
5. ⏳ 添加4G上传功能

---

## 📞 需要帮助？

- 查看详细文档：`README_DETECTOR.md`
- 查看实时日志：`tail -f detector.log`
- 测试各个模块：`python3 test_detector.py`

祝部署顺利！🚂
