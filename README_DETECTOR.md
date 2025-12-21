# Train Detector - 后端检测系统

火车通过检测系统 - 多设备IMU监控，基于阈值触发，带循环缓冲区

## 📋 功能特性

- ✅ **多设备支持**: 同时管理多个IMU设备
- ✅ **循环缓冲区**: 始终保持最近5秒的数据
- ✅ **智能触发**: 阈值检测，自动记录前5秒+后5秒
- ✅ **蓝牙连接**: 基于已有的Witmotion设备模型
- ✅ **数据保存**: CSV格式 + JSON元数据 + SQLite数据库
- ✅ **状态监控**: 实时显示连接状态和数据流

## 🚀 快速开始

### 1. 配置设备

编辑 `witmotion_config.json`:

```json
{
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "AB35487E-B200-B802-E526-C512EA064361",
      "enabled": true
    },
    {
      "number": 2,
      "name": "Device_2",
      "mac": "DB2124E5-ED94-BFB1-FC33-452B097ABA8E",
      "enabled": true
    }
  ]
}
```

### 2. 运行测试

```bash
# 测试所有功能
python3 test_detector.py

# 或单独测试
python3 test_detector.py connection  # 连接测试
python3 test_detector.py buffer      # 缓冲区测试
python3 test_detector.py detection   # 检测测试
```

### 3. 启动检测系统

```bash
python3 train_detector.py
```

## 🔧 系统架构

```
IMU设备 → 蓝牙连接 → 循环缓冲区(5s) → 阈值检测
                                      ↓
                              触发时保存数据
                                      ↓
                     前5秒(buffer) + 后5秒(实时)
                                      ↓
                              保存为CSV + 元数据
```

## 📊 数据存储结构

```
train_events/
├── events.db                    # SQLite数据库
├── event_20241218_143052/
│   ├── device_1.csv            # 设备1原始数据
│   ├── device_2.csv            # 设备2原始数据
│   ├── device_3.csv            # 设备3原始数据
│   └── metadata.json           # 事件元数据
└── event_20241218_150234/
    └── ...
```

### CSV格式

```csv
timestamp,AccX,AccY,AccZ,AngX,AngY,AngZ,AsX,AsY,AsZ
2024-12-18 14:30:52.123456,0.123,0.456,0.789,1.2,3.4,5.6,7.8,9.0,1.2
```

### 元数据格式

```json
{
  "event_id": "20241218_143052",
  "trigger_device": 1,
  "trigger_time": "2024-12-18T14:30:52",
  "duration": 10.5,
  "threshold": 2.0,
  "max_acceleration": 3.456,
  "num_devices": 3,
  "devices": [1, 2, 3]
}
```

## ⚙️ 参数配置

在 `train_detector.py` 中的 `TrainDetector.__init__()`:

```python
self.threshold = 2.0              # 触发阈值 (g)
self.min_duration = 1.0           # 最短持续时间 (秒)
self.post_trigger_duration = 5.0  # 触发后记录时间 (秒)
```

## 🧪 测试说明

### Test 1: Connection Test
- 验证蓝牙连接
- 检查数据流
- 显示实时加速度

### Test 2: Buffer Test
- 验证循环缓冲区
- 检查数据填充率
- 确认5秒缓冲工作正常

### Test 3: Detection Test
- 手动触发检测（晃动设备）
- 验证触发逻辑
- 检查数据保存

## 📝 使用场景

### 场景1: 调试模式
```bash
# 降低阈值，便于测试
python3 test_detector.py detection
```

### 场景2: 长期运行
```bash
# 后台运行
nohup python3 train_detector.py > detector.log 2>&1 &

# 查看日志
tail -f detector.log
```

### 场景3: 系统服务（树莓派）
```bash
# 后续会提供systemd配置
sudo systemctl start train-detector
sudo systemctl enable train-detector
```

## 🔍 监控输出

### 正常运行
```
🎯 Detection started!
   Threshold: 2.0g
   Monitoring 3 devices...
   Waiting for train...
```

### 检测到火车
```
🔔 TRAIN DETECTED!
   Device: 1
   Time: 2024-12-18 14:30:52
   Magnitude: 3.456g
   Recording for 5.0s...
   ✓ Captured 250 samples from Device 1 buffer
   ✓ Captured 250 samples from Device 2 buffer
   ✓ Captured 250 samples from Device 3 buffer
```

### 保存完成
```
💾 Saving event data...
   Duration: 10.52s
   ✓ Saved Device 1: 526 samples
   ✓ Saved Device 2: 526 samples
   ✓ Saved Device 3: 526 samples
   ✅ Event saved: event_20241218_143052
   Max acceleration: 3.456g
   Total events: 1
```

## 🐛 故障排查

### 问题1: 设备连接失败
```
❌ Device 1 connection failed: [Errno 19] No such device
```
**解决**:
- 检查MAC地址是否正确
- 确认设备已开机且在范围内
- 检查蓝牙是否启用: `bluetoothctl power on`

### 问题2: 第二次运行连不上（连接残留）
```
❌ Device 1 connection failed: timeout
```
**原因**: 上次程序没有正确断开，设备还在连接状态

**解决方案1 - 使用清理脚本（推荐）**:
```bash
python3 cleanup.py
# 选择选项1或3，断开所有设备
```

**解决方案2 - 重启蓝牙**:
```bash
sudo systemctl restart bluetooth
# 等待5秒
```

**解决方案3 - 手动断开**:
```bash
sudo bluetoothctl
> disconnect E3:CA:3A:0D:D6:D0
> disconnect CF:3C:37:5F:BC:41
> disconnect E6:1F:C4:87:81:74
> disconnect EB:68:B5:C1:60:1C
> exit
```

**解决方案4 - 重启IMU设备**:
- 关闭设备电源
- 等待5秒
- 重新开机

### 问题3: 没有数据流
```
Connected: 1/3 | Dev1: 0.000g (无变化)
```
**解决**:
- 设备可能处于睡眠模式
- 尝试重启设备
- 检查设备频率设置

### 问题4: 误触发太多
```
🔔 TRAIN DETECTED! (频繁触发)
```
**解决**:
- 提高阈值: `detector.threshold = 3.0`
- 增加最短持续时间: `detector.min_duration = 2.0`

## 📈 性能特性

- **采样率**: 50Hz (可配置)
- **缓冲区**: 5秒 × 50Hz = 250样本/设备
- **内存占用**: ~10MB (3设备)
- **CPU占用**: <5% (树莓派4)
- **存储**: ~50KB/事件 (3设备，10秒)

## 🔜 下一步

1. ✅ 验证连接和检测功能
2. ⏳ 开发Web API和Dashboard
3. ⏳ 添加4G上传功能
4. ⏳ 部署为systemd服务

## 💡 提示

- 首次运行建议先跑测试脚本
- 观察实时加速度值来调整阈值
- 可以用 `Ctrl+C` 安全停止
- 数据库可以用SQLite Browser查看

## 📞 需要帮助？

如果遇到问题：
1. 检查 `detector.log` 日志
2. 运行测试脚本诊断
3. 检查设备电量和蓝牙连接
