#!/usr/bin/env python3
"""
Train Detection System - Backend Service
å¤šè®¾å¤‡IMUç›‘æŽ§ï¼ŒåŸºäºŽé˜ˆå€¼è§¦å‘ï¼Œå¸¦å¾ªçŽ¯ç¼“å†²åŒº
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

from witmotion_device_model_clean import DeviceModel


class CircularBuffer:
    """å¾ªçŽ¯ç¼“å†²åŒº - å§‹ç»ˆä¿æŒæœ€è¿‘Nç§’çš„æ•°æ®"""
    def __init__(self, max_seconds=5, sample_rate=50):
        self.max_size = max_seconds * sample_rate
        self.buffer = deque(maxlen=self.max_size)
        self.sample_rate = sample_rate
    
    def add(self, timestamp, data):
        """æ·»åŠ æ•°æ®ç‚¹"""
        self.buffer.append((timestamp, data))
    
    def get_all(self):
        """èŽ·å–æ‰€æœ‰ç¼“å†²æ•°æ®"""
        return list(self.buffer)
    
    def clear(self):
        """æ¸…ç©ºç¼“å†²åŒº"""
        self.buffer.clear()
    
    def __len__(self):
        return len(self.buffer)


class IMUDevice:
    """å•ä¸ªIMUè®¾å¤‡ç®¡ç†"""
    def __init__(self, number, name, mac, callback):
        self.number = number
        self.name = name
        self.mac = mac
        self.device = None
        self.connected = False
        self.last_data_time = 0
        self.callback = callback
        
        # å¾ªçŽ¯ç¼“å†²åŒºï¼ˆä¿æŒæœ€è¿‘5ç§’ï¼‰
        self.buffer = CircularBuffer(max_seconds=5, sample_rate=50)
        
        # å½“å‰æ•°æ®
        self.current_data = {}
        
        # Sliding window status
        self.sliding_status = {'healthy': True, 'percentage': 0.0}
        
        print(f"ðŸ“± Initialized Device {number}: {name} ({mac})")
    
    def data_callback(self, device_model: DeviceModel):
        """è®¾å¤‡æ•°æ®å›žè°ƒ"""
        current_time = time.time()
        self.last_data_time = current_time
        
        if not self.connected:
            self.connected = True
            print(f"âœ… Device {self.number} connected and streaming data")
        
        device_data = device_model.deviceData.copy()
        self.current_data = device_data
        
        # æ·»åŠ åˆ°å¾ªçŽ¯ç¼“å†²åŒº
        self.buffer.add(current_time, device_data)
        
        # Update sliding window status
        if hasattr(device_model, 'check_sliding_window'):
            self.sliding_status = device_model.check_sliding_window()
        
        # å›žè°ƒç»™æ£€æµ‹å™¨
        if self.callback:
            self.callback(self.number, current_time, device_data)
    
    def get_buffer_data(self):
        """èŽ·å–ç¼“å†²åŒºæ•°æ®"""
        return self.buffer.get_all()
    
    def clear_buffer(self):
        """æ¸…ç©ºç¼“å†²åŒº"""
        self.buffer.clear()


class TrainDetector:
    """ç«è½¦æ£€æµ‹å™¨ - æ ¸å¿ƒé€»è¾‘"""
    def __init__(self, config_file="witmotion_config.json", output_dir="train_events"):
        self.config_file = config_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # æ£€æµ‹å‚æ•°
        self.threshold = 2.0  # åŠ é€Ÿåº¦é˜ˆå€¼ (g)
        self.min_duration = 1.0  # æœ€çŸ­æŒç»­æ—¶é—´ (ç§’)
        self.post_trigger_duration = 5.0  # è§¦å‘åŽç»§ç»­è®°å½•æ—¶é—´ (ç§’)
        
        # è®¾å¤‡ç®¡ç†
        self.devices = {}  # number -> IMUDevice
        self.loop = None
        
        # æ£€æµ‹çŠ¶æ€
        self.detecting = False
        self.recording = False
        self.trigger_time = None
        self.trigger_device = None
        self.event_data = {}  # device_number -> [(timestamp, data), ...]
        self.event_id = None
        
        # æ•°æ®åº“
        self.db_path = self.output_dir / "events.db"
        self.init_database()
        
        # ç»Ÿè®¡
        self.stats = {
            'total_events': 0,
            'last_event_time': None,
            'uptime_start': time.time()
        }
        
        # Upload configuration
        self.upload_enabled = False
        self.upload_url = None
        self.upload_interval = 60
        self.last_upload = 0
        
        print("=" * 60)
        print("ðŸš‚ Train Detection System")
        print("=" * 60)
        print(f"Config: {config_file}")
        print(f"Output: {output_dir}")
        print(f"Threshold: {self.threshold}g")
        print(f"Min Duration: {self.min_duration}s")
        print(f"Post-trigger: {self.post_trigger_duration}s")
        print("=" * 60)
    
    def init_database(self):
        """åˆå§‹åŒ–SQLiteæ•°æ®åº“"""
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
        print(f"ðŸ“Š Database initialized: {self.db_path}")
    
    def load_config(self):
        """åŠ è½½é…ç½®æ–‡ä»¶"""
        if not os.path.exists(self.config_file):
            print(f"âŒ Config file not found: {self.config_file}")
            return []
        
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                devices = data.get('devices', [])
                enabled = [d for d in devices if d.get('enabled', True)]
                print(f"âœ… Loaded {len(enabled)} enabled devices from config")
                
                # Load sliding window config
                sw_config = data.get('sliding_window', {})
                if sw_config.get('enabled', False):
                    print(f"âœ… Sliding window enabled: {sw_config}")
                
                # Load upload config
                upload_config = data.get('upload', {})
                if upload_config.get('enabled', False):
                    self.upload_enabled = True
                    self.upload_url = upload_config.get('url', 'http://localhost:8000/api/data')
                    self.upload_interval = upload_config.get('interval', 60)
                    print(f"âœ… Upload enabled: {self.upload_url}")
                
                # Save configs for device setup
                self.sliding_window_config = sw_config
                
                return enabled
        except Exception as e:
            print(f"âŒ Failed to load config: {e}")
            return []
    
    def device_data_callback(self, device_number, timestamp, data):
        """è®¾å¤‡æ•°æ®å›žè°ƒ - æ£€æµ‹é€»è¾‘"""
        if not self.detecting:
            return
        
        # è®¡ç®—åŠ é€Ÿåº¦å¹…å€¼
        acc_x = data.get('AccX', 0)
        acc_y = data.get('AccY', 0)
        acc_z = data.get('AccZ', 0)
        magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
        
        # æ£€æŸ¥æ˜¯å¦è§¦å‘
        if not self.recording and magnitude > self.threshold:
            self.trigger_detection(device_number, timestamp, magnitude)
        
        # å¦‚æžœæ­£åœ¨è®°å½•ï¼Œç»§ç»­æ”¶é›†æ•°æ®
        if self.recording:
            if device_number not in self.event_data:
                self.event_data[device_number] = []
            self.event_data[device_number].append((timestamp, data.copy()))
            
            # æ£€æŸ¥æ˜¯å¦åº”è¯¥ç»“æŸè®°å½•
            elapsed = timestamp - self.trigger_time
            if elapsed >= self.post_trigger_duration:
                self.end_recording()
    
    def trigger_detection(self, device_number, timestamp, magnitude):
        """è§¦å‘æ£€æµ‹äº‹ä»¶"""
        self.recording = True
        self.trigger_time = timestamp
        self.trigger_device = device_number
        self.event_id = datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')
        self.event_data = {}
        
        print(f"\nðŸ”” TRAIN DETECTED!")
        print(f"   Device: {device_number}")
        print(f"   Time: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Magnitude: {magnitude:.3f}g")
        print(f"   Recording for {self.post_trigger_duration}s...")
        
        # æ”¶é›†æ‰€æœ‰è®¾å¤‡çš„ç¼“å†²åŒºæ•°æ®ï¼ˆå‰5ç§’ï¼‰
        for dev_num, device in self.devices.items():
            buffer_data = device.get_buffer_data()
            if buffer_data:
                self.event_data[dev_num] = buffer_data.copy()
                print(f"   âœ“ Captured {len(buffer_data)} samples from Device {dev_num} buffer")
    
    def end_recording(self):
        """ç»“æŸè®°å½•å¹¶ä¿å­˜æ•°æ®"""
        if not self.recording:
            return
        
        duration = time.time() - self.trigger_time
        print(f"\nðŸ’¾ Saving event data...")
        print(f"   Duration: {duration:.2f}s")
        
        # åˆ›å»ºäº‹ä»¶ç›®å½•
        event_dir = self.output_dir / f"event_{self.event_id}"
        event_dir.mkdir(exist_ok=True)
        
        # ä¿å­˜æ¯ä¸ªè®¾å¤‡çš„æ•°æ®
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
                    
                    # è®¡ç®—æœ€å¤§åŠ é€Ÿåº¦
                    acc = (data.get('AccX', 0)**2 + 
                          data.get('AccY', 0)**2 + 
                          data.get('AccZ', 0)**2)**0.5
                    max_acc = max(max_acc, acc)
            
            print(f"   âœ“ Saved Device {dev_num}: {len(data_list)} samples")
        
        # ä¿å­˜å…ƒæ•°æ®
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
        
        # ä¿å­˜åˆ°æ•°æ®åº“
        self.save_to_database(metadata, str(event_dir))
        
        # æ›´æ–°ç»Ÿè®¡
        self.stats['total_events'] += 1
        self.stats['last_event_time'] = self.trigger_time
        
        print(f"   âœ… Event saved: {event_dir.name}")
        print(f"   Max acceleration: {max_acc:.3f}g")
        print(f"   Total events: {self.stats['total_events']}\n")
        
        # é‡ç½®çŠ¶æ€
        self.recording = False
        self.event_data = {}
    
    def save_to_database(self, metadata, data_path):
        """ä¿å­˜äº‹ä»¶åˆ°æ•°æ®åº“"""
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
            print(f"   âš ï¸  Database save error: {e}")
    
    async def connect_device(self, device):
        """è¿žæŽ¥å•ä¸ªè®¾å¤‡ï¼ˆå¼‚æ­¥ï¼‰"""
        try:
            print(f"ðŸ”„ Connecting Device {device.number}: {device.mac}...")
            device.device = DeviceModel(device.name, device.mac, device.data_callback)
            # Configure sliding window if enabled
            if hasattr(self, 'sliding_window_config') and self.sliding_window_config.get('enabled', False):
                device.device.sliding_config = self.sliding_window_config
                device.device.sliding_window = __import__('collections').deque(maxlen=self.sliding_window_config.get('window_size', 50))
            # ç›´æŽ¥awaitï¼Œä¸è¦å†åˆ›å»ºçº¿ç¨‹
            await device.device.openDevice()
        except Exception as e:
            print(f"âŒ Device {device.number} connection failed: {e}")
            device.connected = False
    
    def setup_async_loop(self):
        """è®¾ç½®å¼‚æ­¥äº‹ä»¶å¾ªçŽ¯"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        time.sleep(0.2)
        print("âœ… Async loop started")
    
    def start(self):
        """å¯åŠ¨æ£€æµ‹ç³»ç»Ÿ"""
        # åŠ è½½é…ç½®
        config_devices = self.load_config()
        if not config_devices:
            print("âŒ No devices to connect")
            return False
        
        # è®¾ç½®å¼‚æ­¥å¾ªçŽ¯
        self.setup_async_loop()
        
        # åˆ›å»ºè®¾å¤‡å®žä¾‹
        for dev_config in config_devices:
            number = dev_config['number']
            name = dev_config['name']
            mac = dev_config['mac']
            
            device = IMUDevice(number, name, mac, self.device_data_callback)
            self.devices[number] = device
        
        print(f"\nðŸ”Œ Connecting {len(self.devices)} devices sequentially...")
        print("   (BlueZ limitation: must connect one at a time)")
        
        # é¡ºåºè¿žæŽ¥è®¾å¤‡ï¼ˆBlueZé™åˆ¶ï¼‰
        async def connect_sequential():
            for device in self.devices.values():
                print(f"\nðŸ”„ Connecting Device {device.number}: {device.mac}...")
                try:
                    await self.connect_device(device)
                    await asyncio.sleep(1)  # ç»™è®¾å¤‡æ—¶é—´ç¨³å®š
                except Exception as e:
                    print(f"âŒ Device {device.number} failed: {e}")
        
        # æäº¤åˆ°äº‹ä»¶å¾ªçŽ¯å¹¶ç­‰å¾…
        future = asyncio.run_coroutine_threadsafe(connect_sequential(), self.loop)
        
        print("\nâ³ Waiting for sequential connections...")
        try:
            future.result(timeout=30)  # æœ€å¤šç­‰30ç§’ï¼ˆ4è®¾å¤‡ x æ¯ä¸ª7ç§’ï¼‰
        except Exception as e:
            print(f"âš ï¸  Connection timeout or error: {e}")
        
        # æ£€æŸ¥è¿žæŽ¥çŠ¶æ€
        connected = [d for d in self.devices.values() if d.connected]
        print(f"\nâœ… Connected: {len(connected)}/{len(self.devices)} devices")
        
        if connected:
            for device in connected:
                print(f"   âœ“ Device {device.number}: {device.name}")
        
        if not connected:
            print("âŒ No devices connected!")
            return False
        
        # å¼€å§‹æ£€æµ‹
        self.detecting = True
        print(f"\nðŸŽ¯ Detection started!")
        print(f"   Threshold: {self.threshold}g")
        print(f"   Monitoring {len(connected)} devices...")
        print("   Waiting for train...\n")
        
        return True
    
    def stop(self):
        """åœæ­¢æ£€æµ‹"""
        print("\nðŸ›‘ Stopping detection...")
        self.detecting = False
        
        # å¦‚æžœæ­£åœ¨è®°å½•ï¼Œå…ˆä¿å­˜
        if self.recording:
            self.end_recording()
        
        # å…³é—­æ‰€æœ‰è®¾å¤‡
        for device in self.devices.values():
            if device.device:
                device.device.closeDevice()
        
        # åœæ­¢å¾ªçŽ¯
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        print("âœ… Detection stopped")
    
    def print_status(self):
        """æ‰“å°çŠ¶æ€ä¿¡æ¯"""
        uptime = time.time() - self.stats['uptime_start']
        
        print("\n" + "=" * 60)
        print("ðŸ“Š SYSTEM STATUS")
        print("=" * 60)
        print(f"Uptime: {uptime/3600:.1f} hours")
        print(f"Total Events: {self.stats['total_events']}")
        
        if self.stats['last_event_time']:
            last_event = datetime.fromtimestamp(self.stats['last_event_time'])
            print(f"Last Event: {last_event.strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\nDevices: {len(self.devices)}")
        for num, device in sorted(self.devices.items()):
            status = "ðŸŸ¢ Connected" if device.connected else "ðŸ”´ Disconnected"
            buffer_size = len(device.buffer)
            print(f"  Device {num}: {status} (Buffer: {buffer_size} samples)")
            
            if device.current_data:
                acc = device.current_data
                print(f"    Acc: X={acc.get('AccX', 0):6.3f}g "
                      f"Y={acc.get('AccY', 0):6.3f}g "
                      f"Z={acc.get('AccZ', 0):6.3f}g")
        
        print("=" * 60 + "\n")
    
    def upload_data(self):
        """Upload health data to server"""
        if not self.upload_enabled:
            return
        
        current_time = time.time()
        if current_time - self.last_upload < self.upload_interval:
            return
        
        try:
            import requests
            devices_status = []
            for num, device in self.devices.items():
                if device.connected:
                    devices_status.append({
                        'number': num,
                        'name': device.name,
                        'sliding_window': device.sliding_status
                    })
            
            payload = {
                'timestamp': datetime.now().isoformat(),
                'devices': devices_status
            }
            
            requests.post(self.upload_url, json=payload, timeout=5)
            self.last_upload = current_time
        except:
            pass  # Silently fail
    
    
    def run_monitoring(self):
        """è¿è¡Œç›‘æŽ§å¾ªçŽ¯"""
        print("Press Ctrl+C to stop\n")
        
        try:
            status_interval = 30  # æ¯30ç§’æ‰“å°ä¸€æ¬¡çŠ¶æ€
            last_status_time = time.time()
            
            while self.detecting:
                time.sleep(1)
                
                # å®šæœŸæ‰“å°çŠ¶æ€
                
                # Try upload
                self.upload_data()
                if time.time() - last_status_time >= status_interval:
                    self.print_status()
                    last_status_time = time.time()
                
        except KeyboardInterrupt:
            print("\n\nâš ï¸  Interrupted by user")
        finally:
            self.stop()


def main():
    """ä¸»å‡½æ•°"""
    detector = TrainDetector(
        config_file="witmotion_config.json",
        output_dir="train_events"
    )
    
    # å¯åŠ¨æ£€æµ‹
    if detector.start():
        detector.run_monitoring()
    else:
        print("âŒ Failed to start detection system")


if __name__ == "__main__":
    main()

