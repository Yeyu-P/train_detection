# 完整使用示例

## 场景1: 本地测试（推荐新手）

### 步骤1: 安装依赖
```bash
pip3 install -r requirements.txt
```

### 步骤2: 启动接收服务器
**终端1:**
```bash
python3 upload_server.py
```

你会看到：
```
====================================================
🚀 Starting Data Receiver Server
====================================================
📡 Listening on: http://localhost:8000
📥 Upload endpoint: http://localhost:8000/api/data
====================================================
```

### 步骤3: 启动检测系统
**终端2:**
```bash
python3 train_detector.py
```

### 步骤4: 观察数据上传
在终端1（服务器）你会看到每60秒收到一次数据：
```
====================================================
📥 Received data at 2024-12-22 14:30:00
====================================================

📱 Devices: 4

  Device 1: Device_1
    Sliding Window: ✅ Healthy
    Percentage: 15.2%
    Exceeded: 8/50

  Device 2: Device_2
    Sliding Window: ✅ Healthy
    Percentage: 12.0%
    Exceeded: 6/50
...
```

### 步骤5: 查看Web界面
打开浏览器访问：http://localhost:8000

---

## 场景2: 使用启动脚本（最简单）

```bash
chmod +x start.sh
./start.sh
```

选择：`3) 同时启动两个`

脚本会自动：
1. 后台启动upload_server.py
2. 前台启动train_detector.py
3. Ctrl+C退出时自动清理

---

## 场景3: 树莓派部署

### 树莓派1（数据收集端）
```bash
# 编辑配置，指向服务器IP
nano witmotion_config.json

# 修改upload url:
"upload": {
  "enabled": true,
  "url": "http://192.168.1.100:8000/api/data",  # 服务器IP
  "interval": 60
}

# 启动检测
python3 train_detector.py
```

### 另一台电脑/树莓派（服务器端）
```bash
# 启动接收服务器
python3 upload_server.py
```

---

## 场景4: 禁用上传功能（纯本地）

编辑 `witmotion_config.json`:
```json
{
  "sliding_window": {
    "enabled": true,    // 保留滑动窗口
    ...
  },
  "upload": {
    "enabled": false    // 禁用上传
  }
}
```

这样只有滑动窗口功能，不上传数据。

---

## 场景5: 只用滑动窗口检测异常

### 配置
```json
{
  "sliding_window": {
    "enabled": true,
    "window_size": 50,        // 监控最近50个样本
    "threshold": 1.5,         // 超过1.5g算异常
    "trigger_percentage": 80  // 80%样本异常才报警
  },
  "upload": {
    "enabled": false
  }
}
```

### 运行
```bash
python3 train_detector.py
```

### 观察
晃动IMU时，如果持续震动（>80%样本超过1.5g），会看到：
```
⚠️ Device 1 sliding window health alert!
  Exceeded: 42/50 (84%)
```

---

## 数据查看方式

### 方式1: 实时控制台输出
直接看终端输出：
```
====================================================
📥 Received data at 2024-12-22 14:30:00
====================================================
...
```

### 方式2: Web界面
浏览器打开：http://localhost:8000

看到：
- 总上传次数
- 最近5次上传的完整数据
- 最后上传时间

### 方式3: JSON文件
```bash
cat received_data.json | python3 -m json.tool
```

### 方式4: API查询
```bash
# 获取最近10条数据
curl http://localhost:8000/api/data | python3 -m json.tool

# 健康检查
curl http://localhost:8000/api/health
```

---

## 典型数据示例

### 上传的数据格式
```json
{
  "timestamp": "2024-12-22T14:30:52.123456",
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "sliding_window": {
        "healthy": true,
        "exceeded_count": 8,
        "percentage": 16.0,
        "window_size": 50
      }
    },
    {
      "number": 2,
      "name": "Device_2",
      "sliding_window": {
        "healthy": false,
        "exceeded_count": 42,
        "percentage": 84.0,
        "window_size": 50
      }
    }
  ],
  "stats": {
    "total_events": 5,
    "last_event_time": 1703254200.0,
    "uptime_start": 1703253000.0
  }
}
```

