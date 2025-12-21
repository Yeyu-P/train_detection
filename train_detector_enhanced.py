#!/usr/bin/env python3
"""
Train Detection System - Enhanced Backend Service
Multi-device IMU monitoring with threshold-based triggering and circular buffer
Features: Sliding window health check, centralized config, cloud upload
"""
import asyncio
import threading
import time
import os
import csv
import json
import sqlite3
import requests
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from witmotion_device_model_clean import DeviceModel


class CircularBuffer:
    """Circular buffer - maintains last N seconds of data"""
    def __init__(self, max_seconds=5, sample_rate=50):
        self.max_size = max_seconds * sample_rate
        self.buffer = deque(maxlen=self.max_size)
        self.sample_rate = sample_rate
    
    def add(self, timestamp, data):
        """Add data point"""
        self.buffer.append((timestamp, data))
    
    def get_all(self):
        """Get all buffered data"""
        return list(self.buffer)
    
    def clear(self):
        """Clear buffer"""
        self.buffer.clear()
    
    def __len__(self):
        return len(self.buffer)


class SlidingWindow:
    """Sliding window for health monitoring with percentage-based triggering"""
    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.measurements = deque(maxlen=window_size)
    
    def add_measurement(self, exceeded_threshold: bool):
        """Add a boolean measurement (True if threshold exceeded)"""
        self.measurements.append(exceeded_threshold)
    
    def get_exceeded_percentage(self) -> float:
        """Calculate percentage of measurements that exceeded threshold"""
        if not self.measurements:
            return 0.0
        exceeded_count = sum(1 for m in self.measurements if m)
        return (exceeded_count / len(self.measurements)) * 100.0
    
    def is_full(self) -> bool:
        """Check if window is full"""
        return len(self.measurements) >= self.window_size
    
    def clear(self):
        """Clear window"""
        self.measurements.clear()


class IMUDevice:
    """Single IMU device manager with health monitoring"""
    def __init__(self, number, name, mac, callback, config: dict):
        self.number = number
        self.name = name
        self.mac = mac
        self.device = None
        self.connected = False
        self.last_data_time = 0
        self.callback = callback
        
        # Circular buffer (maintains last N seconds)
        buffer_seconds = config.get('detection', {}).get('buffer_max_seconds', 5)
        sample_rate = config.get('detection', {}).get('sample_rate_hz', 50)
        self.buffer = CircularBuffer(max_seconds=buffer_seconds, sample_rate=sample_rate)
        
        # Current data
        self.current_data = {}
        
        # Health monitoring - sliding window
        window_size = config.get('health_check', {}).get('sliding_window_size', 50)
        self.health_window = SlidingWindow(window_size=window_size)
        self.health_check_threshold = config.get('health_check', {}).get('health_check_threshold_g', 15.0)
        
        # Health statistics
        self.health_stats = {
            'total_checks': 0,
            'threshold_exceeded_count': 0,
            'last_exceeded_percentage': 0.0,
            'is_healthy': True
        }
        
        print(f"Initialized Device {number}: {name} ({mac})")
    
    def data_callback(self, device_model: DeviceModel):
        """Device data callback - CORE LOGIC, DO NOT MODIFY"""
        current_time = time.time()
        self.last_data_time = current_time
        
        if not self.connected:
            self.connected = True
            print(f"Device {self.number} connected and streaming data")
        
        device_data = device_model.deviceData.copy()
        self.current_data = device_data
        
        # Add to circular buffer
        self.buffer.add(current_time, device_data)
        
        # Health check (non-blocking, isolated)
        self._update_health_check(device_data)
        
        # Callback to detector
        if self.callback:
            self.callback(self.number, current_time, device_data)
    
    def _update_health_check(self, data: dict):
        """
        Update health monitoring - NON-BLOCKING, ISOLATED
        Failure here must not affect core BLE logic
        """
        try:
            acc_x = data.get('AccX', 0)
            acc_y = data.get('AccY', 0)
            acc_z = data.get('AccZ', 0)
            magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
            
            # Check if exceeds health threshold
            exceeded = magnitude > self.health_check_threshold
            
            # Add to sliding window
            self.health_window.add_measurement(exceeded)
            
            # Update stats
            self.health_stats['total_checks'] += 1
            if exceeded:
                self.health_stats['threshold_exceeded_count'] += 1
            
            # Calculate percentage if window is ready
            if self.health_window.is_full():
                percentage = self.health_window.get_exceeded_percentage()
                self.health_stats['last_exceeded_percentage'] = percentage
        except Exception as e:
            # Isolated exception - log but do not propagate
            print(f"Health check error for Device {self.number}: {e}")
    
    def get_health_status(self) -> dict:
        """Get current health status (for upload)"""
        return {
            'device_number': self.number,
            'device_name': self.name,
            'connected': self.connected,
            'total_checks': self.health_stats['total_checks'],
            'threshold_exceeded_count': self.health_stats['threshold_exceeded_count'],
            'exceeded_percentage': self.health_stats['last_exceeded_percentage'],
            'window_full': self.health_window.is_full(),
            'last_data_time': self.last_data_time
        }
    
    def get_buffer_data(self):
        """Get buffer data"""
        return self.buffer.get_all()
    
    def clear_buffer(self):
        """Clear buffer"""
        self.buffer.clear()


