#!/usr/bin/env python3
"""
Train Detection System - Professional Edition
Multi-device IMU monitoring with threshold-based triggering and circular buffering

Features:
- Sliding window health monitoring with configurable thresholds
- Professional English codebase with comprehensive documentation
- Cloud upload integration for health status reporting
- Maintained P0/P1/P2 risk mitigation (sequential connection, mutex, state machine)
"""
import asyncio
import threading
import time
import os
import csv
import json
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from witmotion_device_model_pro import DeviceModel
from cloud_uploader import CloudUploader, MockCloudUploader


class CircularBuffer:
    """
    Circular buffer maintaining most recent N seconds of data
    Thread-safe with automatic overflow handling
    """
    def __init__(self, max_seconds=5, sample_rate=50):
        """
        Initialize circular buffer
        
        Args:
            max_seconds: Duration of data to retain
            sample_rate: Expected samples per second
        """
        self.max_size = max_seconds * sample_rate
        self.buffer = deque(maxlen=self.max_size)
        self.sample_rate = sample_rate
    
    def add(self, timestamp, data):
        """Add data point to buffer"""
        self.buffer.append((timestamp, data))
    
    def get_all(self):
        """Get all buffered data"""
        return list(self.buffer)
    
    def clear(self):
        """Clear buffer"""
        self.buffer.clear()
    
    def __len__(self):
        return len(self.buffer)


class IMUDevice:
    """
    Individual IMU device manager
    Handles connection, data buffering, and health monitoring
    """
    def __init__(self, number, name, mac, callback, config):
        """
        Initialize IMU device
        
        Args:
            number: Device number identifier
            name: Device name
            mac: BLE MAC address
            callback: Data callback function
            config: System configuration dictionary
        """
        self.number = number
        self.name = name
        self.mac = mac
        self.device = None
        self.connected = False
        self.last_data_time = 0
        self.callback = callback
        self.config = config
        
        # Circular buffer (retains most recent N seconds)
        buffer_config = config.get('buffer', {})
        self.buffer = CircularBuffer(
            max_seconds=buffer_config.get('max_seconds', 5),
            sample_rate=buffer_config.get('sample_rate_hz', 50)
        )
        
        # Current data snapshot
        self.current_data = {}
        
        # Health monitoring state
        self.health_status = {
            'first_frame_received': False,
            'first_frame_time': None,
            'last_valid_time': None,
            'is_healthy': False,
            'failure_reason': None
        }
        
        # Sliding window status
        self.sliding_window_status = {
            'healthy': True,
            'exceeded_count': 0,
            'percentage': 0.0,
            'last_check_time': None
        }
        
        print(f"Initialized Device {number}: {name} ({mac})")
    
    def data_callback(self, device_model: DeviceModel):
        """
        Device data callback - invoked on each data frame
        
        Args:
            device_model: DeviceModel instance with current data
        """
        current_time = time.time()
        self.last_data_time = current_time
        
        # Mark first frame received
        if not self.health_status['first_frame_received']:
            self.health_status['first_frame_received'] = True
            self.health_status['first_frame_time'] = current_time
            self.health_status['is_healthy'] = True
            print(f"Device {self.number}: First frame received")
        
        if not self.connected:
            self.connected = True
            print(f"Device {self.number}: Connected and streaming")
        
        # Update health timestamp
        self.health_status['last_valid_time'] = current_time
        
        # Copy device data
        device_data = device_model.deviceData.copy()
        self.current_data = device_data
        
        # Add to circular buffer
        self.buffer.add(current_time, device_data)
        
        # Update sliding window health status
        if hasattr(device_model, 'check_sliding_window_health'):
            self.sliding_window_status = device_model.check_sliding_window_health()
            self.sliding_window_status['last_check_time'] = current_time
            
            # Log if sliding window detects issues
            if not self.sliding_window_status.get('healthy', True):
                print(f"WARNING: Device {self.number} sliding window health alert")
                print(f"  Exceeded threshold: {self.sliding_window_status['percentage']:.1f}% "
                      f"(trigger at {self.sliding_window_status.get('trigger_percentage', 70)}%)")
        
        # Callback to detector
        if self.callback:
            self.callback(self.number, current_time, device_data)
    
    def check_health(self, timeout_config):
        """
        Check device health based on data freshness
        
        Args:
            timeout_config: Health check configuration
            
        Returns:
            bool: Health status
        """
        current_time = time.time()
        
        # Check if first frame timeout exceeded
        if not self.health_status['first_frame_received']:
            if current_time - self.health_status.get('first_frame_time', current_time) > \
               timeout_config.get('first_frame_timeout_seconds', 10):
                self.health_status['is_healthy'] = False
                self.health_status['failure_reason'] = "First frame timeout"
                return False
        
        # Check if data is stale
        if self.health_status['last_valid_time']:
            time_since_data = current_time - self.health_status['last_valid_time']
            if time_since_data > timeout_config.get('data_stale_timeout_seconds', 3):
                self.health_status['is_healthy'] = False
                self.health_status['failure_reason'] = f"Data stale ({time_since_data:.1f}s)"
                return False
        
        self.health_status['is_healthy'] = True
        self.health_status['failure_reason'] = None
        return True
    
    def get_buffer_data(self):
        """Get buffered data"""
        return self.buffer.get_all()
    
    def clear_buffer(self):
        """Clear buffer"""
        self.buffer.clear()


