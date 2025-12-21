# Migration Guide: Original → Professional Edition

## Overview

This guide helps you migrate from the original Train Detection System to the Professional Edition with minimal disruption.

## What's New

### 1. Sliding Window Health Monitoring
- **Feature**: Monitors recent N samples for percentage-based threshold triggering
- **Use Case**: Detect vibration-heavy environments, validate data quality
- **Configuration**: Fully configurable via `system_config.json`

### 2. Professional Codebase
- **Change**: All Chinese comments replaced with English
- **Change**: Removed emoji decorations from code (kept in output only)
- **Benefit**: Easier for international teams to maintain
- **Benefit**: More professional appearance in production environments

### 3. Cloud Upload Integration
- **Feature**: Automatic upload of health status and event data
- **Configuration**: Mock mode available for testing without real endpoint
- **Benefit**: Remote monitoring and alerting capabilities

### 4. Centralized Configuration
- **Change**: All parameters moved to `system_config.json`
- **Benefit**: Single source of truth for all settings
- **Benefit**: Easy parameter tuning without code changes

## Migration Steps

### Step 1: Backup Existing System

```bash
# Backup everything
cd ~/train_detection_system
tar -czf backup_$(date +%Y%m%d).tar.gz .

# Specifically backup data and config
cp -r train_events train_events_backup
cp witmotion_config.json witmotion_config_backup.json
```

### Step 2: Install Professional Edition

```bash
# Create new directory
cd ~
mkdir train_detection_pro
cd train_detection_pro

# Copy new files
cp /path/to/system_config.json .
cp /path/to/witmotion_device_model_pro.py .
cp /path/to/cloud_uploader.py .
cp /path/to/train_detector_pro.py .
cp /path/to/test_detector_pro.py .

# Make executable
chmod +x train_detector_pro.py
chmod +x test_detector_pro.py
```

### Step 3: Migrate Configuration

The Professional Edition uses a new configuration format. Here's how to convert:

**Original Format (witmotion_config.json):**
```json
{
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true
    }
  ]
}
```

**New Format (system_config.json):**

1. Copy the `devices` array from old config
2. Add to the new config structure:

```json
{
  "detection": { ... },
  "health_check": { ... },
  "buffer": { ... },
  "connection": { ... },
  "cloud_upload": { ... },
  
  "devices": [
    // PASTE YOUR OLD DEVICES ARRAY HERE
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true
    }
  ]
}
```

### Step 4: Transfer Existing Detection Parameters

If you customized parameters in the old `train_detector.py`, transfer them to the new config:

**Old Code (in train_detector.py):**
```python
self.threshold = 2.5              # Your custom value
self.min_duration = 2.0           # Your custom value
self.post_trigger_duration = 8.0  # Your custom value
```

**New Config (in system_config.json):**
```json
{
  "detection": {
    "threshold_g": 2.5,
    "min_duration_seconds": 2.0,
    "post_trigger_duration_seconds": 8.0,
    "sliding_window": {
      "enabled": false  // Disable if you want original behavior
    }
  }
}
```

### Step 5: Install Dependencies

```bash
# Install new dependencies (adds aiohttp)
pip3 install -r requirements_pro.txt
```

### Step 6: Run Tests

```bash
# Test the new system
python3 test_detector_pro.py
```

Expected output:
```
============================================================
TEST 1: Configuration Loading
============================================================
PASS: Configuration loaded successfully
...
Result: 5/5 tests passed
🎉 All tests passed!
```

### Step 7: Test with Single Device

Before running full system, test with one device:

**Edit system_config.json:**
```json
{
  "devices": [
    {
      "number": 1,
      "name": "Device_1",
      "mac": "E3:CA:3A:0D:D6:D0",
      "enabled": true
    },
    {
      "number": 2,
      "name": "Device_2",
      "mac": "CF:3C:37:5F:BC:41",
      "enabled": false  // Temporarily disable
    }
  ]
}
```

**Run:**
```bash
python3 train_detector_pro.py
```

**Verify:**
- Device connects successfully
- Data streaming works
- Detection triggers on shake/vibration
- Data saves correctly

### Step 8: Full Deployment

Once single-device testing succeeds:

1. Enable all devices in config
2. Run full system
3. Monitor for 24 hours
4. Verify event data quality

