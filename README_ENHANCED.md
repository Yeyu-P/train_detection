# Train Detection System - Enhanced

A multi-device IMU monitoring system for train detection with threshold-based triggering, circular buffering, health monitoring, and cloud upload capabilities.

## Features

- **Multi-device Support**: Simultaneous management of multiple IMU devices via Bluetooth Low Energy (BLE)
- **Circular Buffer**: Maintains last N seconds of data (configurable, default 5 seconds)
- **Smart Triggering**: Threshold-based detection with automatic recording of pre-trigger and post-trigger data
- **Health Monitoring**: Sliding window-based health checks with percentage thresholds
- **Cloud Upload**: Non-blocking upload of device health status to local/remote endpoints
- **Centralized Configuration**: All parameters managed through JSON configuration
- **Data Persistence**: CSV format + JSON metadata + SQLite database

## System Architecture

```
IMU Devices → BLE Connection → Circular Buffer (5s) → Threshold Detection
                                      ↓
                              Health Monitoring (Sliding Window)
                                      ↓
                              Trigger on Threshold Exceeded
                                      ↓
                     Pre-trigger (buffer) + Post-trigger (real-time)
                                      ↓
                              Save to CSV + Metadata + Database
                                      ↓
                              Upload Status (Non-blocking)
```

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip3 install -r requirements.txt

# Verify Bluetooth is enabled
sudo systemctl status bluetooth
```

### 2. Configuration

Edit `detector_config.json` to configure your setup:

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
    "threshold_g": 2.0,
    "min_duration_seconds": 1.0,
    "post_trigger_duration_seconds": 5.0
  },
  "health_check": {
    "sliding_window_size": 50,
    "threshold_percentage": 70,
    "health_check_threshold_g": 15.0
  },
  "upload": {
    "enabled": true,
    "host": "localhost",
    "port": 8080,
    "endpoint": "/api/imu/status"
  }
}
```

### 3. Run the System

```bash
# Foreground (see real-time output)
python3 train_detector_enhanced.py

# Background
nohup python3 train_detector_enhanced.py > detector.log 2>&1 &

# View logs
tail -f detector.log
```

## Configuration Reference

### Device Configuration

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `number` | int | Device number (unique identifier) | Required |
| `name` | string | Device friendly name | Required |
| `mac` | string | Bluetooth MAC address | Required |
| `enabled` | bool | Enable/disable device | true |

### Detection Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `threshold_g` | float | Acceleration threshold in g-forces | 2.0 |
| `min_duration_seconds` | float | Minimum duration for valid detection | 1.0 |
| `post_trigger_duration_seconds` | float | Recording duration after trigger | 5.0 |
| `buffer_max_seconds` | int | Circular buffer size in seconds | 5 |
| `sample_rate_hz` | int | Expected sample rate | 50 |

### Health Check Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `sliding_window_size` | int | Number of measurements in sliding window | 50 |
| `threshold_percentage` | float | Percentage threshold for health alert | 70 |
| `health_check_threshold_g` | float | Acceleration threshold for health check | 15.0 |
| `health_check_interval_seconds` | int | Interval between health checks | 5 |

**How Sliding Window Works**:
- System maintains last N measurements (default: 50)
- Each measurement records if acceleration exceeded health threshold
- If ≥70% of measurements in window exceed threshold → health alert
- Example: In 50 measurements, if 35+ exceeded 15.0g → potential issue

### Upload Configuration

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `enabled` | bool | Enable cloud upload | false |
| `protocol` | string | HTTP protocol (http/https) | http |
| `host` | string | Upload endpoint host | localhost |
| `port` | int | Upload endpoint port | 8080 |
| `endpoint` | string | API endpoint path | /api/imu/status |
| `upload_interval_seconds` | int | Upload frequency | 30 |
| `timeout_seconds` | int | Request timeout | 5 |
| `retry_on_failure` | bool | Retry on failure | false |

**Upload Payload Format**:
```json
{
  "timestamp": "2024-12-22T14:30:00",
  "devices": [
    {
      "device_number": 1,
      "device_name": "Device_1",
      "connected": true,
      "total_checks": 150,
      "threshold_exceeded_count": 5,
      "exceeded_percentage": 3.3,
      "window_full": true,
      "last_data_time": 1703257800.123
    }
  ]
}
```

### Output Configuration

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `directory` | string | Output directory for events | train_events |
| `database_name` | string | SQLite database filename | events.db |

### Logging Configuration

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `log_file` | string | Log file path | detector.log |
| `log_level` | string | Logging level | INFO |
| `console_output` | bool | Print to console | true |

## Data Storage

### Directory Structure