class TrainDetector:
    """
    Core train detection system
    Manages multiple IMU devices, threshold detection, and data persistence
    """
    def __init__(self, config_file="system_config.json", output_dir="train_events"):
        """
        Initialize train detector
        
        Args:
            config_file: Path to configuration JSON
            output_dir: Directory for event data storage
        """
        self.config_file = config_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Load configuration
        self.config = self._load_config()
        
        # Detection parameters from config
        detection_config = self.config.get('detection', {})
        self.threshold = detection_config.get('threshold_g', 2.0)
        self.min_duration = detection_config.get('min_duration_seconds', 1.0)
        self.post_trigger_duration = detection_config.get('post_trigger_duration_seconds', 5.0)
        
        # Sliding window configuration
        self.sliding_window_config = detection_config.get('sliding_window', {})
        
        # Device management
        self.devices = {}  # number -> IMUDevice
        self.loop = None
        self.connection_mutex = asyncio.Lock()  # P0 fix: Prevent concurrent connections
        
        # Detection state machine
        self.detecting = False
        self.recording = False
        self.trigger_time = None
        self.trigger_device = None
        self.event_data = {}  # device_number -> [(timestamp, data), ...]
        self.event_id = None
        
        # Database
        self.db_path = self.output_dir / "events.db"
        self.init_database()
        
        # Cloud uploader
        cloud_config = self.config.get('cloud_upload', {})
        if cloud_config.get('enabled', False):
            # Use mock uploader for localhost testing
            self.uploader = MockCloudUploader(cloud_config, success_rate=0.95)
        else:
            self.uploader = None
        
        # Statistics
        self.stats = {
            'total_events': 0,
            'last_event_time': None,
            'uptime_start': time.time(),
            'connection_attempts': 0,
            'connection_failures': 0
        }
        
        self._print_system_info()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        if not os.path.exists(self.config_file):
            print(f"WARNING: Config file not found: {self.config_file}")
            print("Using default configuration")
            return self._get_default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                print(f"Configuration loaded from {self.config_file}")
                return config
        except Exception as e:
            print(f"ERROR: Failed to load config: {e}")
            print("Using default configuration")
            return self._get_default_config()
    
    def _get_default_config(self):
        """Get default configuration"""
        return {
            'detection': {
                'threshold_g': 2.0,
                'min_duration_seconds': 1.0,
                'post_trigger_duration_seconds': 5.0,
                'sliding_window': {
                    'enabled': False,
                    'window_size_samples': 50,
                    'trigger_percentage': 70.0,
                    'threshold_g': 1.5
                }
            },
            'health_check': {
                'enabled': True,
                'first_frame_timeout_seconds': 10.0,
                'grace_period_seconds': 5.0,
                'data_stale_timeout_seconds': 3.0
            },
            'buffer': {
                'max_seconds': 5,
                'sample_rate_hz': 50
            },
            'cloud_upload': {
                'enabled': False
            },
            'devices': []
        }
    
    def _print_system_info(self):
        """Print system initialization information"""
        print("=" * 60)
        print("Train Detection System - Professional Edition")
        print("=" * 60)
        print(f"Configuration: {self.config_file}")
        print(f"Output Directory: {self.output_dir}")
        print(f"Detection Threshold: {self.threshold}g")
        print(f"Min Duration: {self.min_duration}s")
        print(f"Post-trigger Duration: {self.post_trigger_duration}s")
        
        if self.sliding_window_config.get('enabled', False):
            print(f"\nSliding Window Monitoring:")
            print(f"  Window Size: {self.sliding_window_config.get('window_size_samples', 50)} samples")
            print(f"  Threshold: {self.sliding_window_config.get('threshold_g', 1.5)}g")
            print(f"  Trigger Percentage: {self.sliding_window_config.get('trigger_percentage', 70)}%")
        
        if self.uploader:
            print(f"\nCloud Upload: Enabled")
            print(f"  Endpoint: {self.uploader.endpoint}")
        
        print("=" * 60)
    
    def init_database(self):
        """Initialize SQLite database for event storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                start_time REAL,
                end_time REAL,
                duration REAL,
                trigger_device INTEGER,
                max_acceleration REAL,
                num_devices INTEGER,
                data_path TEXT,
                created_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_path}")
    
    def device_data_callback(self, device_number, timestamp, data):
        """
        Device data callback - detection logic
        
        Args:
            device_number: Device identifier
            timestamp: Data timestamp
            data: Sensor data dictionary
        """
        if not self.detecting:
            return
        
        # Calculate acceleration magnitude
        acc_x = data.get('AccX', 0)
        acc_y = data.get('AccY', 0)
        acc_z = data.get('AccZ', 0)
        magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
        
        # Check for trigger
        if not self.recording and magnitude > self.threshold:
            self.trigger_detection(device_number, timestamp, magnitude)
        
        # Continue recording if active
        if self.recording:
            if device_number not in self.event_data:
                self.event_data[device_number] = []
            self.event_data[device_number].append((timestamp, data.copy()))
            
            # Check if recording should end
            elapsed = timestamp - self.trigger_time
            if elapsed >= self.post_trigger_duration:
                asyncio.create_task(self.end_recording())
    
    def trigger_detection(self, device_number, timestamp, magnitude):
        """
        Trigger detection event
        
        Args:
            device_number: Triggering device
            timestamp: Trigger timestamp
            magnitude: Acceleration magnitude
        """
        self.recording = True
        self.trigger_time = timestamp
        self.trigger_device = device_number
        self.event_id = datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')
        self.event_data = {}
        
        print(f"\nTRAIN DETECTED!")
        print(f"  Device: {device_number}")
        print(f"  Time: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Magnitude: {magnitude:.3f}g")
        print(f"  Recording for {self.post_trigger_duration}s...")
        
        # Collect buffer data from all devices (pre-trigger data)
        for dev_num, device in self.devices.items():
            buffer_data = device.get_buffer_data()
            if buffer_data:
                self.event_data[dev_num] = buffer_data.copy()
                print(f"  Captured {len(buffer_data)} samples from Device {dev_num} buffer")
    
    async def end_recording(self):
        """End recording and save event data"""
        if not self.recording:
            return
        
        duration = time.time() - self.trigger_time
        print(f"\nSaving event data...")
        print(f"  Duration: {duration:.2f}s")
        
        # Create event directory
        event_dir = self.output_dir / f"event_{self.event_id}"
        event_dir.mkdir(exist_ok=True)
        
        # Save each device's data
        max_acc = 0
        for dev_num, data_list in self.event_data.items():
            if not data_list:
                continue
            
            csv_path = event_dir / f"device_{dev_num}.csv"
            
            with open(csv_path, 'w', newline='') as f:
                fieldnames = ['timestamp', 'AccX', 'AccY', 'AccZ', 
                            'AngX', 'AngY', 'AngZ', 'AsX', 'AsY', 'AsZ']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for ts, data in data_list:
                    row = {
                        'timestamp': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f'),
                        'AccX': data.get('AccX', ''),
                        'AccY': data.get('AccY', ''),
                        'AccZ': data.get('AccZ', ''),
                        'AngX': data.get('AngX', ''),
                        'AngY': data.get('AngY', ''),
                        'AngZ': data.get('AngZ', ''),
                        'AsX': data.get('AsX', ''),
                        'AsY': data.get('AsY', ''),
                        'AsZ': data.get('AsZ', '')
                    }
                    writer.writerow(row)
                    
                    # Calculate max acceleration
                    acc = (data.get('AccX', 0)**2 + 
                          data.get('AccY', 0)**2 + 
                          data.get('AccZ', 0)**2)**0.5
                    max_acc = max(max_acc, acc)
            
            print(f"  Saved Device {dev_num}: {len(data_list)} samples")
        
        # Save metadata
        metadata = {
            'event_id': self.event_id,
            'trigger_device': self.trigger_device,
            'trigger_time': datetime.fromtimestamp(self.trigger_time).isoformat(),
            'duration': duration,
            'threshold': self.threshold,
            'max_acceleration': max_acc,
            'num_devices': len(self.event_data),
            'devices': list(self.event_data.keys())
        }
        
        with open(event_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save to database
        self.save_to_database(metadata, str(event_dir))
        
        # Upload to cloud if enabled
        if self.uploader:
            await self.uploader.upload_event_data(self.event_id, metadata)
        
        # Update statistics
        self.stats['total_events'] += 1
        self.stats['last_event_time'] = self.trigger_time
        
        print(f"  Event saved: {event_dir.name}")
        print(f"  Max acceleration: {max_acc:.3f}g")
        print(f"  Total events: {self.stats['total_events']}\n")
        
        # Reset state
        self.recording = False
        self.event_data = {}
    
    def save_to_database(self, metadata, data_path):
        """
        Save event to database
        
        Args:
            metadata: Event metadata dictionary
            data_path: Path to event data directory
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metadata['event_id'],
                self.trigger_time,
                self.trigger_time + metadata['duration'],
                metadata['duration'],
                metadata['trigger_device'],
                metadata['max_acceleration'],
                metadata['num_devices'],
                data_path,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  Database save error: {e}")
    
    async def connect_device(self, device):
        """
        Connect individual device (async)
        P0 Fix: Sequential connection with mutex
        
        Args:
            device: IMUDevice instance
        """
        async with self.connection_mutex:  # P0: Prevent concurrent connections
            try:
                print(f"Connecting Device {device.number}: {device.mac}...")
                self.stats['connection_attempts'] += 1
                
                # Create device model
                device.device = DeviceModel(device.name, device.mac, device.data_callback)
                
                # Configure sliding window if enabled
                if self.sliding_window_config.get('enabled', False):
                    device.device.configure_sliding_window(
                        enabled=True,
                        size=self.sliding_window_config.get('window_size_samples', 50),
                        threshold=self.sliding_window_config.get('threshold_g', 1.5),
                        trigger_percentage=self.sliding_window_config.get('trigger_percentage', 70.0)
                    )
                
                # Open device connection
                await device.device.openDevice()
                
            except Exception as e:
                print(f"Device {device.number} connection failed: {e}")
                device.connected = False
                self.stats['connection_failures'] += 1
    
    def setup_async_loop(self):
        """Setup async event loop in separate thread"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        time.sleep(0.2)
        print("Async loop started")
    
    def start(self):
        """
        Start detection system
        P0 Fix: Sequential connection maintained
        
        Returns:
            bool: Success status
        """
        # Load device configuration
        config_devices = self.config.get('devices', [])
        enabled_devices = [d for d in config_devices if d.get('enabled', True)]
        
        if not enabled_devices:
            print("No enabled devices in configuration")
            return False
        
        # Setup async loop
        self.setup_async_loop()
        
        # Create device instances
        for dev_config in enabled_devices:
            number = dev_config['number']
            name = dev_config['name']
            mac = dev_config['mac']
            
            device = IMUDevice(number, name, mac, self.device_data_callback, self.config)
            self.devices[number] = device
        
        print(f"\nConnecting {len(self.devices)} devices sequentially...")
        print("(Sequential connection prevents BLE conflicts)")
        
        # Sequential connection (P0 fix maintained)
        async def connect_sequential():
            for device in self.devices.values():
                await self.connect_device(device)
                await asyncio.sleep(1)  # Stabilization delay
        
        # Submit to event loop and wait
        future = asyncio.run_coroutine_threadsafe(connect_sequential(), self.loop)
        
        print("\nWaiting for connections...")
        try:
            connection_timeout = self.config.get('connection', {}).get('connection_timeout_seconds', 30)
            future.result(timeout=connection_timeout)
        except Exception as e:
            print(f"Connection timeout or error: {e}")
        
        # Check connection status
        connected = [d for d in self.devices.values() if d.connected]
        print(f"\nConnected: {len(connected)}/{len(self.devices)} devices")
        
        if connected:
            for device in connected:
                print(f"  Device {device.number}: {device.name}")
        
        if not connected:
            print("No devices connected!")
            return False
        
        # Start detection
        self.detecting = True
        print(f"\nDetection started!")
        print(f"  Threshold: {self.threshold}g")
        print(f"  Monitoring {len(connected)} devices...")
        print("  Waiting for train...\n")
        
        # Start health monitoring and cloud upload tasks
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._health_monitor_loop(), self.loop)
            if self.uploader:
                asyncio.run_coroutine_threadsafe(self._cloud_upload_loop(), self.loop)
        
        return True
    
    async def _health_monitor_loop(self):
        """
        Background health monitoring loop
        Checks device health and triggers alerts
        """
        health_config = self.config.get('health_check', {})
        if not health_config.get('enabled', True):
            return
        
        while self.detecting:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            for device in self.devices.values():
                if device.connected:
                    is_healthy = device.check_health(health_config)
                    if not is_healthy:
                        print(f"HEALTH ALERT: Device {device.number} - {device.health_status['failure_reason']}")
    
    async def _cloud_upload_loop(self):
        """
        Background cloud upload loop
        Periodically uploads health status
        """
        if not self.uploader:
            return
        
        upload_interval = self.uploader.upload_interval
        
        while self.detecting:
            await asyncio.sleep(upload_interval)
            
            # Upload health status for all devices
            for device in self.devices.values():
                if device.connected:
                    await self.uploader.upload_health_status(
                        device_number=device.number,
                        device_name=device.name,
                        mac_address=device.mac,
                        health_data=device.health_status,
                        sliding_window_status=device.sliding_window_status
                    )
    
    def stop(self):
        """Stop detection system"""
        print("\nStopping detection...")
        self.detecting = False
        
        # Save any active recording
        if self.recording:
            asyncio.run_coroutine_threadsafe(self.end_recording(), self.loop)
            time.sleep(1)
        
        # Close all devices
        for device in self.devices.values():
            if device.device:
                device.device.closeDevice()
        
        # Stop async loop
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        print("Detection stopped")
        
        # Print final statistics
        if self.uploader:
            print("\nCloud Upload Statistics:")
            stats = self.uploader.get_stats()
            print(f"  Total uploads: {stats['total_uploads']}")
            print(f"  Success rate: {stats['success_rate']:.1f}%")
    
    def print_status(self):
        """Print system status"""
        uptime = time.time() - self.stats['uptime_start']
        
        print("\n" + "=" * 60)
        print("SYSTEM STATUS")
        print("=" * 60)
        print(f"Uptime: {uptime/3600:.1f} hours")
        print(f"Total Events: {self.stats['total_events']}")
        print(f"Connection Success Rate: {self._calc_connection_success_rate():.1f}%")
        
        if self.stats['last_event_time']:
            last_event = datetime.fromtimestamp(self.stats['last_event_time'])
            print(f"Last Event: {last_event.strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\nDevices: {len(self.devices)}")
        for num, device in sorted(self.devices.items()):
            status = "Connected" if device.connected else "Disconnected"
            buffer_size = len(device.buffer)
            health = "Healthy" if device.health_status.get('is_healthy', False) else "Unhealthy"
            
            print(f"  Device {num}: {status}, {health} (Buffer: {buffer_size} samples)")
            
            # Show sliding window status
            if device.sliding_window_status.get('last_check_time'):
                sw_health = "OK" if device.sliding_window_status.get('healthy', True) else "ALERT"
                print(f"    Sliding Window: {sw_health} ({device.sliding_window_status.get('percentage', 0):.1f}%)")
            
            if device.current_data:
                acc = device.current_data
                print(f"    Acc: X={acc.get('AccX', 0):6.3f}g "
                      f"Y={acc.get('AccY', 0):6.3f}g "
                      f"Z={acc.get('AccZ', 0):6.3f}g")
        
        if self.uploader:
            print("\nCloud Upload:")
            stats = self.uploader.get_stats()
            print(f"  Success rate: {stats['success_rate']:.1f}%")
            print(f"  Last upload: {stats.get('last_upload_time', 'Never')}")
        
        print("=" * 60 + "\n")
    
    def _calc_connection_success_rate(self):
        """Calculate connection success rate"""
        if self.stats['connection_attempts'] == 0:
            return 100.0
        successful = self.stats['connection_attempts'] - self.stats['connection_failures']
        return (successful / self.stats['connection_attempts']) * 100
    
    def run_monitoring(self):
        """Run monitoring loop with periodic status updates"""
        print("Press Ctrl+C to stop\n")
        
        try:
            status_interval = 30  # Print status every 30 seconds
            last_status_time = time.time()
            
            while self.detecting:
                time.sleep(1)
                
                # Periodic status output
                if time.time() - last_status_time >= status_interval:
                    self.print_status()
                    last_status_time = time.time()
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        finally:
            self.stop()


def main():
    """Main entry point"""
    detector = TrainDetector(
        config_file="system_config.json",
        output_dir="train_events"
    )
    
    # Start detection
    if detector.start():
        detector.run_monitoring()
    else:
        print("Failed to start detection system")


if __name__ == "__main__":
    main()
