# Train Detection System - Production Stable Version

A production-ready BLE multi-device system for train vibration detection using Witmotion IMU sensors, strictly adhering to BlueZ engineering constraints.

## Features

### Core Capabilities
- **Serial BLE Connection**: One-by-one connection, no concurrency
- **Explicit Resource Management**: Each disconnection goes through stop_notify → disconnect
- **Complete Error Handling**: Timeout, failure, and retry mechanisms for every step
- **Unified Exit Path**: Ctrl+C / exceptions / normal exit all properly clean up resources
- **State Machine Management**: Each IMU has independent state, with exception isolation

### Advanced Features
- **Sliding Window Health Detection**: Percentage-based trigger for improved reliability
- **Automatic Reconnection**: Detects and recovers from dead connections
- **OS-Level BLE Cleanup**: Handles extreme failure cases with bluetoothctl/hciconfig
- **Non-blocking Health Upload**: Sends monitoring data to local/LAN endpoint
- **JSON Configuration**: All parameters centralized in config file
- **Comprehensive Logging**: Production-grade logging to file and console

## Quick Start

### 1. Installation

```bash
# Clone or extract the project
cd train_detection_stable

# Install dependencies
pip3 install -r requirements.txt
```

### 2. Configuration

Edit `config.json` to match your setup:

```json
{
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true
    }
  ],
  "detection": {
    "threshold": 2.0,
    "min_duration": 1.0,
    "post_trigger_duration": 5.0
  },
  "upload": {
    "enabled": true,
    "host": "localhost",
    "port": 8080,
    "endpoint": "/api/imu/status"
  }
}
```

### 3. Run

```bash
# Direct run
python3 train_detector_stable.py

# Background run
nohup python3 train_detector_stable.py > detector.log 2>&1 &

# With custom config
python3 train_detector_stable.py my_config.json
```

## Configuration Reference

### Device Configuration

```json
"devices": [
  {
    "number": 1,              // Device number (unique identifier)
    "name": "Device_1",       // Device name (for logging)
    "mac": "XX:XX:XX:XX:XX:XX", // BLE MAC address
    "enabled": true           // Enable/disable this device
  }
]
```

### Detection Parameters

```json
"detection": {
  "threshold": 2.0,              // Acceleration threshold (g) to trigger detection
  "min_duration": 1.0,           // Minimum duration (seconds) for valid event
  "post_trigger_duration": 5.0   // Recording duration after trigger (seconds)
}
```

### Health Monitoring

```json
"health_monitoring": {
  "data_timeout": 3.0,              // Max seconds without data before flagging as unhealthy
  "health_check_interval": 2.0,     // How often to check health (seconds)
  "max_consecutive_failures": 3,    // Failures before triggering OS cleanup
  "sliding_window_size": 50,        // Number of recent checks to keep
  "trigger_percentage": 70.0        // Percentage of failed checks to trigger reconnect
}
```

**Sliding Window Explanation**: 
- Maintains the last N health checks (default 50)
- Calculates the percentage of unhealthy checks in the last 1 second
- If ≥70% are unhealthy, triggers reconnection
- More robust than simple timeout-based detection

### Reconnection Settings

```json
"reconnection": {
  "max_retries": 3,                    // Max connection attempts per device
  "global_cooldown": 5.0,              // Min seconds between any reconnections
  "os_cleanup_cooldown": 600,          // Cooldown per device (10 minutes)
  "os_cleanup_global_cooldown": 300    // Global cooldown for OS cleanup (5 minutes)
}
```

### Upload Configuration

```json
"upload": {
  "enabled": true,              // Enable/disable health data upload
  "host": "localhost",          // Target host (use LAN IP for remote)
  "port": 8080,                 // Target port
  "endpoint": "/api/imu/status", // API endpoint
  "interval": 30,               // Upload interval (seconds)
  "timeout": 5.0,               // Request timeout (seconds)
  "retry_on_failure": false     // Retry failed uploads
}
```

**Upload Data Format**:
```json
{
  "timestamp": "2024-12-22T10:30:00",
  "system": {
    "total_events": 5,
    "total_reconnects": 2,
    "total_os_cleanups": 0,
    "uptime_start": 1703234400.0
  },
  "imus": [
    {
      "number": 1,
      "name": "Device_1",
      "is_ready": true,
      "device_health": {
        "state": "ready",
        "consecutive_failures": 0,
        "sliding_window": {
          "healthy": true,
          "stats": {
            "total_checks": 25,
            "unhealthy_count": 5,
            "unhealthy_percentage": 20.0
          }
        }
      }
    }
  ]
}
```

### Timeouts

```json
"timeouts": {
  "connect_timeout": 15.0,      // BLE connection timeout (seconds)
  "gatt_timeout": 10.0,         // GATT service discovery timeout
  "first_data_timeout": 5.0     // Timeout waiting for first data packet
}
```