```
train_events/
├── events.db                    # SQLite database
├── event_20241218_143052/
│   ├── device_1.csv            # Device 1 raw data
│   ├── device_2.csv            # Device 2 raw data
│   ├── device_3.csv            # Device 3 raw data
│   └── metadata.json           # Event metadata
└── event_20241218_150234/
    └── ...
```

### CSV Format

```csv
timestamp,AccX,AccY,AccZ,AngX,AngY,AngZ,AsX,AsY,AsZ
2024-12-18 14:30:52.123456,0.123,0.456,0.789,1.2,3.4,5.6,7.8,9.0,1.2
```

### Metadata Format

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

## System Status Output

Example status display:

```
============================================================
SYSTEM STATUS
============================================================
Uptime: 2.5 hours
Total Events: 3
Last Event: 2024-12-18 14:30:52

Upload Stats:
  Total: 300
  Success: 295
  Failed: 5

Devices: 4
  Device 1: Connected (Buffer: 250 samples)
    Health: 2.3% exceeded (window: True)
    Acc: X= 0.012g Y= 0.034g Z= 0.998g
  Device 2: Connected (Buffer: 250 samples)
    Health: 1.8% exceeded (window: True)
    Acc: X=-0.008g Y= 0.021g Z= 1.002g
============================================================
```

## Troubleshooting

### Connection Issues

**Problem**: Devices won't connect
```bash
# Check Bluetooth status
sudo systemctl status bluetooth

# Restart Bluetooth
sudo systemctl restart bluetooth

# Scan for devices
sudo bluetoothctl
> scan on
> devices
```

**Problem**: Second run fails (stale connections)
```bash
# Use cleanup script
python3 cleanup.py

# Or manually disconnect
sudo bluetoothctl
> disconnect MAC_ADDRESS
```

### Configuration Issues

**Problem**: Config file not found
- Ensure `detector_config.json` is in the same directory as the script
- Check file permissions: `chmod 644 detector_config.json`

### Upload Issues

**Problem**: Upload failures
- Verify upload endpoint is reachable: `curl http://localhost:8080/api/imu/status`
- Check firewall rules
- Review upload stats in system status
- Set `enabled: false` to disable uploads if not needed

### Performance Issues

**Problem**: High CPU usage
- Reduce sample rate in device configuration
- Decrease buffer size: `buffer_max_seconds: 3`
- Disable uploads if not needed

**Problem**: Memory issues
- Reduce sliding window size: `sliding_window_size: 30`
- Decrease buffer duration

## Advanced Usage

### Running as System Service

Create `/etc/systemd/system/train-detector.service`:

```ini
[Unit]
Description=Train Detection System
After=bluetooth.target network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/train_detection
ExecStart=/usr/bin/python3 /home/pi/train_detection/train_detector_enhanced.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable train-detector
sudo systemctl start train-detector
sudo systemctl status train-detector
```

### Custom Upload Endpoint

Example Flask endpoint to receive uploads:

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/imu/status', methods=['POST'])
def receive_status():
    data = request.json
    print(f"Received status from {len(data['devices'])} devices")
    # Process data here
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Data Analysis

Query events from database:

```bash
sqlite3 train_events/events.db

# View all events
SELECT * FROM events;

# Recent events
SELECT event_id, trigger_time, max_acceleration 
FROM events 
ORDER BY start_time DESC 
LIMIT 10;

# Events by device
SELECT trigger_device, COUNT(*) 
FROM events 
GROUP BY trigger_device;
```

## Performance Characteristics

- **Sample Rate**: 50 Hz (configurable)
- **Buffer Size**: 5 seconds × 50 Hz = 250 samples/device
- **Memory Usage**: ~10 MB (3 devices)
- **CPU Usage**: <5% (Raspberry Pi 4)
- **Storage**: ~50 KB/event (3 devices, 10 seconds)
- **Upload Overhead**: <1% (non-blocking, isolated)

## Architecture Notes

### Core Principles

1. **Non-blocking Design**: Upload and health monitoring do not block BLE operations
2. **Exception Isolation**: Upload failures cannot affect core detection logic
3. **Sequential BLE Connection**: Due to BlueZ limitations, devices connect one at a time
4. **Thread Safety**: Upload worker runs in separate thread with proper isolation

### Critical Sections (Do Not Modify)

- `device_data_callback()`: Core data callback from BLE devices
- `connect_device()`: BLE connection logic
- `setup_async_loop()`: Async event loop setup
- Sequential connection logic in `start()`

### Safe to Modify

- Detection parameters (in config)
- Health check parameters (in config)
- Upload endpoint configuration
- Logging configuration
- Status display format

## Support

For issues or questions:
1. Check logs: `tail -f detector.log`
2. Run connection test: `python3 test_detector.py`
3. Review this documentation
4. Check device battery levels and Bluetooth connectivity

## License

This project is provided as-is for train detection applications.
