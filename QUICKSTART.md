# Quick Start Guide - Enhanced Train Detector

## Installation (5 minutes)

### 1. Upload Files
```bash
# Copy all files to your Raspberry Pi
scp -r enhanced_detector/ pi@raspberrypi.local:~/train_detection/
```

### 2. Install Dependencies
```bash
ssh pi@raspberrypi.local
cd ~/train_detection

# Install Python dependencies
pip3 install -r requirements_enhanced.txt

# Enable Bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

### 3. Configure Devices
```bash
# Edit configuration file
nano detector_config.json

# Update MAC addresses for your devices
# Set enabled: true/false for each device
```

### 4. Run Tests
```bash
# Run all tests
python3 test_detector_enhanced.py

# Or run specific test
python3 test_detector_enhanced.py connection
python3 test_detector_enhanced.py health
```

### 5. Start Detection
```bash
# Foreground (see output)
python3 train_detector_enhanced.py

# Background
nohup python3 train_detector_enhanced.py > detector.log 2>&1 &

# Check logs
tail -f detector.log
```

## Configuration Checklist

- [ ] Update device MAC addresses in `detector_config.json`
- [ ] Set detection threshold (default: 2.0g)
- [ ] Configure health monitoring window (default: 50 samples)
- [ ] Set health threshold percentage (default: 70%)
- [ ] Enable/disable cloud upload
- [ ] Configure upload endpoint (if enabled)

## Common Commands

```bash
# View configuration
cat detector_config.json

# Test connection only
python3 test_detector_enhanced.py connection

# View real-time logs
tail -f detector.log

# Check Bluetooth
sudo systemctl status bluetooth

# Scan for devices
sudo bluetoothctl
> scan on

# Stop background process
pkill -f train_detector_enhanced.py

# View events database
sqlite3 train_events/events.db "SELECT * FROM events;"
```

## Optional: Upload Endpoint Setup

### Start Test Server (on same or different device)
```bash
# On upload endpoint device
python3 upload_server.py

# Server will run on http://0.0.0.0:8080
```

### Configure Detector
```json
{
  "upload": {
    "enabled": true,
    "host": "localhost",  // or "192.168.1.100" for network
    "port": 8080,
    "endpoint": "/api/imu/status"
  }
}
```

### Test Upload
```bash
# Test endpoint connectivity
python3 test_detector_enhanced.py upload
```

## Parameter Tuning Guide

### Adjust Detection Sensitivity
```json
{
  "detection": {
    "threshold_g": 1.5    // Lower = more sensitive
  }
}
```

### Adjust Health Monitoring
```json
{
  "health_check": {
    "sliding_window_size": 50,        // Number of samples
    "threshold_percentage": 70,       // Alert at 70% exceeded
    "health_check_threshold_g": 15.0  // Threshold for health
  }
}
```

### Optimize Performance
```json
{
  "detection": {
    "buffer_max_seconds": 3,    // Reduce for low memory
    "sample_rate_hz": 30        // Reduce for low CPU
  }
}
```

## Troubleshooting Quick Fixes

### Problem: Can't connect to devices
```bash
# Restart Bluetooth
sudo systemctl restart bluetooth
sleep 5

# Run cleanup
python3 cleanup.py
```

### Problem: High memory usage
```json
// Reduce buffer size in detector_config.json
{
  "detection": {
    "buffer_max_seconds": 3
  },
  "health_check": {
    "sliding_window_size": 30
  }
}
```

### Problem: Upload failing
```json
// Disable uploads temporarily
{
  "upload": {
    "enabled": false
  }
}
```

## Next Steps

1. ✅ Complete initial setup and testing
2. ⏳ Collect real train data
3. ⏳ Optimize thresholds based on data
4. ⏳ Set up as system service for auto-start
5. ⏳ Configure remote upload endpoint

## Support

- View logs: `tail -f detector.log`
- Run tests: `python3 test_detector_enhanced.py`
- Check README: `README_ENHANCED.md`