class CloudUploader:
    """Non-blocking cloud uploader for IMU health status"""
    def __init__(self, config: dict):
        self.enabled = config.get('upload', {}).get('enabled', False)
        self.protocol = config.get('upload', {}).get('protocol', 'http')
        self.host = config.get('upload', {}).get('host', 'localhost')
        self.port = config.get('upload', {}).get('port', 8080)
        self.endpoint = config.get('upload', {}).get('endpoint', '/api/imu/status')
        self.timeout = config.get('upload', {}).get('timeout_seconds', 5)
        self.retry_on_failure = config.get('upload', {}).get('retry_on_failure', False)
        
        self.url = f"{self.protocol}://{self.host}:{self.port}{self.endpoint}"
        
        # Upload stats
        self.stats = {
            'total_attempts': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'last_upload_time': None,
            'last_error': None
        }
        
        if self.enabled:
            print(f"Cloud uploader enabled: {self.url}")
        else:
            print("Cloud uploader disabled")
    
    def upload_status(self, devices_status: List[dict]) -> bool:
        """
        Upload device status - NON-BLOCKING, ISOLATED
        Failure here must NOT affect core BLE logic
        """
        if not self.enabled:
            return False
        
        try:
            self.stats['total_attempts'] += 1
            
            payload = {
                'timestamp': datetime.now().isoformat(),
                'devices': devices_status
            }
            
            response = requests.post(
                self.url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                self.stats['successful_uploads'] += 1
                self.stats['last_upload_time'] = time.time()
                print(f"Upload successful: {len(devices_status)} devices")
                return True
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            # Isolated exception - log but do not propagate
            self.stats['failed_uploads'] += 1
            self.stats['last_error'] = str(e)
            print(f"Upload failed: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get upload statistics"""
        return self.stats.copy()


class TrainDetector:
    """Train detector - core logic with enhanced features"""
    def __init__(self, config_file="detector_config.json"):
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Output setup
        output_dir = self.config.get('output', {}).get('directory', 'train_events')
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Detection parameters from config
        detection_config = self.config.get('detection', {})
        self.threshold = detection_config.get('threshold_g', 2.0)
        self.min_duration = detection_config.get('min_duration_seconds', 1.0)
        self.post_trigger_duration = detection_config.get('post_trigger_duration_seconds', 5.0)
        
        # Device management
        self.devices: Dict[int, IMUDevice] = {}
        self.loop = None
        
        # Detection state
        self.detecting = False
        self.recording = False
        self.trigger_time = None
        self.trigger_device = None
        self.event_data = {}
        self.event_id = None
        
        # Database
        db_name = self.config.get('output', {}).get('database_name', 'events.db')
        self.db_path = self.output_dir / db_name
        self.init_database()
        
        # Cloud uploader
        self.uploader = CloudUploader(self.config)
        
        # Upload thread management
        self.upload_thread = None
        self.upload_interval = self.config.get('upload', {}).get('upload_interval_seconds', 30)
        
        # Statistics
        self.stats = {
            'total_events': 0,
            'last_event_time': None,
            'uptime_start': time.time()
        }
        
        print("=" * 60)
        print("Train Detection System - Enhanced")
        print("=" * 60)
        print(f"Config: {config_file}")
        print(f"Output: {output_dir}")
        print(f"Threshold: {self.threshold}g")
        print(f"Min Duration: {self.min_duration}s")
        print(f"Post-trigger: {self.post_trigger_duration}s")
        print(f"Upload enabled: {self.uploader.enabled}")
        print("=" * 60)
    
    def _load_config(self, config_file: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                print(f"Configuration loaded from {config_file}")
                return config
        except FileNotFoundError:
            print(f"Warning: Config file {config_file} not found, using defaults")
            return {}
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return {}
    
    def init_database(self):
        """Initialize SQLite database"""
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
    
    def load_device_config(self):
        """Load device configuration"""
        devices = self.config.get('devices', [])
        enabled = [d for d in devices if d.get('enabled', True)]
        print(f"Loaded {len(enabled)} enabled devices from config")
        return enabled
    
    def device_data_callback(self, device_number, timestamp, data):
        """
        Device data callback - detection logic
        CORE LOGIC - DO NOT MODIFY
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
        
        # If recording, continue collecting data
        if self.recording:
            if device_number not in self.event_data:
                self.event_data[device_number] = []
            self.event_data[device_number].append((timestamp, data.copy()))
            
            # Check if should end recording
            elapsed = timestamp - self.trigger_time
            if elapsed >= self.post_trigger_duration:
                self.end_recording()
    
    def trigger_detection(self, device_number, timestamp, magnitude):
        """Trigger detection event"""
        self.recording = True
        self.trigger_time = timestamp
        self.trigger_device = device_number
        self.event_id = datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')
        self.event_data = {}
        
        print(f"\nTRAIN DETECTED!")
        print(f"   Device: {device_number}")
        print(f"   Time: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Magnitude: {magnitude:.3f}g")
        print(f"   Recording for {self.post_trigger_duration}s...")
        
        # Collect buffer data from all devices (previous 5 seconds)
        for dev_num, device in self.devices.items():
            buffer_data = device.get_buffer_data()
            if buffer_data:
                self.event_data[dev_num] = buffer_data.copy()
                print(f"   Captured {len(buffer_data)} samples from Device {dev_num} buffer")
    
    def end_recording(self):
        """End recording and save data"""
        if not self.recording:
            return
        
        duration = time.time() - self.trigger_time
        print(f"\nSaving event data...")
        print(f"   Duration: {duration:.2f}s")
        
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
            
            print(f"   Saved Device {dev_num}: {len(data_list)} samples")
        
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
        
        # Update statistics
        self.stats['total_events'] += 1
        self.stats['last_event_time'] = self.trigger_time
        
        print(f"   Event saved: {event_dir.name}")
        print(f"   Max acceleration: {max_acc:.3f}g")
        print(f"   Total events: {self.stats['total_events']}\n")
        
        # Reset state
        self.recording = False
        self.event_data = {}
    
    def save_to_database(self, metadata, data_path):
        """Save event to database"""
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
            print(f"   Database save error: {e}")
    
    async def connect_device(self, device):
        """
        Connect single device (async)
        CORE BLE LOGIC - DO NOT MODIFY
        """
        try:
            print(f"Connecting Device {device.number}: {device.mac}...")
            device.device = DeviceModel(device.name, device.mac, device.data_callback)
            await device.device.openDevice()
        except Exception as e:
            print(f"Device {device.number} connection failed: {e}")
            device.connected = False
    
    def setup_async_loop(self):
        """
        Setup async event loop
        CORE BLE LOGIC - DO NOT MODIFY
        """
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        time.sleep(0.2)
        print("Async loop started")
    
    def _upload_worker(self):
        """
        Background worker for periodic uploads
        NON-BLOCKING - runs in separate thread
        """
        while self.detecting:
            try:
                time.sleep(self.upload_interval)
                
                # Collect health status from all devices
                devices_status = []
                for device in self.devices.values():
                    status = device.get_health_status()
                    devices_status.append(status)
                
                # Upload (non-blocking, isolated)
                if devices_status:
                    self.uploader.upload_status(devices_status)
                    
            except Exception as e:
                # Isolated exception - log but continue
                print(f"Upload worker error: {e}")
    
    def start(self):
        """
        Start detection system
        CORE LOGIC - MINIMAL MODIFICATIONS
        """
        # Load device configuration
        config_devices = self.load_device_config()
        if not config_devices:
            print("No devices to connect")
            return False
        
        # Setup async loop
        self.setup_async_loop()
        
        # Create device instances
        for dev_config in config_devices:
            number = dev_config['number']
            name = dev_config['name']
            mac = dev_config['mac']
            
            device = IMUDevice(number, name, mac, self.device_data_callback, self.config)
            self.devices[number] = device
        
        print(f"\nConnecting {len(self.devices)} devices sequentially...")
        print("   (BlueZ limitation: must connect one at a time)")
        
        # Sequential connection (BlueZ limitation)
        async def connect_sequential():
            for device in self.devices.values():
                print(f"\nConnecting Device {device.number}: {device.mac}...")
                try:
                    await self.connect_device(device)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Device {device.number} failed: {e}")
        
        # Submit to event loop and wait
        future = asyncio.run_coroutine_threadsafe(connect_sequential(), self.loop)
        
        print("\nWaiting for sequential connections...")
        try:
            future.result(timeout=30)
        except Exception as e:
            print(f"Connection timeout or error: {e}")
        
        # Check connection status
        connected = [d for d in self.devices.values() if d.connected]
        print(f"\nConnected: {len(connected)}/{len(self.devices)} devices")
        
        if connected:
            for device in connected:
                print(f"   Device {device.number}: {device.name}")
        
        if not connected:
            print("No devices connected!")
            return False
        
        # Start detection
        self.detecting = True
        
        # Start upload worker thread if enabled
        if self.uploader.enabled:
            self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
            self.upload_thread.start()
            print(f"Upload worker started (interval: {self.upload_interval}s)")
        
        print(f"\nDetection started!")
        print(f"   Threshold: {self.threshold}g")
        print(f"   Monitoring {len(connected)} devices...")
        print("   Waiting for train...\n")
        
        return True
    
    def stop(self):
        """Stop detection"""
        print("\nStopping detection...")
        self.detecting = False
        
        # If recording, save first
        if self.recording:
            self.end_recording()
        
        # Close all devices
        for device in self.devices.values():
            if device.device:
                device.device.closeDevice()
        
        # Stop loop
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        print("Detection stopped")
    
    def print_status(self):
        """Print status information"""
        uptime = time.time() - self.stats['uptime_start']
        
        print("\n" + "=" * 60)
        print("SYSTEM STATUS")
        print("=" * 60)
        print(f"Uptime: {uptime/3600:.1f} hours")
        print(f"Total Events: {self.stats['total_events']}")
        
        if self.stats['last_event_time']:
            last_event = datetime.fromtimestamp(self.stats['last_event_time'])
            print(f"Last Event: {last_event.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Upload statistics
        if self.uploader.enabled:
            upload_stats = self.uploader.get_stats()
            print(f"\nUpload Stats:")
            print(f"  Total: {upload_stats['total_attempts']}")
            print(f"  Success: {upload_stats['successful_uploads']}")
            print(f"  Failed: {upload_stats['failed_uploads']}")
        
        print(f"\nDevices: {len(self.devices)}")
        for num, device in sorted(self.devices.items()):
            status = "Connected" if device.connected else "Disconnected"
            buffer_size = len(device.buffer)
            health = device.get_health_status()
            
            print(f"  Device {num}: {status} (Buffer: {buffer_size} samples)")
            print(f"    Health: {health['exceeded_percentage']:.1f}% exceeded "
                  f"(window: {health['window_full']})")
            
            if device.current_data:
                acc = device.current_data
                print(f"    Acc: X={acc.get('AccX', 0):6.3f}g "
                      f"Y={acc.get('AccY', 0):6.3f}g "
                      f"Z={acc.get('AccZ', 0):6.3f}g")
        
        print("=" * 60 + "\n")
    
    def run_monitoring(self):
        """Run monitoring loop"""
        print("Press Ctrl+C to stop\n")
        
        try:
            status_interval = 30
            last_status_time = time.time()
            
            while self.detecting:
                time.sleep(1)
                
                # Periodic status print
                if time.time() - last_status_time >= status_interval:
                    self.print_status()
                    last_status_time = time.time()
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        finally:
            self.stop()


def main():
    """Main function"""
    detector = TrainDetector(config_file="detector_config.json")
    
    # Start detection
    if detector.start():
        detector.run_monitoring()
    else:
        print("Failed to start detection system")


if __name__ == "__main__":
    main()
