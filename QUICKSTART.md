# Quick Start Guide

## Installation

```bash
# Extract files
tar -xzf train_detection_system_v4_professional.tar.gz
cd train_detection_system_v4_professional

# Install dependencies
pip3 install -r requirements.txt
```

## Configuration

Edit `train_detection_config.json` to set your device MAC addresses:

```json
{
  "devices": [
    {"number": 1, "mac": "E3:CA:3A:0D:D6:D0", "enabled": true}
  ]
}
```

## Run

### Option 1: Direct Run

```bash
python3 train_detector.py
```

### Option 2: With Mock Cloud Server

Terminal 1:
```bash
python3 mock_server.py
```

Terminal 2:
```bash
python3 train_detector.py
```

### Option 3: Background Mode

```bash
nohup python3 train_detector.py > detector.log 2>&1 &
tail -f detector.log
```

## Key Parameters

In `train_detection_config.json`:

- `threshold`: 2.0 (acceleration threshold in g)
- `trigger_ratio`: 0.7 (70% of samples must exceed threshold)
- `window_duration`: 1.0 (detection window in seconds)
- `post_trigger_duration`: 5.0 (record after trigger in seconds)
- `pre_buffer_duration`: 5.0 (buffer before trigger in seconds)

## Detection Logic

**Sliding Window Trigger**: In a 1-second window (50 samples at 50Hz), if 70% of samples exceed 2.0g, the system triggers and records:
- 5 seconds before trigger (from buffer)
- 5 seconds after trigger
- Total: 10 seconds per event

## Data Location

- Local: `train_events/`
- Database: `train_events/events.db`
- Cloud: `cloud_uploads/` (if using mock server)

## View Data

```bash
# List events
ls -lh train_events/

# View database
sqlite3 train_events/events.db "SELECT * FROM events;"

# View latest event
ls -lt train_events/ | head -5
```

## Troubleshooting

```bash
# Check Bluetooth
sudo systemctl status bluetooth

# Scan devices
sudo bluetoothctl
> scan on

# View logs
tail -f detector.log
```

For more details, see README.md