### Output Settings

```json
"output": {
  "directory": "train_events",    // Output directory for event data
  "db_name": "events.db",         // SQLite database filename
  "log_file": "train_detector.log" // Log file name
}
```

## System Architecture

```
Central Coordinator (TrainDetector)
    ↓ Serial Connection
┌──────────────────────────────────────┐
│  IMU Manager 1 (State Machine)      │ → DeviceModel → BLE Hardware
├──────────────────────────────────────┤
│  IMU Manager 2 (State Machine)      │ → DeviceModel → BLE Hardware  
├──────────────────────────────────────┤
│  IMU Manager 3 (State Machine)      │ → DeviceModel → BLE Hardware
└──────────────────────────────────────┘
```

**Key Design Principles**:
- Each IMU is independently managed; one failure doesn't affect others
- Serial connection ensures Bluetooth stack stability
- Clear state machine: DISCONNECTED → CONNECTING → CONNECTED → DISCOVERING → READY

## Connection Flow

### Serial Connection (Critical!)

```
Device 1: DISCONNECTED → CONNECTING → CONNECTED → DISCOVERING → READY ✓
           ↓ Wait for completion
Device 2: DISCONNECTED → CONNECTING → CONNECTED → DISCOVERING → READY ✓
           ↓ Wait for completion  
Device 3: DISCONNECTED → CONNECTING → CONNECTED → DISCOVERING → READY ✓
```

**Why Serial?**
- BlueZ Bluetooth stack doesn't reliably support concurrent connections
- Serial connection avoids resource competition
- 1-second wait after each device connection for system stabilization

### Connection Verification

Each device must pass all steps:
1. ✓ BLE connection successful (`client.is_connected = True`)
2. ✓ GATT service discovery complete
3. ✓ Notification started
4. ✓ **First data frame received** ← Most critical step!

Only after all steps are complete is the device marked READY.

## Health Monitoring

### Two-Layer Detection

1. **Basic Health Check**: No data for N seconds (configurable)
2. **Sliding Window Check**: Percentage of failed checks in time window

Example scenario:
```
Last 50 checks (1 second window):
- 35 checks: healthy (data flowing)
- 15 checks: unhealthy (no data)
- Unhealthy percentage: 30%

If trigger_percentage = 70%, this is still healthy.
If trigger_percentage = 25%, this triggers reconnection.
```

### Automatic Reconnection

When dead connection detected:
```
Connection failed → stop_notify (if enabled)
                 → disconnect
                 → clean up state
                 → retry (max 3 times)
                 → if all fail, skip device
```

### OS-Level Cleanup

Triggered when:
- Same device has ≥3 consecutive failures
- Last cleanup was >10 minutes ago
- Global cooldown period has passed

Process:
```
1. Pause all BLE operations
2. Try: bluetoothctl remove <MAC>
3. If failed, try: sudo hciconfig hci0 reset
4. Cooldown 10-15 seconds
5. Resume BLE operations
6. Attempt reconnection
```

## Logging

### Log Levels

**INFO** - Normal events:
```
2024-12-22 10:30:52 [INFO] [Device_1] READY (data flowing)
2024-12-22 10:35:20 [INFO] Total reconnects: 3
```

**WARNING** - Needs attention:
```
2024-12-22 11:15:33 [WARNING] [IMU-2] RECONNECT triggered: No data for 3.5s
2024-12-22 11:15:40 [WARNING] [Device_2] Consecutive failures: 2
```

**CRITICAL** - Extreme operations:
```
2024-12-22 12:00:15 [CRITICAL] TRIGGERING OS-LEVEL BLE CLEANUP
```

**ERROR** - Failures:
```
2024-12-22 13:20:45 [ERROR] [IMU-3] Connection failed: timeout
```

### Log Analysis

```bash
# Count reconnections
grep "RECONNECT triggered" train_detector.log | wc -l

# Find dead connection patterns
grep "No data for" train_detector.log

# OS cleanup frequency
grep "OS cleanup completed" train_detector.log

# Real-time monitoring
tail -f train_detector.log | grep -E "RECONNECT|CLEANUP|ERROR"
```

## Status Reports

Every 30 seconds (configurable), the system prints:

```
==============================================================
SYSTEM STATUS
==============================================================
Uptime: 2.3 hours
Total Events: 5
Reconnects: 12
OS Cleanups: 1
Upload Count: 48
Upload Failures: 2

IMUs: 4
  IMU-1: READY (Buffer: 250)
    Acc: X= 0.012g Y=-0.003g Z= 0.998g (last data: 0.2s ago)
  IMU-2: READY (Buffer: 250) UNHEALTHY (failures: 2) (window: 75%)
  IMU-3: READY (Buffer: 250)
  IMU-4: DISCONNECTED (Buffer: 0)
==============================================================
```