### 解读数据

**Device 1: Healthy**
- `healthy: true` - 健康
- `percentage: 16.0%` - 只有16%的样本超过阈值
- `exceeded_count: 8/50` - 50个样本中有8个超过阈值

**Device 2: Alert!**
- `healthy: false` - 不健康！
- `percentage: 84.0%` - 84%的样本超过阈值（超过70%触发点）
- `exceeded_count: 42/50` - 50个样本中有42个超过阈值
- **说明**: 设备2持续震动，可能：
  - 火车正在通过
  - 安装松动
  - 环境震动过大
  - 设备故障

---

## 常见组合配置

### 配置1: 高灵敏度检测
```json
{
  "sliding_window": {
    "enabled": true,
    "window_size": 50,
    "threshold": 1.2,        // 低阈值
    "trigger_percentage": 60 // 低触发点
  }
}
```
适用于：检测轻微震动

### 配置2: 低误报配置
```json
{
  "sliding_window": {
    "enabled": true,
    "window_size": 100,      // 大窗口
    "threshold": 2.0,        // 高阈值
    "trigger_percentage": 80 // 高触发点
  }
}
```
适用于：避免误报，只检测明显异常

### 配置3: 快速响应
```json
{
  "sliding_window": {
    "enabled": true,
    "window_size": 25,       // 小窗口（0.5秒）
    "threshold": 1.5,
    "trigger_percentage": 70
  },
  "upload": {
    "enabled": true,
    "interval": 10           // 10秒上传一次
  }
}
```
适用于：需要快速检测和频繁上传

---

## 调试技巧

### 技巧1: 查看是否在上传
```bash
# 看upload_server.py的输出
# 应该每60秒看到一次"📥 Received data"
```

### 技巧2: 测试上传功能
```bash
# 手动发送测试数据
curl -X POST http://localhost:8000/api/data \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# 应该收到：{"status": "success", ...}
```

### 技巧3: 查看滑动窗口是否工作
```bash
# 晃动IMU，观察train_detector.py输出
# 应该看到percentage变化
```

### 技巧4: 强制触发滑动窗口警告
```bash
# 修改配置，降低阈值到很低
"sliding_window": {
  "threshold": 0.5,  // 非常低
  "trigger_percentage": 50
}

# 重启后应该立即看到警告
```

---

## 故障排查

### 问题: upload_server.py启动失败
```
Address already in use
```
**解决**: 端口8000被占用
```bash
# 找到并杀死占用进程
lsof -i :8000
kill -9 <PID>

# 或者换个端口
# 修改upload_server.py里的: app.run(port=8001)
```

### 问题: train_detector不上传数据
**检查清单:**
1. upload_server.py 是否在运行？
2. 配置里 `"enabled": true` 了吗？
3. URL正确吗？`http://localhost:8000/api/data`
4. 等了60秒了吗？（默认间隔）

### 问题: 收到数据但没有sliding_window信息
**原因**: 滑动窗口未启用
**解决**:
```json
"sliding_window": {
  "enabled": true  // 确保是true
}
```

---

## 进阶: 自定义接收服务器

如果你想修改接收服务器的行为，编辑 `upload_server.py`:

```python
@app.route('/api/data', methods=['POST'])
def receive_data():
    data = request.get_json()
    
    # 自定义处理
    # 例如：发送邮件、存入数据库、触发报警等
    
    if data['devices'][0]['sliding_window']['percentage'] > 90:
        send_alert_email()  # 你的自定义函数
    
    return jsonify({'status': 'success'}), 200
```

---

## 总结

使用最简单的方式开始：
```bash
./start.sh
# 选择 3
```

然后打开浏览器：http://localhost:8000

就能看到实时数据了！
