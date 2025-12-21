# Train Detection System - Professional Edition

A professional multi-device IMU monitoring system for detecting train passage using threshold-based triggering with circular buffering, sliding window health monitoring, and cloud upload capabilities.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Advanced Features](#advanced-features)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Troubleshooting](#troubleshooting)
- [API Documentation](#api-documentation)

---

## Overview

This system monitors multiple Witmotion IMU (Inertial Measurement Unit) sensors via Bluetooth Low Energy (BLE) to detect train passage events. When acceleration exceeds a configurable threshold, the system captures pre-trigger data (from circular buffers) and post-trigger data, storing comprehensive event information for analysis.

### Key Improvements in Professional Edition

- **Sliding Window Health Monitoring**: Configurable window-based health checks with percentage-based triggering
- **Professional Codebase**: Clean English documentation, modular design, comprehensive error handling
- **Cloud Upload Integration**: Asynchronous health status and event reporting to remote endpoints
- **Maintained P0 Fixes**: Sequential BLE connection, mutex protection, robust state machine
- **Centralized Configuration**: All parameters in a single JSON file for easy tuning

---

## Features

### Core Functionality

- ✅ **Multi-Device Support**: Simultaneously manage 1-4 (or more) IMU devices
- ✅ **Circular Buffering**: Retain last 5 seconds of data for pre-trigger capture
- ✅ **Threshold Detection**: Configurable acceleration threshold triggering
- ✅ **Data Persistence**: CSV format + JSON metadata + SQLite database
- ✅ **Real-time Monitoring**: Live connection status and data stream visualization

### Advanced Features

- ✅ **Sliding Window Health Monitoring**: 
  - Configurable window size (e.g., 50 samples = 1 second at 50Hz)
  - Percentage-based threshold triggering (e.g., alert if >70% of samples exceed 1.5g)
  - Automatic health status reporting

- ✅ **Cloud Integration**:
  - Asynchronous upload of health status
  - Event metadata reporting
  - Configurable retry logic and timeouts
  - Mock mode for local testing

- ✅ **Robust Connection Management**:
  - Sequential device connection (P0 fix for BLE limitations)
  - Automatic reconnection with cooldown
  - Connection state machine with health checks
  - OS-level cleanup integration

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Train Detector Core                       │
│  - Configuration Management                                  │
│  - State Machine (Idle → Monitoring → Recording → Saving)   │
│  - Event Loop Coordination                                   │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼──────┐        ┌──────▼───────┐
│ IMU Device 1 │        │ Cloud Upload │
│ - BLE Conn   │        │ - Async POST │
│ - Buffer     │        │ - Retry Logic│
│ - Health     │        │ - Stats      │
└──────┬───────┘        └──────────────┘
       │
┌──────▼────────┐
│ Device Model  │
│ - BLE Protocol│
│ - Data Parsing│
│ - Sliding Win │
└───────────────┘
```

### Data Flow

1. **BLE Connection**: Sequential device connection via async event loop
2. **Data Stream**: 50Hz IMU data → Device Model → Parse → Callback
3. **Circular Buffer**: Last 5 seconds retained for pre-trigger capture
4. **Sliding Window**: Last N samples monitored for health checks
5. **Detection**: Threshold exceeded → Capture buffer + record for 5s
6. **Storage**: CSV + JSON + SQLite database
7. **Upload**: Async POST to cloud endpoint (optional)

---

## Installation

### Prerequisites

- **Hardware**: Raspberry Pi 3/4 or compatible Linux system
- **OS**: Ubuntu 20.04+ or Raspberry Pi OS
- **Python**: 3.8+
- **Bluetooth**: BlueZ 5.50+

### System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Bluetooth stack
sudo apt install bluetooth bluez libbluetooth-dev -y

# Install Python and pip
sudo apt install python3 python3-pip -y

# Enable Bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

### Python Dependencies

```bash
# Install required packages
pip3 install -r requirements.txt
```

**requirements.txt:**
```
bleak>=0.21.0
aiohttp>=3.8.0
asyncio
```

### Project Setup

```bash
# Clone or extract project
cd ~/
mkdir train_detection_pro
cd train_detection_pro

# Copy files
cp system_config.json .
cp witmotion_device_model_pro.py .
cp cloud_uploader.py .
cp train_detector_pro.py .

# Make executable
chmod +x train_detector_pro.py

# Create output directory
mkdir train_events
```

---

## Configuration

### System Configuration File: `system_config.json`

This file contains all system parameters. Edit as needed:

```json
{
  "detection": {
    "threshold_g": 2.0,                    // Main detection threshold
    "min_duration_seconds": 1.0,           // Minimum event duration
    "post_trigger_duration_seconds": 5.0,  // Post-trigger recording time
    
    "sliding_window": {
      "enabled": true,                     // Enable sliding window health check
      "window_size_samples": 50,           // Window size (50 samples @ 50Hz = 1s)
      "trigger_percentage": 70.0,          // Alert if >70% exceed threshold
      "threshold_g": 1.5                   // Sliding window threshold
    }
  },
  
  "health_check": {
    "enabled": true,
    "first_frame_timeout_seconds": 10.0,   // Max time to receive first frame
    "grace_period_seconds": 5.0,           // Grace period after connection
    "data_stale_timeout_seconds": 3.0,     // Max time between data frames
    "reconnect_cooldown_seconds": 10.0     // Cooldown before reconnection
  },
  
  "buffer": {
    "max_seconds": 5,                      // Circular buffer duration
    "sample_rate_hz": 50                   // Expected sample rate
  },
  
  "connection": {
    "sequential_connection": true,         // P0 fix: prevent concurrent connections
    "connection_timeout_seconds": 30,      // Total connection timeout
    "inter_device_delay_seconds": 1.0,     // Delay between device connections
    "max_retries": 3,                      // Connection retry attempts
    "retry_delay_seconds": 5.0             // Delay between retries
  },
  
  "cloud_upload": {
    "enabled": true,                       // Enable cloud upload
    "endpoint": "http://localhost:8000/api/health",  // Upload endpoint
    "upload_interval_seconds": 60,         // Upload frequency
    "timeout_seconds": 5.0,                // Request timeout
    "retry_attempts": 3,                   // Upload retry attempts
    "include_raw_data": false              // Include raw sensor data
  },
  
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true
    }
    // Add more devices as needed
  ]
}
```

### Configuration Tuning Guide

#### Detection Sensitivity

- **High Sensitivity** (detect light vibrations):
  - `threshold_g`: 1.5
  - `min_duration_seconds`: 0.5
  
- **Normal Sensitivity** (typical trains):
  - `threshold_g`: 2.0
  - `min_duration_seconds`: 1.0
  
- **Low Sensitivity** (heavy trains only):
  - `threshold_g`: 3.0
  - `min_duration_seconds`: 2.0

#### Sliding Window Health Monitoring

- **Aggressive** (detect potential issues early):
  - `window_size_samples`: 50 (1 second at 50Hz)
  - `trigger_percentage`: 60.0
  - `threshold_g`: 1.2
  
- **Balanced** (recommended):
  - `window_size_samples`: 50
  - `trigger_percentage`: 70.0
  - `threshold_g`: 1.5
  
- **Conservative** (avoid false alerts):
  - `window_size_samples`: 100 (2 seconds)
  - `trigger_percentage`: 80.0
  - `threshold_g`: 2.0

---

## Usage

### Quick Start

```bash
# Run with default configuration
python3 train_detector_pro.py
```

### Command Line Options

```bash
# Specify custom config file
python3 train_detector_pro.py --config custom_config.json

