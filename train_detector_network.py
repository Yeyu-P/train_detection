#!/usr/bin/env python3
# coding:UTF-8
"""
火车检测系统 - 带网络上传版本
"""

import time
import json
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
import numpy as np
from collections import deque
import signal
import sys
import requests
from queue import Queue
import threading
from witmotion_device_model_clean import DeviceModel


# ==================== 配置加载器 ====================
class ConfigLoader:
    def __init__(self, config_file):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
    
    def get(self, *keys):
        """获取嵌套配置值"""
        value = self.config
        for key in keys:
            value = value[key]
        return value
    
    def get_all(self):
        return self.config


# ==================== LED控制器 ====================
class LEDController:
    def __init__(self, config):
        self.enabled = config.get('led', 'enabled')
        if self.enabled:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(config.get('led', 'pin_power'), GPIO.OUT)
                GPIO.setup(config.get('led', 'pin_detecting'), GPIO.OUT)
                GPIO.setup(config.get('led', 'pin_error'), GPIO.OUT)
                self.power_on()
            except ImportError:
                logging.warning("RPi.GPIO not available, LED disabled")
                self.enabled = False
    
    def power_on(self):
        if self.enabled:
            self.GPIO.output(17, self.GPIO.HIGH)
    
    def detecting_on(self):
        if self.enabled:
            self.GPIO.output(27, self.GPIO.HIGH)
    
    def detecting_off(self):
        if self.enabled:
            self.GPIO.output(27, self.GPIO.LOW)
    
    def error_on(self):
        if self.enabled:
            self.GPIO.output(22, self.GPIO.HIGH)
    
    def error_off(self):
        if self.enabled:
            self.GPIO.output(22, self.GPIO.LOW)
    
    def cleanup(self):
        if self.enabled:
            self.GPIO.cleanup()


