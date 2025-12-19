#!/usr/bin/env python3
"""
Train Detection System
Real-time IMU-based train detection with cloud upload capability
"""

import asyncio
import json
import os
import csv
import sqlite3
import time
import signal
import threading
import queue
import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional
import requests

from witmotion_device_model_clean import DeviceModel


class DeviceManager:
    """Manages a single IMU device and its data buffering"""
    
    def __init__(self, number: int, name: str, mac: str, sampling_rate: int, buffer_duration: float):
        self.number = number
        self.name = name
        self.mac = mac
        self.device = None
        self.connected = False
        self.data_flowing = False
        self.last_data_time = 0
        
        self.buffer_size = int(sampling_rate * buffer_duration)
        self.data_queue = queue.Queue(maxsize=1000)
        self.circular_buffer = deque(maxlen=self.buffer_size)
        
        self.recording = False
        self.csv_file = None
        self.csv_writer = None
        
        self.logger = logging.getLogger(f"Device_{number}")
    
    def data_callback(self, device_model: DeviceModel):
        """Callback for incoming device data"""
        current_time = time.time()
        self.last_data_time = current_time
        self.data_flowing = True
        
        device_data = device_model.deviceData
        if device_data:
            try:
                self.data_queue.put_nowait((current_time, device_data))
            except queue.Full:
                try:
                    self.data_queue.get_nowait()
                    self.data_queue.put_nowait((current_time, device_data))
                except queue.Empty:
                    pass
    
    def process_data(self) -> List[tuple]:
        """Process queued data and update circular buffer"""
        processed = []
        count = 0
        
        while not self.data_queue.empty() and count < 10:
            try:
                timestamp, data = self.data_queue.get_nowait()
                self.circular_buffer.append((timestamp, data))
                processed.append((timestamp, data))
                
                if self.recording and self.csv_writer:
                    self._write_csv_row(timestamp, data)
                
                count += 1
            except queue.Empty:
                break
        
        return processed
    
    def start_recording(self, output_dir: str, event_id: str) -> str:
        """Start CSV recording"""
        filename = f"device_{self.number}.csv"
        filepath = os.path.join(output_dir, event_id, filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        self.csv_file = open(filepath, 'w', newline='')
        fieldnames = ['timestamp', 'AccX', 'AccY', 'AccZ', 'AngX', 'AngY', 'AngZ', 'AsX', 'AsY', 'AsZ']
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
        self.csv_writer.writeheader()
        
        for timestamp, data in self.circular_buffer:
            self._write_csv_row(timestamp, data)
        
        self.recording = True
        return filepath
    
    def stop_recording(self):
        """Stop CSV recording"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
        self.recording = False
    
    def _write_csv_row(self, timestamp, data):
        """Write a single CSV row"""
        if self.csv_writer:
            row = {
                'timestamp': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f'),
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
            self.csv_writer.writerow(row)
    
    def get_buffer_data(self) -> List[tuple]:
        """Get all data from circular buffer"""
        return list(self.circular_buffer)
    
    def clear_buffer(self):
        """Clear circular buffer"""
        self.circular_buffer.clear()


class TriggerDetector:
    """Sliding window trigger detection logic"""
    
    def __init__(self, threshold: float, trigger_ratio: float, window_size: int):
        self.threshold = threshold
        self.trigger_ratio = trigger_ratio
        self.window_size = window_size
        self.windows = {}
        self.logger = logging.getLogger("TriggerDetector")
    
    def check_trigger(self, device_num: int, data: Dict) -> tuple:
        """Check if trigger condition is met
        
        Returns:
            (triggered: bool, max_acceleration: float)
        """
        max_acc = max(
            abs(data.get('AccX', 0)),
            abs(data.get('AccY', 0)),
            abs(data.get('AccZ', 0))
        )
        
        if device_num not in self.windows:
            self.windows[device_num] = deque(maxlen=self.window_size)
        
        self.windows[device_num].append(max_acc > self.threshold)
        
        if len(self.windows[device_num]) == self.window_size:
            exceed_count = sum(self.windows[device_num])
            ratio = exceed_count / self.window_size
            
            if ratio >= self.trigger_ratio:
                self.logger.info(f"Trigger detected on device {device_num}: {exceed_count}/{self.window_size} samples ({ratio:.1%}) exceed {self.threshold}g")
                return True, max_acc
        
        return False, max_acc
    
    def reset(self):
        """Reset all trigger windows"""
        self.windows.clear()


class EventRecorder:
    """Records and manages detection events"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger("EventRecorder")
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                trigger_device INTEGER NOT NULL,
                max_acceleration REAL NOT NULL,
                duration REAL NOT NULL,
                num_devices INTEGER NOT NULL,
                data_path TEXT NOT NULL,
                uploaded INTEGER DEFAULT 0,
                upload_time TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def save_event(self, event_id: str, trigger_device: int, max_acc: float, 
                   duration: float, num_devices: int, data_path: str):
        """Save event metadata to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO events (event_id, timestamp, trigger_device, max_acceleration, 
                                   duration, num_devices, data_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (event_id, datetime.now().isoformat(), trigger_device, max_acc, 
                  duration, num_devices, data_path))
            conn.commit()
            self.logger.info(f"Event {event_id} saved to database")
        except sqlite3.IntegrityError:
            self.logger.warning(f"Event {event_id} already exists in database")
        finally:
            conn.close()
    
    def get_unuploaded_events(self) -> List[Dict]:
        """Get list of events not yet uploaded"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT event_id, data_path FROM events WHERE uploaded = 0
        ''')
        
        events = [{'event_id': row[0], 'data_path': row[1]} for row in cursor.fetchall()]
        conn.close()
        
        return events
    
    def mark_uploaded(self, event_id: str):
        """Mark event as uploaded"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE events SET uploaded = 1, upload_time = ? WHERE event_id = ?
        ''', (datetime.now().isoformat(), event_id))
        
        conn.commit()
        conn.close()
        self.logger.info(f"Event {event_id} marked as uploaded")