# Specify custom output directory
python3 train_detector_pro.py --output custom_events/
```

### Background Execution

```bash
# Run in background with nohup
nohup python3 train_detector_pro.py > detector.log 2>&1 &

# View logs
tail -f detector.log

# Stop background process
pkill -f train_detector_pro.py
```

### Systemd Service (Production)

Create service file:

```bash
sudo nano /etc/systemd/system/train-detector.service
```

```ini
[Unit]
Description=Train Detection System Professional Edition
After=bluetooth.target network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/train_detection_pro
ExecStart=/usr/bin/python3 /home/pi/train_detection_pro/train_detector_pro.py
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

# View status
sudo systemctl status train-detector

# View logs
sudo journalctl -u train-detector -f
```

---

## Advanced Features

### Sliding Window Health Monitoring

The sliding window monitors the most recent N samples (configurable) and triggers an alert if a threshold percentage of samples exceed a specified acceleration value.

**Use Cases:**
- Detect vibration-heavy environments
- Identify malfunctioning sensors
- Monitor mounting stability
- Validate data quality

**Example Configuration:**
```json
"sliding_window": {
  "enabled": true,
  "window_size_samples": 50,      // 1 second at 50Hz
  "trigger_percentage": 70.0,     // Alert if >70% exceed threshold
  "threshold_g": 1.5              // Threshold for individual samples
}
```

**Interpretation:**
- If 35+ out of 50 recent samples exceed 1.5g → Health alert triggered
- Useful for detecting constant vibration vs. transient train events

### Cloud Upload Integration

Automatically uploads health status and event metadata to a remote endpoint.

**Supported Upload Types:**
1. **Health Status** (periodic):
   - Device connection state
   - Health check results
   - Sliding window statistics
   - Timestamp and device info

2. **Event Metadata** (on detection):
   - Event ID and timestamp
   - Trigger device and magnitude
   - Duration and device count
   - Max acceleration

**Mock Mode for Testing:**

The system includes a `MockCloudUploader` that simulates uploads without requiring a real endpoint:

```python
# In train_detector_pro.py
if cloud_config.get('enabled', False):
    # Use mock uploader for localhost testing
    self.uploader = MockCloudUploader(cloud_config, success_rate=0.95)
