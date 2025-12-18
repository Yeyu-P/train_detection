# 火车检测系统 - Railway Track Monitoring System

基于IMU传感器的火车通过检测系统，带网络数据上传功能。

## 📁 文件说明

```
train_detection_final/
├── system_config.json              # 配置文件（修改这个）
├── train_detector_network.py       # 主程序（树莓派运行）
├── witmotion_device_model_clean.py # 设备驱动（不需要改）
├── server.py                       # 后端服务器
├── calibration_tool.py             # 阈值标定工具
└── README.md                       # 本文档
```

## 🚀 快速开始

### 1. 树莓派上安装依赖

```bash
# 更新系统
sudo apt update

# 安装依赖
sudo apt install -y python3-pip python3-numpy bluetooth bluez
pip3 install bleak numpy requests flask --break-system-packages

# 配置蓝牙权限
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))
```

### 2. 克隆仓库到树莓派

```bash
cd ~
git clone https://github.com/你的用户名/你的仓库名.git train_detection
cd train_detection
```

### 3. 修改配置文件

```bash
nano system_config.json
```

**必须修改的3个地方：**

1. **设备MAC地址** - 设置你的IMU设备
```json
"devices": [
  {
    "name": "Device_1",
    "mac": "AB35487E-B200-B802-E526-C512EA064361",  // ← 改成你的MAC地址
    "enabled": true  // ← 设为true启用
  }
]
```

2. **服务器地址** - 先用本地测试
```json
"network": {
  "enabled": true,
  "server_url": "http://localhost:5000/api",  // ← 本地服务器
  "api_key": "test-key-123"  // ← 随便设一个密钥
}
```

3. **检测阈值** - 标定后再改
```json
"detection": {
  "threshold_g": 2.0  // ← 先用默认值，标定后修改
}
```

### 4. 启动后端服务器（在树莓派上）

```bash
# 修改server.py的API密钥（和配置文件一致）
nano server.py
# 找到: API_KEY = 'your-secret-key-here'
# 改成: API_KEY = 'test-key-123'

# 后台启动服务器
python3 server.py &
```

### 5. 阈值标定（重要！）

```bash
# 采集60秒数据
python3 calibration_tool.py system_config.json 60

# 记下建议阈值，例如：建议阈值: 1.174g
# 修改配置文件
nano system_config.json
# 把 "threshold_g": 2.0 改成标定的值
```

### 6. 运行主程序

```bash
# 前台运行（测试）
python3 train_detector_network.py system_config.json

# 后台运行（生产）
nohup python3 train_detector_network.py system_config.json > detector.log 2>&1 &
```

### 7. 查看数据

**浏览器查看：**
```
http://树莓派IP:5000/api/stats          # 统计信息
http://树莓派IP:5000/api/events/recent  # 最近事件
```

**查询数据库：**
```bash
sqlite3 train_monitoring.db
SELECT * FROM train_events ORDER BY start_time DESC LIMIT 10;
.quit
```

## 📊 配置文件详解

### system_config.json 主要参数

```json
{
  "detection": {
    "threshold_g": 2.0,          // 检测阈值（g），标定后修改
    "min_duration_sec": 0.5,     // 最小持续时间（秒）
    "cooldown_sec": 3.0          // 冷却时间（秒）
  },
  
  "storage": {
    "save_raw_data": true,       // 是否保存原始数据
    "auto_cleanup_days": 30      // 自动清理旧数据（天）
  },
  
  "network": {
    "enabled": true,             // 是否启用网络上传
    "server_url": "http://...",  // 服务器地址
    "api_key": "your-key"        // API密钥
  }
}
```

## 🔧 常见操作

### 查看运行日志
```bash
tail -f ~/train_logs/system.log
```

### 停止程序
```bash
ps aux | grep train_detector
kill <进程ID>
```

### 导出数据到CSV
```bash
sqlite3 -header -csv train_monitoring.db \
  "SELECT * FROM train_events" > events.csv
```

### 清理旧数据
```bash
# 删除30天前的数据
find ~/train_data -type f -mtime +30 -delete
```

## 🐛 故障排查

### 设备连接失败
```bash
# 扫描蓝牙设备
sudo hcitool lescan

# 检查蓝牙服务
sudo systemctl status bluetooth

# 重启蓝牙
sudo systemctl restart bluetooth
```

### 网络上传失败
```bash
# 检查服务器是否运行
ps aux | grep server.py

# 测试连接
curl http://localhost:5000/

# 查看上传日志
grep "上传" ~/train_logs/system.log
```

### 查看详细错误
```bash
# 前台运行查看详细信息
python3 train_detector_network.py system_config.json
```

## 📈 性能优化

### 如果不需要原始数据（节省空间）
```json
"storage": {
  "save_raw_data": false  // 只保存事件摘要
}
```

### 如果网络不稳定
```json
"network": {
  "retry_max_attempts": 5,     // 增加重试次数
  "offline_cache_max_items": 2000  // 增加离线缓存
}
```

## 🌐 部署到云服务器

当老板要求上云时：

1. **买云服务器**，得到公网IP

2. **在云服务器上运行 server.py**
```bash
# 安装依赖
pip3 install flask

# 启动服务器
nohup python3 server.py > server.log 2>&1 &
```

3. **修改树莓派配置**
```json
"network": {
  "server_url": "http://你的服务器IP:5000/api"
}
```

4. **重启树莓派程序**
```bash
kill <进程ID>
python3 train_detector_network.py system_config.json
```

## 📞 技术支持

- 查看日志：`~/train_logs/system.log`
- 数据库位置：`~/train_detection/train_monitoring.db`
- 配置文件：`~/train_detection/system_config.json`

## 📄 License

MIT License

## 👤 Author

Yeyu Pan - PhD Student, University of Auckland