class CloudUploader:
    """Handles cloud upload of event data"""
    
    def __init__(self, config: Dict, event_recorder: EventRecorder):
        self.enabled = config.get('enabled', False)
        self.upload_url = config.get('upload_url', 'http://localhost:8000/api/upload')
        self.upload_interval = config.get('upload_interval', 60)
        self.retry_count = config.get('retry_count', 3)
        self.retry_delay = config.get('retry_delay', 5)
        
        self.event_recorder = event_recorder
        self.running = False
        self.thread = None
        
        self.logger = logging.getLogger("CloudUploader")
    
    def start(self):
        """Start background upload thread"""
        if not self.enabled:
            self.logger.info("Cloud upload disabled")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._upload_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Cloud upload started: {self.upload_url}")
    
    def stop(self):
        """Stop upload thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _upload_loop(self):
        """Background loop for uploading events"""
        while self.running:
            try:
                unuploaded = self.event_recorder.get_unuploaded_events()
                
                for event in unuploaded:
                    if not self.running:
                        break
                    
                    success = self._upload_event(event)
                    if success:
                        self.event_recorder.mark_uploaded(event['event_id'])
                
            except Exception as e:
                self.logger.error(f"Upload loop error: {e}")
            
            time.sleep(self.upload_interval)
    
    def _upload_event(self, event: Dict) -> bool:
        """Upload a single event"""
        event_id = event['event_id']
        data_path = event['data_path']
        
        if not os.path.exists(data_path):
            self.logger.error(f"Event path not found: {data_path}")
            return False
        
        for attempt in range(self.retry_count):
            try:
                files = {}
                metadata_path = os.path.join(data_path, 'metadata.json')
                
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                else:
                    metadata = {'event_id': event_id}
                
                for filename in os.listdir(data_path):
                    if filename.endswith('.csv'):
                        filepath = os.path.join(data_path, filename)
                        files[filename] = open(filepath, 'rb')
                
                response = requests.post(
                    self.upload_url,
                    data={'metadata': json.dumps(metadata)},
                    files=files,
                    timeout=30
                )
                
                for f in files.values():
                    f.close()
                
                if response.status_code == 200:
                    self.logger.info(f"Successfully uploaded event {event_id}")
                    return True
                else:
                    self.logger.warning(f"Upload failed (attempt {attempt+1}/{self.retry_count}): {response.status_code}")
                
            except Exception as e:
                self.logger.error(f"Upload error (attempt {attempt+1}/{self.retry_count}): {e}")
            
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay)
        
        return False


class TrainDetectionSystem:
    """Main system coordinator"""
    
    def __init__(self, config_file: str = "train_detection_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        
        self._setup_logging()
        
        self.devices: Dict[int, DeviceManager] = {}
        self.loop = None
        self.running = False
        
        detection_config = self.config['detection']
        self.sampling_rate = detection_config['sampling_rate']
        self.post_trigger_duration = detection_config['post_trigger_duration']
        self.pre_buffer_duration = detection_config['pre_buffer_duration']
        
        window_size = int(self.sampling_rate * detection_config['window_duration'])
        self.trigger_detector = TriggerDetector(
            threshold=detection_config['threshold'],
            trigger_ratio=detection_config['trigger_ratio'],
            window_size=window_size
        )
        
        storage_config = self.config['storage']
        self.output_dir = storage_config['local_path']
        os.makedirs(self.output_dir, exist_ok=True)
        
        db_path = os.path.join(self.output_dir, storage_config['db_name'])
        self.event_recorder = EventRecorder(db_path)
        
        self.cloud_uploader = CloudUploader(self.config['cloud'], self.event_recorder)
        
        self.event_active = False
        self.event_id = None
        self.event_start_time = None
        self.trigger_device = None
        self.max_acceleration = 0
        
        self.logger = logging.getLogger("TrainDetectionSystem")
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_config(self) -> Dict:
        """Load configuration from JSON file"""
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_level = self.config['system'].get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def _signal_handler(self, signum, frame):
        """Handle system signals"""
        self.logger.info("Received stop signal, shutting down...")
        self.stop()
    
    def initialize_devices(self):
        """Initialize all enabled devices"""
        device_configs = [d for d in self.config['devices'] if d.get('enabled', True)]
        
        for dev_config in device_configs:
            device = DeviceManager(
                number=dev_config['number'],
                name=dev_config['name'],
                mac=dev_config['mac'],
                sampling_rate=self.sampling_rate,
                buffer_duration=self.pre_buffer_duration
            )
            self.devices[device.number] = device
        
        self.logger.info(f"Initialized {len(self.devices)} devices")
    
    async def connect_devices(self):
        """Connect to all devices in parallel"""
        async def connect_single(device: DeviceManager):
            try:
                device.device = DeviceModel(device.name, device.mac, device.data_callback)
                await device.device.openDevice()
            except Exception as e:
                self.logger.error(f"Failed to connect device {device.number}: {e}")
        
        tasks = [connect_single(device) for device in self.devices.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def _setup_async_loop(self):
        """Setup asyncio event loop in separate thread"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        time.sleep(0.5)
    
    def start(self):
        """Start the detection system"""
        self.logger.info("=" * 60)
        self.logger.info("Train Detection System Starting")
        self.logger.info(f"Config: {self.config_file}")
        self.logger.info(f"Detection threshold: {self.config['detection']['threshold']}g")
        self.logger.info(f"Trigger ratio: {self.config['detection']['trigger_ratio']:.0%}")
        self.logger.info("=" * 60)
        
        self.initialize_devices()
        
        self._setup_async_loop()
        
        self.logger.info("Connecting to devices...")
        future = asyncio.run_coroutine_threadsafe(self.connect_devices(), self.loop)
        future.result(timeout=self.config['system']['connection_timeout'])
        
        self.running = True
        
        self.cloud_uploader.start()
        
        self._monitor_connections()
        self._process_data_loop()
    
    def _monitor_connections(self):
        """Monitor device connection status"""
        def monitor():
            while self.running:
                time.sleep(5)
                
                current_time = time.time()
                timeout = self.config['system']['data_timeout']
                
                for device in self.devices.values():
                    if device.data_flowing and device.last_data_time > 0:
                        if current_time - device.last_data_time > timeout:
                            device.connected = False
                            device.data_flowing = False
                            self.logger.warning(f"Device {device.number} connection lost")
                        elif not device.connected:
                            device.connected = True
                            self.logger.info(f"Device {device.number} connected")
        
        threading.Thread(target=monitor, daemon=True).start()
    
    def _process_data_loop(self):
        """Main data processing loop"""
        last_status = time.time()
        status_interval = self.config['system']['status_interval']
        
        self.logger.info("Detection system active")
        
        try:
            while self.running:
                for device in self.devices.values():
                    processed_data = device.process_data()
                    
                    for timestamp, data in processed_data:
                        self._check_trigger(device.number, data)
                
                if self.event_active:
                    elapsed = time.time() - self.event_start_time
                    if elapsed >= self.post_trigger_duration:
                        self._stop_event()
                
                current_time = time.time()
                if current_time - last_status >= status_interval:
                    self._print_status()
                    last_status = current_time
                
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    def _check_trigger(self, device_num: int, data: Dict):
        """Check trigger condition and start event if needed"""
        if self.event_active:
            return
        
        triggered, max_acc = self.trigger_detector.check_trigger(device_num, data)
        
        if triggered:
            self._start_event(device_num, max_acc)
    
    def _start_event(self, trigger_device: int, max_acc: float):
        """Start recording an event"""
        self.event_id = f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.event_start_time = time.time()
        self.trigger_device = trigger_device
        self.max_acceleration = max_acc
        self.event_active = True
        
        self.logger.info(f"EVENT STARTED: {self.event_id} (Device {trigger_device}, {max_acc:.2f}g)")
        
        for device in self.devices.values():
            if device.connected:
                try:
                    device.start_recording(self.output_dir, self.event_id)
                except Exception as e:
                    self.logger.error(f"Failed to start recording on device {device.number}: {e}")
        
        self.trigger_detector.reset()
    
    def _stop_event(self):
        """Stop recording an event"""
        if not self.event_active:
            return
        
        duration = time.time() - self.event_start_time
        
        for device in self.devices.values():
            device.stop_recording()
        
        event_path = os.path.join(self.output_dir, self.event_id)
        
        metadata = {
            'event_id': self.event_id,
            'timestamp': datetime.fromtimestamp(self.event_start_time).isoformat(),
            'trigger_device': self.trigger_device,
            'max_acceleration': self.max_acceleration,
            'duration': duration,
            'threshold': self.config['detection']['threshold'],
            'trigger_ratio': self.config['detection']['trigger_ratio'],
            'devices': list(self.devices.keys()),
            'sampling_rate': self.sampling_rate
        }
        
        metadata_path = os.path.join(event_path, 'metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.event_recorder.save_event(
            self.event_id,
            self.trigger_device,
            self.max_acceleration,
            duration,
            len(self.devices),
            event_path
        )
        
        self.logger.info(f"EVENT STOPPED: {self.event_id} (Duration: {duration:.1f}s)")
        
        self.event_active = False
        self.event_id = None
    
    def _print_status(self):
        """Print system status"""
        connected = sum(1 for d in self.devices.values() if d.connected)
        status = f"Status: {connected}/{len(self.devices)} devices connected"
        
        if self.event_active:
            elapsed = time.time() - self.event_start_time
            status += f" | Recording event {self.event_id} ({elapsed:.1f}s)"
        
        self.logger.info(status)
    
    def stop(self):
        """Stop the detection system"""
        self.running = False
        
        if self.event_active:
            self._stop_event()
        
        self.cloud_uploader.stop()
        
        self.logger.info("Disconnecting devices...")
        for device in self.devices.values():
            try:
                if device.device:
                    device.device.closeDevice()
            except Exception as e:
                self.logger.error(f"Error disconnecting device {device.number}: {e}")
        
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.logger.info("System shutdown complete")


def main():
    system = TrainDetectionSystem()
    system.start()


if __name__ == "__main__":
    main()