```

**Setting Up Real Endpoint:**

Replace `MockCloudUploader` with `CloudUploader` and configure endpoint:

```json
"cloud_upload": {
  "enabled": true,
  "endpoint": "http://your-server.com:8000/api/health",
  "upload_interval_seconds": 60,
  "timeout_seconds": 5.0,
  "retry_attempts": 3
}
```

**Payload Format:**

```json
{
  "timestamp": "2024-12-22T14:30:00",
  "device": {
    "number": 1,
    "name": "Device_1",
    "mac_address": "E3:CA:3A:0D:D6:D0"
  },
  "health_status": {
    "is_healthy": true,
    "first_frame_received": true,
    "last_valid_time": 1703254200.0
  },
  "sliding_window": {
    "healthy": true,
    "exceeded_count": 12,
    "percentage": 24.0,
    "window_size": 50
  }
}
```

---

## Monitoring and Maintenance

### Real-time Status

The system prints status every 30 seconds showing:
- Uptime
- Total events detected
- Connection success rate
- Per-device status (connection, health, buffer size)
- Sliding window status
- Cloud upload statistics

```
============================================================
SYSTEM STATUS
============================================================
Uptime: 2.3 hours
Total Events: 15
Connection Success Rate: 100.0%
Last Event: 2024-12-22 14:30:52

Devices: 4
  Device 1: Connected, Healthy (Buffer: 250 samples)
    Sliding Window: OK (12.0%)
    Acc: X= 0.012g Y= 0.005g Z= 0.998g
  Device 2: Connected, Healthy (Buffer: 250 samples)
    Sliding Window: OK (8.0%)
    Acc: X= 0.008g Y=-0.003g Z= 1.002g

Cloud Upload:
  Success rate: 98.5%
  Last upload: 2024-12-22T14:35:00
