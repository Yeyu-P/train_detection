# 增量更新说明

## 改动说明

### 只添加了两个功能，保持原有架构不变：

1. **滑动窗口健康监控**
2. **数据上传功能**

## 文件清单

- `witmotion_config.json` - 配置文件（添加了新配置项）
- `witmotion_device_model_clean.py` - 设备模型（添加了滑动窗口）
- `train_detector.py` - 检测系统（添加了上传功能）
- `upload_server.py` - **新增**：数据接收服务器
- `start.sh` - **新增**：快速启动脚本
- `requirements.txt` - 依赖文件（添加了requests和flask）

## 快速开始

### 方法1: 使用启动脚本（推荐）
```bash
chmod +x start.sh
./start.sh
# 选择 3) 同时启动两个
```

### 方法2: 手动启动

**终端1 - 启动数据接收服务器：**
```bash
python3 upload_server.py
```

**终端2 - 启动检测系统：**
```bash
python3 train_detector.py
```

## 上传服务器说明

### upload_server.py
这是一个简单的Flask服务器，用来接收train_detector上传的数据。

**功能：**
- 📥 接收上传的数据（POST /api/data）
- 📊 查看接收到的数据（GET /api/data）
- 💚 健康检查（GET /api/health）
- 🌐 Web界面（http://localhost:8000）

**启动后会显示：**
```
🚀 Starting Data Receiver Server
📡 Listening on: http://localhost:8000
📥 Upload endpoint: http://localhost:8000/api/data
```

**收到数据时会打印：**
```
====================================================
📥 Received data at 2024-12-22 14:30:00
====================================================

📱 Devices: 4

  Device 1: Device_1
    Sliding Window: ✅ Healthy
    Percentage: 15.2%
    Exceeded: 8/50
```

**访问Web界面：**
打开浏览器访问 http://localhost:8000 可以看到：
- 总上传次数
- 最近的上传数据
- API端点列表

## 修改的文件

### 1. witmotion_config.json (配置文件)
添加了两个新配置项：

```json
{
  "devices": [ ... ],  // 设备配置不变
  
  "sliding_window": {
    "enabled": true,           // 是否启用滑动窗口
    "window_size": 50,         // 窗口大小（样本数）
    "threshold": 1.5,          // 阈值(g)
    "trigger_percentage": 70.0 // 触发百分比
  },
  
  "upload": {
    "enabled": true,                              // 是否启用上传
    "url": "http://localhost:8000/api/data",      // 上传地址
    "interval": 60                                // 上传间隔(秒)
  }
}
```

### 2. witmotion_device_model_clean.py
**只添加了：**
- `__init__` 里添加滑动窗口deque
- `processData` 里添加magnitude计算和窗口更新
- 新增 `check_sliding_window()` 方法

**没有改变任何原有逻辑！**

### 3. train_detector.py
**只添加了：**
- IMUDevice 添加 `sliding_status` 属性
- IMUDevice.data_callback 添加滑动窗口状态更新
- TrainDetector 添加 upload 相关属性
- load_config 添加读取 sliding_window 和 upload 配置
- connect_device 添加配置滑动窗口参数
- 新增 `upload_data()` 方法
- run_monitoring 循环里添加 `self.upload_data()` 调用

**没有改变原有连接逻辑！原来怎么连多个设备，现在还是怎么连！**

## 使用方法

### 1. 基础使用（和原来一样）
```bash
python3 train_detector.py
```

### 2. 启用滑动窗口
编辑 `witmotion_config.json`：
```json
"sliding_window": {
  "enabled": true,
  "window_size": 50,
  "threshold": 1.5,
  "trigger_percentage": 70.0
}
```

### 3. 启用数据上传
编辑 `witmotion_config.json`：
```json
"upload": {
  "enabled": true,
  "url": "http://your-server:8000/api/data",
  "interval": 60
}
```

### 4. 禁用新功能（完全恢复原来行为）
```json
"sliding_window": {
  "enabled": false
},
"upload": {
  "enabled": false
}
```

## 滑动窗口说明

### 工作原理
1. 保持最近50个样本（默认，可配置）
2. 计算加速度magnitude = sqrt(AccX² + AccY² + AccZ²)
3. 统计窗口内超过阈值的样本数
4. 如果超过70%（默认）的样本超过1.5g（默认），触发健康警告

### 查看状态
每个设备的 `sliding_status` 包含：
```python
{
  'healthy': True/False,
  'exceeded_count': 12,      # 超过阈值的样本数
  'percentage': 24.0,        # 百分比
  'window_size': 50          # 窗口大小
}
```

## 数据上传说明

### 上传内容
每隔60秒（默认）自动上传一次：
```json
{
  "timestamp": "2024-12-22T14:30:00",
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "sliding_window": {
        "healthy": true,
        "percentage": 15.0
      }
    }
  ]
}
```

### 接收服务器
使用 `upload_server.py` 接收数据：

**启动服务器：**
```bash
python3 upload_server.py
```

**查看接收到的数据：**
- Web界面：http://localhost:8000
- API查询：http://localhost:8000/api/data
- 健康检查：http://localhost:8000/api/health

**数据保存：**
- 所有接收到的数据保存在 `received_data.json`
- 可以用任何JSON查看器打开

### 上传失败处理
- 静默失败，不影响检测
- 不会阻塞主程序
- 超时5秒自动放弃

### 更改上传地址
如果要上传到其他服务器：
```json
"upload": {
  "enabled": true,
  "url": "http://your-server-ip:8000/api/data",
  "interval": 60
}
```

## 依赖变化

新增依赖：
```
requests>=2.28.0  # 用于HTTP上传
flask>=2.0.0      # 用于接收服务器
```

安装：
```bash
pip3 install -r requirements.txt

# 或者单独安装
pip3 install requests flask
```

## 测试建议

1. 先禁用新功能，确认原有功能正常：
```json
"sliding_window": {"enabled": false},
"upload": {"enabled": false}
```

2. 单独测试滑动窗口：
```json
"sliding_window": {"enabled": true},
"upload": {"enabled": false}
```

3. 单独测试上传：
```json
"sliding_window": {"enabled": false},
"upload": {"enabled": true}
```

4. 都启用：
```json
"sliding_window": {"enabled": true},
"upload": {"enabled": true}
```

## 问题排查

### 如果连不上多个设备
**这不应该发生！因为我完全没改连接逻辑！**

但如果真的出现，请：
1. 确认用的是修改后的 `train_detector.py`
2. 检查是否有其他地方的改动
3. 对比原文件：`diff train_detector.py train_detector_backup.py`

### 如果滑动窗口不工作
1. 确认配置里 `"enabled": true`
2. 检查 `device.sliding_status`
3. 查看日志里的 "✅ Sliding window enabled"

### 如果上传失败
1. 检查 `upload.url` 是否正确
2. 确认服务器在运行
3. 上传失败不会影响检测，只是静默跳过

## 总结

这次更新：
- ✅ 只添加了滑动窗口和上传功能
- ✅ 完全保留原有架构
- ✅ 不影响原有连接逻辑
- ✅ 可以随时禁用新功能
- ✅ 向后兼容

**如果不启用新功能，系统行为和原来完全一样！**