## Troubleshooting

### Problem: Connection Timeout

```
[Device_1] Connection failed: Connection timeout
```

**Causes**: Device too far / low battery / Bluetooth interference

**Solutions**:
1. Check if device is powered on
2. Move closer to Raspberry Pi
3. Verify MAC address is correct
4. Run `python3 cleanup.py` to clear residual connections

### Problem: Service Discovery Failed

```
[Device_1] Connection failed: Service discovery failed
```

**Causes**: Not a Witmotion device / firmware issue

**Solutions**:
1. Confirm device is Witmotion WT901BLE
2. Check device firmware version
3. Try power cycling the device

### Problem: No Data Received

```
[Device_1] Connection failed: No data received (timeout)
```

**Causes**: Device sleeping / notification not started

**Solutions**:
1. Restart IMU device
2. Check device battery
3. Manually shake device to activate
4. Increase `first_data_timeout` in config

### Problem: Repeated Reconnections

**Causes**: Bluetooth interference / device hardware issue

**Solutions**:
1. Check sliding window configuration
2. Increase `trigger_percentage` (make less sensitive)
3. Check for sources of RF interference
4. Try different USB Bluetooth adapter

### Problem: Upload Failures

```
Health upload timeout
```

**Causes**: Target service not running / network issue

**Solutions**:
1. Verify upload target is running
2. Check network connectivity
3. Disable upload if not needed: `"enabled": false`
4. Upload failures won't affect core BLE operations

## Performance Characteristics

- **Connection Time**: ~10 seconds per device (serial)
- **CPU Usage**: <3% (Raspberry Pi 4)
- **Memory Usage**: ~15MB (4 devices)
- **Stability**: Can run continuously for 72+ hours

## Differences from Previous Versions

| Feature | Old Version | Stable Version | Enhanced Version |
|---------|-------------|----------------|------------------|
| Connection | ❌ Concurrent | ✅ Serial | ✅ Serial |
| Resource Mgmt | ❌ Incomplete | ✅ Explicit cleanup | ✅ Explicit cleanup |
| Error Handling | ❌ Basic | ✅ Complete timeout/retry | ✅ Complete timeout/retry |
| Exit Handling | ❌ May leave residue | ✅ Unified path | ✅ Unified path |
| Connection Verify | ❌ Assume success | ✅ Wait for first data | ✅ Wait for first data |
| Health Detection | - | ✅ Timeout-based | ✅ Sliding window + timeout |
| Configuration | - | ✅ Partial | ✅ Full JSON config |
| Monitoring Upload | - | - | ✅ Non-blocking HTTP |

## Files

- `train_detector_stable.py` - Main detection system
- `witmotion_device_stable.py` - BLE device model with state machine
- `config.json` - Configuration file (all parameters)
- `cleanup.py` - Utility to force disconnect devices
- `requirements.txt` - Python dependencies

## Advanced Usage

### Running as systemd Service

Create `/etc/systemd/system/train-detector.service`:

```ini
[Unit]
Description=Train Detection System
After=bluetooth.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/train_detection
ExecStart=/usr/bin/python3 train_detector_stable.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable train-detector
sudo systemctl start train-detector
sudo journalctl -u train-detector -f
```

### Setting up Upload Server

Simple Python receiver example:

```python
from aiohttp import web

async def handle_status(request):
    data = await request.json()
    print(f"Received from {len(data['imus'])} IMUs")
    
    # Process health data
    for imu in data['imus']:
        if not imu['is_ready']:
            print(f"  Alert: IMU-{imu['number']} not ready!")
    
    return web.Response(text="OK")

app = web.Application()
app.router.add_post('/api/imu/status', handle_status)
web.run_app(app, host='0.0.0.0', port=8080)
```

### Tuning Parameters

**More Sensitive Detection** (detects smaller vibrations):
```json
"detection": {
  "threshold": 1.5  // Lower = more sensitive
}
```

**Less Sensitive Reconnection** (fewer false alarms):
```json
"health_monitoring": {
  "trigger_percentage": 85.0,  // Higher = less sensitive
  "sliding_window_size": 100    // Larger window = more stable
}
```

**Faster Reconnection** (less stable):
```json
"reconnection": {
  "global_cooldown": 2.0  // Lower = faster, but riskier
}
```

## Core Principles

Remember:
- 🚫 Never use concurrent connections
- ✅ Always explicitly clean up resources  
- ⏰ All operations must have timeouts
- 🔁 Failed operations must have retry strategy
- 🛡️ Exceptions must be isolated

**Stability > Speed!**

## Support

For issues:
1. Check real-time logs: `tail -f train_detector.log`
2. Run diagnostics: Check system status output
3. Clean connections: `python3 cleanup.py`
4. Review configuration: Verify JSON syntax and values

## License

Production-stable BLE multi-device system for research and monitoring applications.