============================================================
```

### Data Storage

Events are stored in multiple formats:

```
train_events/
├── events.db                    # SQLite database
├── event_20241222_143052/
│   ├── device_1.csv            # Device 1 raw data
│   ├── device_2.csv            # Device 2 raw data
│   ├── device_3.csv            # Device 3 raw data
│   ├── device_4.csv            # Device 4 raw data
│   └── metadata.json           # Event metadata
```

**CSV Format:**
```csv
timestamp,AccX,AccY,AccZ,AngX,AngY,AngZ,AsX,AsY,AsZ
2024-12-22 14:30:52.123456,0.123,0.456,0.789,1.2,3.4,5.6,7.8,9.0,1.2
```

**Metadata JSON:**
```json
{
  "event_id": "20241222_143052",
  "trigger_device": 1,
  "trigger_time": "2024-12-22T14:30:52",
  "duration": 10.5,
  "threshold": 2.0,
  "max_acceleration": 3.456,
  "num_devices": 4,
  "devices": [1, 2, 3, 4]
}
```

### Database Queries

```bash
# View all events
sqlite3 train_events/events.db "SELECT * FROM events;"

# Count events
sqlite3 train_events/events.db "SELECT COUNT(*) FROM events;"

# Events in last 24 hours
sqlite3 train_events/events.db "
  SELECT event_id, start_time, max_acceleration 
  FROM events 
  WHERE start_time > strftime('%s', 'now', '-1 day');"

# Average max acceleration
sqlite3 train_events/events.db "
  SELECT AVG(max_acceleration) FROM events;"
```

### Log Analysis

```bash
# View recent errors
grep "ERROR" detector.log | tail -20

# View connection issues
grep "connection" detector.log -i

# View health alerts
grep "HEALTH ALERT" detector.log

# Count detections
grep "TRAIN DETECTED" detector.log | wc -l
```

---

## Troubleshooting

### Common Issues

#### 1. BLE Connection Failures

**Symptoms:**
```
Device 1 connection failed: [Errno 19] No such device
```

**Solutions:**

A. Check Bluetooth status:
```bash
sudo systemctl status bluetooth
sudo bluetoothctl power on
```

B. Verify MAC addresses:
```bash
sudo bluetoothctl
> scan on
> devices
> scan off
> exit
```

C. Use cleanup script:
```bash
python3 cleanup.py  # From original project
```

D. Restart Bluetooth:
```bash
sudo systemctl restart bluetooth
sleep 5
```

#### 2. Stale Connection Issues

**Symptoms:**
```
Device 1 connection failed: timeout
HEALTH ALERT: Device 1 - Data stale (5.2s)
```

**Solutions:**

A. Increase timeouts in config:
```json
"health_check": {
  "first_frame_timeout_seconds": 15.0,
  "data_stale_timeout_seconds": 5.0
}
```

B. Check device power and proximity

C. Reduce interference (move away from WiFi routers, etc.)

#### 3. False Triggers

**Symptoms:**
```
TRAIN DETECTED! (frequent, no train present)
```

**Solutions:**

A. Increase detection threshold:
```json
"detection": {
  "threshold_g": 3.0,
  "min_duration_seconds": 2.0
}
```

B. Improve sensor mounting (reduce ambient vibration)

C. Enable sliding window to filter noise:
```json
"sliding_window": {
  "enabled": true,
  "threshold_g": 2.0,
  "trigger_percentage": 80.0
}
```

#### 4. Sliding Window Alerts

**Symptoms:**
```
WARNING: Device 1 sliding window health alert
  Exceeded threshold: 75.0% (trigger at 70%)
```

**Interpretation:**
- High constant vibration environment
- Potential sensor mounting issue
- May need threshold adjustment

**Solutions:**

A. Adjust sliding window parameters:
```json
"sliding_window": {
  "trigger_percentage": 85.0,  // More tolerant
  "threshold_g": 2.0            // Higher threshold
}
```

B. Check physical mounting

C. Review environment for vibration sources

#### 5. Cloud Upload Failures

**Symptoms:**
```
Cloud Upload Statistics:
  Success rate: 45.0%