### Step 9: Update Systemd Service (if applicable)

If you were using systemd:

```bash
# Edit service file
sudo nano /etc/systemd/system/train-detector.service
```

**Update ExecStart line:**
```ini
[Service]
ExecStart=/usr/bin/python3 /home/pi/train_detection_pro/train_detector_pro.py
WorkingDirectory=/home/pi/train_detection_pro
```

**Reload and restart:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart train-detector
sudo systemctl status train-detector
```

## Feature Comparison

| Feature | Original | Professional |
|---------|----------|--------------|
| Multi-device support | ✓ | ✓ |
| Circular buffer | ✓ | ✓ |
| Threshold detection | ✓ | ✓ |
| Sequential connection | ✓ | ✓ (maintained) |
| Sliding window health | ✗ | ✓ (new) |
| Cloud upload | ✗ | ✓ (new) |
| Centralized config | ✗ | ✓ (new) |
| English codebase | Partial | ✓ (complete) |
| Health monitoring | Basic | ✓ (enhanced) |

## Rollback Procedure

If you need to rollback to the original system:

```bash
# Stop new system
pkill -f train_detector_pro.py

# Restore old system
cd ~/train_detection_system
./start.sh
```

## Backward Compatibility

The Professional Edition maintains backward compatibility with:
- ✓ Original data storage format (CSV + JSON + SQLite)
- ✓ Original device configuration (MAC addresses, names)
- ✓ Original P0/P1/P2 fixes (sequential connection, mutex, etc.)

**Breaking Changes:**
- Configuration file format (needs migration)
- Import statements in custom scripts
- Some internal class names

## New Configuration Options

### Minimal Configuration (Original Behavior)

To replicate original behavior exactly:

```json
{
  "detection": {
    "threshold_g": 2.0,
    "min_duration_seconds": 1.0,
    "post_trigger_duration_seconds": 5.0,
    "sliding_window": {
      "enabled": false  // Disable new feature
    }
  },
  "cloud_upload": {
    "enabled": false  // Disable new feature
  },
  "devices": [ /* your devices */ ]
}
```

### Recommended Configuration (New Features)

To take advantage of new features:

```json
{
  "detection": {
    "threshold_g": 2.0,
    "sliding_window": {
      "enabled": true,
      "window_size_samples": 50,
      "trigger_percentage": 70.0,
      "threshold_g": 1.5
    }
  },
  "cloud_upload": {
    "enabled": true,
    "endpoint": "http://localhost:8000/api/health"
  }
}
```

## Validation Checklist

After migration, verify:

- [ ] All devices connect successfully
- [ ] Data streaming at expected rate (50Hz default)
- [ ] Events trigger correctly
- [ ] Data saved in expected format
- [ ] Database accessible
- [ ] Cloud upload working (if enabled)
- [ ] System stable for 24+ hours
- [ ] No memory leaks
- [ ] No connection drops

## Common Migration Issues

### Issue 1: Config Not Found

**Symptom:**
```
WARNING: Config file not found: system_config.json
```

**Solution:**
```bash
# Ensure config file is in working directory
ls -la system_config.json

# Or specify absolute path
python3 train_detector_pro.py --config /full/path/to/system_config.json
```

### Issue 2: Import Errors

**Symptom:**
```
ImportError: No module named 'aiohttp'
```

**Solution:**
```bash
pip3 install aiohttp
# Or install all requirements
pip3 install -r requirements_pro.txt
```

### Issue 3: Old Data Format

**Symptom:** Existing event data not accessible

**Solution:** Both versions use same data format - no migration needed. Just point to old directory:

```bash
# Copy old events to new location
cp -r ~/train_detection_system/train_events ~/train_detection_pro/
```

## Support

If you encounter issues during migration:

1. Review this guide
2. Check test results: `python3 test_detector_pro.py`
3. Verify configuration syntax
4. Test with single device first
5. Review logs for specific errors

## Next Steps After Migration

1. **Tune Thresholds**: Use sliding window data to optimize detection
2. **Enable Cloud Upload**: Set up monitoring endpoint
3. **Update Documentation**: Document your specific configuration
4. **Train Team**: Share new features with operators
5. **Monitor Performance**: Track metrics for 1-2 weeks

---

**Last Updated:** December 2024  
**Migration Version:** 1.0 → 2.0