# ==================== 网络上传管理器 ====================
class NetworkUploader:
    def __init__(self, config):
        self.enabled = config.get('network', 'enabled')
        self.server_url = config.get('network', 'server_url')
        self.api_key = config.get('network', 'api_key')
        self.timeout = config.get('network', 'timeout_sec')
        self.retry_max = config.get('network', 'retry_max_attempts')
        self.retry_interval = config.get('network', 'retry_interval_sec')
        
        # 离线队列
        self.offline_queue = Queue(maxsize=config.get('network', 'offline_cache_max_items'))
        self.upload_thread = None
        self.running = False
        
        # 统计
        self.total_uploads = 0
        self.failed_uploads = 0
        
        if self.enabled:
            self.start_upload_thread()
    
    def start_upload_thread(self):
        """启动后台上传线程"""
        self.running = True
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self.upload_thread.start()
        logging.info("网络上传线程已启动")
    
    def _upload_worker(self):
        """后台上传工作线程"""
        while self.running:
            try:
                if not self.offline_queue.empty():
                    data_type, data = self.offline_queue.get(timeout=1)
                    success = self._send_to_server(data_type, data)
                    
                    if success:
                        self.total_uploads += 1
                        logging.debug(f"上传成功: {data_type}")
                    else:
                        self.failed_uploads += 1
                        # 重新放回队列（如果队列未满）
                        if not self.offline_queue.full():
                            self.offline_queue.put((data_type, data))
                        logging.warning(f"上传失败，已重新加入队列")
                else:
                    time.sleep(1)
            except Exception as e:
                logging.error(f"上传线程错误: {e}")
                time.sleep(5)
    
    def _send_to_server(self, data_type, data):
        """发送数据到服务器"""
        if not self.enabled:
            return False
        
        endpoint = f"{self.server_url}/{data_type}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        for attempt in range(self.retry_max):
            try:
                response = requests.post(
                    endpoint,
                    json=data,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return True
                else:
                    logging.warning(f"服务器返回错误: {response.status_code}")
            
            except requests.exceptions.Timeout:
                logging.warning(f"上传超时 (尝试 {attempt + 1}/{self.retry_max})")
            except requests.exceptions.ConnectionError:
                logging.warning(f"网络连接失败 (尝试 {attempt + 1}/{self.retry_max})")
            except Exception as e:
                logging.error(f"上传异常: {e}")
            
            if attempt < self.retry_max - 1:
                time.sleep(self.retry_interval)
        
        return False
    
    def upload_event(self, event_data):
        """上传火车通过事件"""
        if not self.enabled:
            return
        
        try:
            self.offline_queue.put(('events', event_data), block=False)
        except:
            logging.warning("离线队列已满，丢弃事件")
    
    def upload_status(self, status_data):
        """上传设备状态"""
        if not self.enabled:
            return
        
        try:
            self.offline_queue.put(('status', status_data), block=False)
        except:
            logging.warning("离线队列已满，丢弃状态")
    
    def get_stats(self):
        """获取上传统计"""
        return {
            'total_uploads': self.total_uploads,
            'failed_uploads': self.failed_uploads,
            'queue_size': self.offline_queue.qsize()
        }
    
    def stop(self):
        """停止上传线程"""
        self.running = False
        if self.upload_thread:
            self.upload_thread.join(timeout=5)


# ==================== 火车检测器 ====================
class TrainDetector:
    def __init__(self, device_name, config):
        self.device_name = device_name
        self.threshold = config.get('detection', 'threshold_g')
        self.min_duration = config.get('detection', 'min_duration_sec')
        self.cooldown = config.get('detection', 'cooldown_sec')
        self.buffer_size = config.get('detection', 'background_window_samples')
        
        self.is_detecting = False
        self.detection_start_time = None
        self.last_detection_time = 0
        
        self.acc_buffer = deque(maxlen=self.buffer_size)
        self.detection_data = []
        
        self.background_rms = 0.0
        self.peak_acceleration = 0.0
        
        self.last_data_time = time.time()
        self.total_detections = 0
    
    def update(self, acc_x, acc_y, acc_z, timestamp):
        """更新传感器数据并进行检测"""
        self.last_data_time = time.time()
        
        acc_magnitude = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        self.acc_buffer.append(acc_magnitude)
        if len(self.acc_buffer) >= 10:
            self.background_rms = np.std(self.acc_buffer)
        
        dynamic_threshold = self.background_rms + self.threshold
        current_time = time.time()
        
        if acc_magnitude > dynamic_threshold:
            if not self.is_detecting:
                if current_time - self.last_detection_time > self.cooldown:
                    self.start_detection(timestamp)
            
            if self.is_detecting:
                self.detection_data.append({
                    'timestamp': timestamp,
                    'acc_x': acc_x,
                    'acc_y': acc_y,
                    'acc_z': acc_z,
                    'magnitude': acc_magnitude
                })
                self.peak_acceleration = max(self.peak_acceleration, acc_magnitude)
        else:
            if self.is_detecting:
                duration = current_time - self.detection_start_time
                if duration >= self.min_duration:
                    return self.end_detection(timestamp)
                else:
                    self.cancel_detection()
        
        return None
    
    def start_detection(self, timestamp):
        self.is_detecting = True
        self.detection_start_time = time.time()
        self.detection_data = []
        self.peak_acceleration = 0.0
        logging.info(f"[{self.device_name}] 检测到火车")
    
    def end_detection(self, timestamp):
        duration = time.time() - self.detection_start_time
        self.is_detecting = False
        self.last_detection_time = time.time()
        self.total_detections += 1
        
        result = {
            'device': self.device_name,
            'start_time': self.detection_data[0]['timestamp'] if self.detection_data else timestamp,
            'end_time': timestamp,
            'duration': round(duration, 2),
            'peak_acceleration': round(self.peak_acceleration, 2),
            'background_rms': round(self.background_rms, 3),
            'sample_count': len(self.detection_data)
        }
        
        logging.info(f"[{self.device_name}] 火车通过 - 时长:{duration:.1f}s, 峰值:{self.peak_acceleration:.1f}g")
        
        raw_data = self.detection_data.copy()
        self.detection_data = []
        
        return result, raw_data
    
    def cancel_detection(self):
        self.is_detecting = False
        self.detection_data = []
    
    def is_healthy(self, max_no_data_sec):
        time_since_last_data = time.time() - self.last_data_time
        return time_since_last_data < max_no_data_sec
    
    def get_stats(self):
        return {
            'device': self.device_name,
            'total_detections': self.total_detections,
            'is_detecting': self.is_detecting,
            'background_rms': round(self.background_rms, 3),
            'last_data_time': datetime.fromtimestamp(self.last_data_time).strftime('%Y-%m-%d %H:%M:%S')
        }


# ==================== 存储管理器 ====================
class StorageManager:
    def __init__(self, config):
        self.data_dir = Path(config.get('storage', 'data_dir'))
        self.save_raw = config.get('storage', 'save_raw_data')
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def save_event(self, event_info):
        date_str = datetime.now().strftime('%Y%m%d')
        event_file = self.data_dir / f"events_{date_str}.jsonl"
        
        with open(event_file, 'a') as f:
            f.write(json.dumps(event_info) + '\n')
    
    def save_raw_data(self, device_name, timestamp, raw_data):
        if not self.save_raw or not raw_data:
            return None
        
        data_file = self.data_dir / f"raw_{device_name}_{timestamp}.json"
        with open(data_file, 'w') as f:
            json.dump(raw_data, f)
        
        return data_file.name


# ==================== 设备管理器 ====================
class DeviceManager:
    def __init__(self, device_config, data_callback, config):
        self.config_data = device_config
        self.device_name = device_config['name']
        self.mac = device_config['mac']
        self.data_callback = data_callback
        
        self.reconnect_enabled = config.get('reconnect', 'enabled')
        self.reconnect_max = config.get('reconnect', 'max_attempts')
        self.reconnect_interval = config.get('reconnect', 'interval_sec')
        
        self.device = None
        self.is_connected = False
        self.reconnect_count = 0
        self.last_connect_attempt = 0
    
    async def connect(self):
        try:
            logging.info(f"连接设备: {self.device_name} ({self.mac})")
            self.device = DeviceModel(self.device_name, self.mac, self.data_callback)
            await asyncio.wait_for(self.device.openDevice(), timeout=30)
            self.is_connected = True
            self.reconnect_count = 0
            logging.info(f"设备 {self.device_name} 连接成功")
        except Exception as e:
            logging.error(f"设备 {self.device_name} 连接失败: {e}")
            self.is_connected = False
    
    async def reconnect_loop(self):
        while self.reconnect_enabled:
            if not self.is_connected:
                current_time = time.time()
                if current_time - self.last_connect_attempt > self.reconnect_interval:
                    if self.reconnect_count < self.reconnect_max:
                        logging.info(f"尝试重连 {self.device_name} (第{self.reconnect_count + 1}次)")
                        self.last_connect_attempt = current_time
                        self.reconnect_count += 1
                        await self.connect()
                    else:
                        await asyncio.sleep(60)
                        self.reconnect_count = 0
            await asyncio.sleep(self.reconnect_interval)
    
    def disconnect(self):
        if self.device:
            self.device.closeDevice()
            self.is_connected = False


# ==================== 主管理器 ====================
class SystemManager:
    def __init__(self, config_file):
        self.config = ConfigLoader(config_file)
        self.device_managers = {}
        self.detectors = {}
        self.led = LEDController(self.config)
        self.storage = StorageManager(self.config)
        self.uploader = NetworkUploader(self.config)
        
        self.running = True
        self.setup_logging()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logging.info("=" * 60)
        logging.info(f"系统启动: {self.config.get('system', 'name')}")
        logging.info(f"位置: {self.config.get('system', 'location')}")
        logging.info(f"网络上传: {'启用' if self.config.get('network', 'enabled') else '禁用'}")
        logging.info("=" * 60)
    
    def setup_logging(self):
        log_dir = Path(self.config.get('storage', 'log_dir'))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "system.log"
        
        handler = RotatingFileHandler(
            log_file,
            maxBytes=self.config.get('storage', 'max_log_size_mb') * 1024 * 1024,
            backupCount=self.config.get('storage', 'max_log_files')
        )
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.addHandler(logging.StreamHandler())
    
    def signal_handler(self, signum, frame):
        logging.info(f"收到信号 {signum}，准备退出...")
        self.running = False
    
    def data_callback(self, device):
        device_name = device.deviceName
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        acc_x = device.get("AccX")
        acc_y = device.get("AccY")
        acc_z = device.get("AccZ")
        
        if acc_x is None:
            return
        
        if device_name in self.detectors:
            detector = self.detectors[device_name]
            result = detector.update(acc_x, acc_y, acc_z, timestamp)
            
            if result is not None:
                event_info, raw_data = result
                
                # 保存到本地
                self.storage.save_event(event_info)
                if raw_data and self.config.get('storage', 'save_raw_data'):
                    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.storage.save_raw_data(device_name, timestamp_str, raw_data)
                
                # 上传到服务器
                self.uploader.upload_event(event_info)
                
                self.led.detecting_off()
            elif detector.is_detecting:
                self.led.detecting_on()
    
    async def status_upload_loop(self):
        """定期上传设备状态"""
        interval = self.config.get('monitoring', 'status_upload_interval_sec')
        
        while self.running:
            await asyncio.sleep(interval)
            
            status_data = {
                'timestamp': datetime.now().isoformat(),
                'system_name': self.config.get('system', 'name'),
                'location': self.config.get('system', 'location'),
                'devices': []
            }
            
            for name, detector in self.detectors.items():
                device_status = {
                    'name': name,
                    'connected': self.device_managers[name].is_connected,
                    'healthy': detector.is_healthy(self.config.get('monitoring', 'max_no_data_sec')),
                    'total_detections': detector.total_detections,
                    'background_rms': detector.background_rms
                }
                status_data['devices'].append(device_status)
            
            # 添加上传统计
            status_data['network_stats'] = self.uploader.get_stats()
            
            self.uploader.upload_status(status_data)
            logging.debug("设备状态已上传")
    
    async def health_check_loop(self):
        interval = self.config.get('monitoring', 'health_check_interval_sec')
        max_no_data = self.config.get('monitoring', 'max_no_data_sec')
        
        while self.running:
            await asyncio.sleep(interval)
            
            logging.info("--- 健康检查 ---")
            
            for name, detector in self.detectors.items():
                if not detector.is_healthy(max_no_data):
                    logging.warning(f"设备 {name} 长时间无数据")
                    self.led.error_on()
                else:
                    stats = detector.get_stats()
                    logging.info(f"{name}: 检测={stats['total_detections']}, 噪音={stats['background_rms']}g")
            
            # 上传统计
            upload_stats = self.uploader.get_stats()
            logging.info(f"网络: 成功={upload_stats['total_uploads']}, 失败={upload_stats['failed_uploads']}, 队列={upload_stats['queue_size']}")
    
    async def run(self):
        try:
            devices = self.config.get('devices')
            enabled_devices = [d for d in devices if d['enabled']]
            
            if not enabled_devices:
                logging.error("没有启用的设备")
                return
            
            # 创建检测器和设备管理器
            for device_config in enabled_devices:
                device_name = device_config['name']
                self.detectors[device_name] = TrainDetector(device_name, self.config)
                dm = DeviceManager(device_config, self.data_callback, self.config)
                self.device_managers[device_name] = dm
            
            # 连接所有设备
            tasks = [dm.connect() for dm in self.device_managers.values()]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # 启动后台任务
            background_tasks = [
                asyncio.create_task(self.health_check_loop()),
                asyncio.create_task(self.status_upload_loop())
            ]
            
            for dm in self.device_managers.values():
                background_tasks.append(asyncio.create_task(dm.reconnect_loop()))
            
            # 保持运行
            while self.running:
                await asyncio.sleep(1)
            
            for task in background_tasks:
                task.cancel()
            await asyncio.gather(*background_tasks, return_exceptions=True)
        
        except Exception as e:
            logging.error(f"运行错误: {e}")
            self.led.error_on()
        finally:
            self.cleanup()
    
    def cleanup(self):
        logging.info("正在关闭...")
        for dm in self.device_managers.values():
            dm.disconnect()
        self.uploader.stop()
        self.led.cleanup()
        logging.info("系统已停止")


# ==================== 主程序 ====================
def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else "system_config.json"
    
    manager = SystemManager(config_file)
    
    try:
        asyncio.run(manager.run())
    except KeyboardInterrupt:
        print("\n程序已停止")


if __name__ == "__main__":
    main()