```

**Solutions:**

A. Check endpoint accessibility:
```bash
curl -X POST http://localhost:8000/api/health -d '{"test": true}'
```

B. Increase timeout:
```json
"cloud_upload": {
  "timeout_seconds": 10.0,
  "retry_attempts": 5
}
```

C. Verify network connectivity

---

## API Documentation

### CloudUploader API

#### `upload_health_status(device_number, device_name, mac_address, health_data, sliding_window_status)`

Upload device health status to cloud endpoint.

**Parameters:**
- `device_number` (int): Device identifier
- `device_name` (str): Device name
- `mac_address` (str): BLE MAC address
- `health_data` (dict): Health check results
- `sliding_window_status` (dict): Sliding window analysis

**Returns:**
- `bool`: Upload success status

**Example:**
```python
await uploader.upload_health_status(
    device_number=1,
    device_name="Device_1",
    mac_address="E3:CA:3A:0D:D6:D0",
    health_data={
        'is_healthy': True,
        'first_frame_received': True
    },
    sliding_window_status={
        'healthy': True,
        'percentage': 15.0
    }
)
```

#### `upload_event_data(event_id, event_metadata)`

Upload train detection event metadata.

**Parameters:**
- `event_id` (str): Event identifier
- `event_metadata` (dict): Event metadata dictionary

**Returns:**
- `bool`: Upload success status

**Example:**
```python
await uploader.upload_event_data(
    event_id="20241222_143052",
    event_metadata={
        'trigger_device': 1,
        'max_acceleration': 3.456,
        'duration': 10.5
    }
)
```

### DeviceModel API

#### `configure_sliding_window(enabled, size, threshold, trigger_percentage)`

Configure sliding window health monitoring parameters.

**Parameters:**
- `enabled` (bool): Enable sliding window
- `size` (int): Number of samples in window
- `threshold` (float): Acceleration threshold (g)
- `trigger_percentage` (float): Trigger percentage (0-100)

**Example:**
```python
device.configure_sliding_window(
    enabled=True,
    size=50,
    threshold=1.5,
    trigger_percentage=70.0
)
```

#### `check_sliding_window_health()`

Check current sliding window health status.

**Returns:**
- `dict`: Health status with keys:
  - `healthy` (bool)
  - `exceeded_count` (int)
  - `percentage` (float)
  - `threshold` (float)
  - `window_size` (int)

---

## Upgrade and Maintenance Guide

### Version Migration

When upgrading from the original version:

1. **Backup existing data:**
```bash
cp -r train_events train_events_backup
cp witmotion_config.json witmotion_config_backup.json
```

2. **Create new configuration:**
```bash
# Merge old config into new format
python3 migrate_config.py witmotion_config.json system_config.json
```

3. **Test with single device first:**
```json
"devices": [
  {
    "number": 1,
    "name": "Device_1",
    "mac": "E3:CA:3A:0D:D6:D0",
    "enabled": true
  }
]
```

4. **Validate functionality:**
```bash
python3 test_detector_pro.py
```

### Performance Optimization

**For Raspberry Pi Zero/1/2:**
```json
"buffer": {
  "max_seconds": 3,        // Reduce memory
  "sample_rate_hz": 20     // Lower CPU load
}
```

**For Raspberry Pi 3/4:**
```json
"buffer": {
  "max_seconds": 5,
  "sample_rate_hz": 50     // Full performance
}
```

### Regular Maintenance

1. **Weekly:**
   - Check system status
   - Review detection logs
   - Verify disk space

2. **Monthly:**
   - Archive old events
   - Update configuration based on false positive/negative rate
   - Check cloud upload success rate

3. **Quarterly:**
   - Update system packages
   - Recalibrate sensors if needed
   - Review and optimize thresholds

---

## Contributing

When modifying the codebase:

1. Maintain professional English comments
2. Keep P0/P1/P2 fixes intact (sequential connection, mutex, state machine)
3. Update `system_config.json` with new parameters
4. Add unit tests for new features
5. Update this README with changes

---

## License

[Your License Here]

---

## Support

For issues or questions:
- Review troubleshooting section
- Check system logs
- Verify configuration parameters
- Test with single device first

---

**Last Updated:** December 2024  
**Version:** 2.0.0 Professional Edition
