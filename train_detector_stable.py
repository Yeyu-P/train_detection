#!/usr/bin/env python3
"""
Train Detection System - Production Stable Version with Enhancements
Strict adherence to BlueZ engineering constraints:
- Serial connection (no concurrency)
- Explicit resource management
- Complete error handling and retry
- Unified exit path

NEW Features:
- JSON configuration for all parameters
- Sliding window health detection with percentage trigger
- Non-blocking upload interface for health monitoring
- English comments and logging
"""
import asyncio
import signal
import sys
import time
import os
import csv
import json
import sqlite3
import logging
import subprocess
import aiohttp
from collections import deque
from datetime import datetime
from pathlib import Path
from enum import Enum

from witmotion_device_stable import DeviceModel, DeviceState

# Global config will be loaded from JSON
CONFIG = {}

# ====================================================================
# NEW CONSTANTS FOR Z-AXIS DETECTION AND CALIBRATION
# ====================================================================
# Maximum recording duration (seconds) - hard limit to force stop
MAX_RECORD_SECONDS = 60  # Can be overridden by config

# Z-axis stop threshold (g) - recording stops when ALL devices below this
STOP_THRESHOLD_Z = 0.5  # Can be overridden by config

# Calibration parameters
CALIBRATION_INTERVAL_HOURS = 6  # Auto-calibrate every N hours
CALIBRATION_SAMPLES = 100  # Number of samples to average for calibration
CALIBRATION_DURATION = 2.0  # Duration (seconds) to collect calibration samples
CALIBRATION_VIBRATION_THRESHOLD = 0.3  # If Z-axis variance exceeds this, skip calibration

# Stop condition window size (samples per device)
STOP_WINDOW_SIZE = 50  # Sliding window for checking stop condition

# Configure logging
def setup_logging(log_file):
    """Setup logging with file and console handlers"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)


class IMUManager:
    """
    Single IMU manager - independent state machine
    Responsibilities: connection, reconnection, data reception, exception isolation, health monitoring
    """
    
    def __init__(self, number, name, mac, data_callback, config):
        self.number = number
        self.name = name
        self.mac = mac
        self.data_callback = data_callback
        self.config = config
        
        # Health monitoring parameters from config
        health_config = config.get('health_monitoring', {})
        self.DATA_TIMEOUT = health_config.get('data_timeout', 3.0)
        self.HEALTH_CHECK_INTERVAL = health_config.get('health_check_interval', 2.0)
        self.MAX_CONSECUTIVE_FAILURES = health_config.get('max_consecutive_failures', 3)
        
        # Reconnection parameters from config
        reconnect_config = config.get('reconnection', {})
        self.max_retries = reconnect_config.get('max_retries', 3)
        
        # Device instance
        self.device = None
        
        # P0: Connection mutex lock (prevent race conditions)
        self._connection_lock = asyncio.Lock()
        
        # State
        self.is_ready = False
        self.last_data_time = 0
        self.connection_attempts = 0
        
        # Health monitoring
        self.last_health_check = 0
        self.reconnecting = False  # Prevent concurrent reconnections
        
        # Circular buffer
        self.buffer = deque(maxlen=250)  # 5 seconds @ 50Hz
        self.current_data = {}
        
        logger.info(f"[IMU-{self.number}] Manager initialized")
        print(f"[IMU-{self.number}] Manager initialized")
    
    async def connect(self, retry_count=0):
        """
        Connect device (with retry and failure counting)
        P0: Use lock protection to prevent concurrent connections
        Returns: success (bool)
        """
        # P0: Check lock state, skip if already occupied
        if self._connection_lock.locked():
            logger.warning(f"[IMU-{self.number}] Connection already in progress, skipping")
            return False
        
        async with self._connection_lock:  # P0: Mutual exclusion protection
            if retry_count == 0:
                self.connection_attempts += 1
            
            if self.connection_attempts > self.max_retries:
                logger.error(f"[IMU-{self.number}] Max retries reached")
                print(f"[IMU-{self.number}] Max retries reached")
                return False
            
            # Create device instance
            self.device = DeviceModel(self.name, self.mac, self._device_callback, self.config)
            
            # Try to connect
            success, error_msg = await self.device.connect()
            
            if success:
                self.is_ready = True
                self.connection_attempts = 0  # Reset counter
                self.device.reset_failure()  # Reset device failure count
                logger.info(f"[IMU-{self.number}] Connected successfully")
                print(f"[IMU-{self.number}] Connected successfully")
                return True
            else:
                logger.error(f"[IMU-{self.number}] Connection failed: {error_msg}")
                print(f"[IMU-{self.number}] Connection failed: {error_msg}")
                
                # Increment device failure count
                if self.device:
                    fail_count = self.device.increment_failure()
                else:
                    fail_count = 0
                
                await self.disconnect()
                return False
    
    async def disconnect(self):
        """Disconnect (complete cleanup)"""
        self.is_ready = False
        
        if self.device:
            await self.device.disconnect()
            self.device = None
        
        print(f"[IMU-{self.number}] Disconnected")
    
    def _device_callback(self, device_model):
        """Device data callback"""
        current_time = time.time()
        self.last_data_time = current_time
        
        data = device_model.deviceData.copy()
        self.current_data = data
        
        # Add to buffer
        self.buffer.append((current_time, data))
        
        # Callback to detector
        if self.data_callback:
            self.data_callback(self.number, current_time, data)
    
    def get_buffer_data(self):
        """Get buffer data"""
        return list(self.buffer)
    
    def clear_buffer(self):
        """Clear buffer"""
        self.buffer.clear()
    
    async def check_and_reconnect(self):
        """
        Health check + automatic reconnection
        P0: Use lock protection to prevent competition with main connection flow
        
        Detection conditions:
        - Device in READY state
        - But no data received for DATA_TIMEOUT seconds (dead connection)
        
        Reconnection flow:
        - stop_notify -> disconnect -> cleanup -> delay -> reconnect
        - Serial execution, non-blocking for other IMUs
        - No infinite retry after failure
        
        Returns: reconnected (bool)
        """
        current_time = time.time()
        
        # Prevent concurrent reconnections
        if self.reconnecting:
            return False
        
        # P0: Check connection lock, skip if other connection operations
        if self._connection_lock.locked():
            logger.debug(f"[IMU-{self.number}] Connection lock busy, skipping health check")
            return False
        
        # Health check interval
        if current_time - self.last_health_check < self.HEALTH_CHECK_INTERVAL:
            return False
        
        self.last_health_check = current_time
        
        # Not READY state, don't check
        if not self.is_ready or not self.device:
            return False
        
        # Perform health check
        is_healthy, reason = self.device.check_health(self.DATA_TIMEOUT)
        
        # NEW: Update sliding window
        self.device.update_health_window(is_healthy)
        
        # NEW: Check sliding window
        window_healthy, window_reason, window_stats = self.device.check_sliding_window_health()
        
        if is_healthy and window_healthy:
            return False
        
        # Detected dead connection or sliding window failure, start reconnection flow
        final_reason = reason if not is_healthy else window_reason
        logger.warning(
            f"[IMU-{self.number}] RECONNECT triggered: {final_reason}"
        )
        print(f"[IMU-{self.number}] Detected problem, reconnecting...")
        
        self.reconnecting = True
        
        try:
            # P0: Use lock to protect reconnection flow
            async with self._connection_lock:
                # Step 1: Complete disconnect
                logger.info(f"[IMU-{self.number}] Step 1: Disconnecting...")
                await self.disconnect()
                
                # Step 2: Delay (let BLE stack stabilize)
                await asyncio.sleep(2.0)
                
                # Step 3: Reconnect (lock already held, won't acquire again internally)
                logger.info(f"[IMU-{self.number}] Step 2: Reconnecting...")
                
                # Temporarily call internal connection logic without acquiring lock again
                if self.connection_attempts > self.max_retries:
                    logger.error(f"[IMU-{self.number}] Max retries reached")
                    return False
                
                self.device = DeviceModel(self.name, self.mac, self._device_callback, self.config)
                success, error_msg = await self.device.connect()
                
                if success:
                    self.is_ready = True
                    self.connection_attempts = 0
                    self.device.reset_failure()
                    logger.info(f"[IMU-{self.number}] Reconnection successful")
                    print(f"[IMU-{self.number}] Reconnected")
                    return True
                else:
                    logger.error(f"[IMU-{self.number}] Reconnection failed: {error_msg}")
                    print(f"[IMU-{self.number}] Reconnection failed")
                    if self.device:
                        self.device.increment_failure()
                    await self.disconnect()
                    return False
                
        except Exception as e:
            logger.error(f"[IMU-{self.number}] Reconnection error: {e}")
            return False
        finally:
            self.reconnecting = False
    
    def should_trigger_os_cleanup(self):
        """
        Determine if OS-level cleanup should be triggered
        
        Condition: consecutive failures >= MAX_CONSECUTIVE_FAILURES
        """
        if not self.device:
            return False
        
        return self.device.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES
    
    def get_status_dict(self):
        """
        NEW: Get IMU status as dictionary for upload
        
        Returns: dict with IMU status
        """
        status = {
            'number': self.number,
            'name': self.name,
            'mac': self.mac,
            'is_ready': self.is_ready,
            'reconnecting': self.reconnecting,
            'connection_attempts': self.connection_attempts,
            'buffer_size': len(self.buffer),
            'current_data': self.current_data.copy() if self.current_data else {}
        }
        
        # Add device health stats if available
        if self.device:
            status['device_health'] = self.device.get_health_stats()
        
        return status


class EventUploader:
    """
    HTTP event uploader for train detection events
    All uploads are asynchronous and non-blocking
    Network failures are isolated and only logged
    Can be completely disabled via config
    """

    def __init__(self, config):
        upload_config = config.get('event_upload', {})

        self.enabled = upload_config.get('enabled', False)
        self.base_url = upload_config.get('base_url', 'http://127.0.0.1:8000')

        endpoints = upload_config.get('endpoints', {})
        self.endpoint_event_start = endpoints.get('event_start', '/api/events/start')
        self.endpoint_event_end = endpoints.get('event_end', '/api/events/end')
        self.endpoint_summary = endpoints.get('summary', '/api/events/summary')
        self.endpoint_warning = endpoints.get('warning', '/api/warnings')

        self.timeout = upload_config.get('timeout_sec', 2.0)

        # Statistics
        self.upload_count = 0
        self.upload_failures = 0

        if self.enabled:
            logger.info(f"Event uploader enabled: {self.base_url}")
            print(f"Event uploader enabled: {self.base_url}")

    async def upload_event_start(self, event_id, trigger_time, trigger_device, z_magnitude):
        """Upload train detection start event (non-blocking, fire-and-forget)"""
        if not self.enabled:
            return

        try:
            data = {
                'event_type': 'train_detected',
                'event_id': event_id,
                'trigger_time': trigger_time,
                'trigger_device': trigger_device,
                'z_magnitude': z_magnitude
            }

            url = f"{self.base_url}{self.endpoint_event_start}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.upload_count += 1
                        logger.debug(f"Event start uploaded: {event_id}")
                    else:
                        self.upload_failures += 1
                        logger.warning(f"Event start upload failed: HTTP {response.status}")

        except asyncio.TimeoutError:
            self.upload_failures += 1
            logger.debug(f"Event start upload timeout: {event_id}")
        except Exception as e:
            self.upload_failures += 1
            logger.debug(f"Event start upload error: {e}")

    async def upload_event_end(self, event_id, end_time, duration, max_acceleration):
        """Upload train detection end event (non-blocking, fire-and-forget)"""
        if not self.enabled:
            return

        try:
            data = {
                'event_type': 'train_passed',
                'event_id': event_id,
                'end_time': end_time,
                'duration': duration,
                'max_acceleration': max_acceleration
            }

            url = f"{self.base_url}{self.endpoint_event_end}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.upload_count += 1
                        logger.debug(f"Event end uploaded: {event_id}")
                    else:
                        self.upload_failures += 1
                        logger.warning(f"Event end upload failed: HTTP {response.status}")

        except asyncio.TimeoutError:
            self.upload_failures += 1
            logger.debug(f"Event end upload timeout: {event_id}")
        except Exception as e:
            self.upload_failures += 1
            logger.debug(f"Event end upload error: {e}")

    async def upload_event_summary(self, event_id, summary_data):
        """Upload event summary with per-device statistics (non-blocking, fire-and-forget)"""
        if not self.enabled:
            return

        try:
            data = {
                'event_type': 'event_summary',
                'event_id': event_id,
                'devices': summary_data
            }

            url = f"{self.base_url}{self.endpoint_summary}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.upload_count += 1
                        logger.debug(f"Event summary uploaded: {event_id}")
                    else:
                        self.upload_failures += 1
                        logger.warning(f"Event summary upload failed: HTTP {response.status}")

        except asyncio.TimeoutError:
            self.upload_failures += 1
            logger.debug(f"Event summary upload timeout: {event_id}")
        except Exception as e:
            self.upload_failures += 1
            logger.debug(f"Event summary upload error: {e}")

    async def upload_warning(self, warning_type, device_number, device_name, message, severity='medium'):
        """Upload system warning/alert (non-blocking, fire-and-forget)"""
        if not self.enabled:
            return

        try:
            data = {
                'warning_type': warning_type,
                'timestamp': datetime.now().isoformat(),
                'device_number': device_number,
                'device_name': device_name,
                'message': message,
                'severity': severity
            }

            url = f"{self.base_url}{self.endpoint_warning}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.upload_count += 1
                        logger.debug(f"Warning uploaded: {warning_type}")
                    else:
                        self.upload_failures += 1
                        logger.warning(f"Warning upload failed: HTTP {response.status}")

        except asyncio.TimeoutError:
            self.upload_failures += 1
            logger.debug(f"Warning upload timeout: {warning_type}")
        except Exception as e:
            self.upload_failures += 1
            logger.debug(f"Warning upload error: {e}")


class GoogleDriveUploader:
    """
    Google Drive uploader for automatic event data backup
    Uploads event folders to Google Drive for long-term storage
    Uses service account for unattended operation
    """

    def __init__(self, config):
        self.config = config
        gdrive_config = config.get('google_drive', {})

        self.enabled = gdrive_config.get('enabled', False)
        self.credentials_file = gdrive_config.get('credentials_file', 'service_account.json')
        self.folder_id = gdrive_config.get('folder_id', '')
        self.upload_delay = gdrive_config.get('upload_delay_seconds', 5)

        self.upload_count = 0
        self.upload_failures = 0

        # Try to initialize Google Drive API
        self.service = None
        if self.enabled:
            self._initialize_drive_service()

    def _initialize_drive_service(self):
        """Initialize Google Drive API service"""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if not os.path.exists(self.credentials_file):
                logger.error(f"Google Drive credentials file not found: {self.credentials_file}")
                print(f"Google Drive: Credentials file not found, upload disabled")
                self.enabled = False
                return

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )

            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive uploader initialized successfully")
            print(f"Google Drive uploader enabled: Folder ID {self.folder_id}")

        except ImportError:
            logger.error("Google Drive libraries not installed. Run: pip install google-api-python-client google-auth")
            print("Google Drive: Required libraries not installed, upload disabled")
            self.enabled = False
        except Exception as e:
            logger.error(f"Google Drive initialization error: {e}")
            print(f"Google Drive initialization failed: {e}")
            self.enabled = False

    async def upload_event_folder(self, event_dir_path):
        """Upload event files directly to Google Drive (non-blocking)"""
        if not self.enabled or not self.service:
            return

        try:
            from googleapiclient.http import MediaFileUpload

            event_dir = Path(event_dir_path)
            if not event_dir.exists():
                logger.warning(f"Event directory not found: {event_dir}")
                return

            # Wait a bit to ensure all files are written
            await asyncio.sleep(self.upload_delay)

            # Get event name prefix (e.g., "event_20251226_230829")
            event_prefix = event_dir.name

            # Upload all files directly to the shared folder with event prefix
            uploaded_files = 0
            for file_path in event_dir.iterdir():
                if file_path.is_file():
                    # Add event prefix to filename: event_20251226_230829_metadata.json
                    prefixed_name = f"{event_prefix}_{file_path.name}"

                    file_metadata = {
                        'name': prefixed_name,
                        'parents': [self.folder_id] if self.folder_id else []
                    }

                    media = MediaFileUpload(str(file_path), resumable=True)

                    # Use a wrapper function to capture the current media object
                    def upload_file(metadata=file_metadata, media_obj=media):
                        return self.service.files().create(
                            body=metadata,
                            media_body=media_obj,
                            fields='id'
                        ).execute()

                    await asyncio.get_event_loop().run_in_executor(None, upload_file)

                    uploaded_files += 1
                    logger.debug(f"Uploaded to Google Drive: {prefixed_name}")

            self.upload_count += 1
            logger.info(f"Google Drive upload complete: {event_prefix} ({uploaded_files} files)")
            print(f"   Uploaded to Google Drive: {event_prefix} ({uploaded_files} files)")

        except Exception as e:
            self.upload_failures += 1
            logger.error(f"Google Drive upload error: {e}")
            print(f"   Google Drive upload failed: {e}")


class HealthUploader:
    """
    NEW: Non-blocking health data uploader
    Uploads IMU health statistics to local/LAN endpoint
    Failures do not affect BLE operations
    """
    
    def __init__(self, config):
        self.config = config
        upload_config = config.get('upload', {})
        
        self.enabled = upload_config.get('enabled', False)
        self.host = upload_config.get('host', 'localhost')
        self.port = upload_config.get('port', 8080)
        self.endpoint = upload_config.get('endpoint', '/api/imu/status')
        self.interval = upload_config.get('interval', 30)
        self.timeout = upload_config.get('timeout', 5.0)
        self.retry_on_failure = upload_config.get('retry_on_failure', False)
        
        self.url = f"http://{self.host}:{self.port}{self.endpoint}"
        self.last_upload_time = 0
        self.upload_count = 0
        self.upload_failures = 0
        
        if self.enabled:
            logger.info(f"Health uploader enabled: {self.url}")
            print(f"Health uploader enabled: {self.url}")
    
    async def upload_health_data(self, imu_managers, system_stats):
        """
        Upload health data (non-blocking)
        
        Args:
            imu_managers: dict of IMU managers
            system_stats: system statistics dict
        
        Returns: success (bool)
        """
        if not self.enabled:
            return True
        
        current_time = time.time()
        
        # Check interval
        if current_time - self.last_upload_time < self.interval:
            return True
        
        try:
            # Collect health data
            health_data = {
                'timestamp': datetime.now().isoformat(),
                'system': system_stats,
                'imus': []
            }
            
            for num, imu in imu_managers.items():
                health_data['imus'].append(imu.get_status_dict())
            
            # Upload with timeout
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.url,
                    json=health_data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.upload_count += 1
                        self.last_upload_time = current_time
                        logger.debug(f"Health data uploaded successfully (count: {self.upload_count})")
                        return True
                    else:
                        logger.warning(f"Upload failed with status {response.status}")
                        self.upload_failures += 1
                        return False
        
        except asyncio.TimeoutError:
            logger.warning("Health upload timeout")
            self.upload_failures += 1
            return False
        except Exception as e:
            # Do not log at ERROR level to avoid noise
            logger.debug(f"Health upload error: {e}")
            self.upload_failures += 1
            return False


class TrainDetector:
    """
    Train detection system - central coordinator
    Responsibilities:
    - Serial connection of all IMUs
    - Detect train passage
    - Data recording
    - Exception isolation
    - Unified exit
    - NEW: Health monitoring upload
    """
    
    def __init__(self, config_file="config.json"):
        # Load configuration
        self.config = self._load_config_file(config_file)
        
        # Output configuration
        output_config = self.config.get('output', {})
        self.output_dir = Path(output_config.get('directory', 'train_events'))
        self.output_dir.mkdir(exist_ok=True)
        
        log_file = output_config.get('log_file', 'train_detector.log')
        setup_logging(log_file)
        
        # IMU managers
        self.imus = {}  # number -> IMUManager
        
        # P0: Global throttling (prevent reconnection storm)
        reconnect_config = self.config.get('reconnection', {})
        self.last_reconnect_time = 0
        self.reconnect_global_cooldown = reconnect_config.get('global_cooldown', 5.0)
        
        # OS cleanup state tracking
        self.os_cleanup_history = {}  # mac -> last_cleanup_time
        self.OS_CLEANUP_COOLDOWN = reconnect_config.get('os_cleanup_cooldown', 600)
        
        # P0: Global OS cleanup throttling
        self.last_os_cleanup_global = 0
        self.os_cleanup_global_cooldown = reconnect_config.get('os_cleanup_global_cooldown', 300)
        self.ble_operations_paused = False  # BLE operations pause flag (during OS cleanup)
        
        # Detection parameters from config
        detection_config = self.config.get('detection', {})
        self.threshold = detection_config.get('threshold', 2.0)
        self.min_duration = detection_config.get('min_duration', 1.0)
        self.post_trigger_duration = detection_config.get('post_trigger_duration', 5.0)

        # NEW: Z-axis specific parameters
        self.max_record_seconds = detection_config.get('max_record_seconds', MAX_RECORD_SECONDS)
        self.stop_threshold_z = detection_config.get('stop_threshold_z', STOP_THRESHOLD_Z)

        # Detection state
        self.running = False
        self.recording = False
        self.trigger_time = None
        self.trigger_device = None
        self.event_data = {}
        self.event_id = None

        # NEW: Calibration state
        calibration_config = self.config.get('calibration', {})
        self.calibration_interval_hours = calibration_config.get('interval_hours', CALIBRATION_INTERVAL_HOURS)
        self.calibration_samples = calibration_config.get('samples', CALIBRATION_SAMPLES)
        self.calibration_duration = calibration_config.get('duration', CALIBRATION_DURATION)
        self.calibration_vibration_threshold = calibration_config.get('vibration_threshold', CALIBRATION_VIBRATION_THRESHOLD)
        self.z_axis_offset = {}  # device_number -> calibration offset
        self.last_calibration_time = 0
        self.calibrating = False  # Flag to prevent concurrent calibration

        # NEW: Sliding window for Z-axis stop condition (per device)
        self.stop_window_size = detection_config.get('stop_window_size', STOP_WINDOW_SIZE)
        self.z_stop_windows = {}  # device_number -> deque of Z-axis values
        
        # Database
        db_name = output_config.get('db_name', 'events.db')
        self.db_path = self.output_dir / db_name
        self._init_database()
        
        # Statistics
        self.stats = {
            'total_events': 0,
            'last_event_time': None,
            'uptime_start': time.time(),
            'total_reconnects': 0,
            'total_os_cleanups': 0
        }
        
        # NEW: Health uploader
        self.health_uploader = HealthUploader(self.config)

        # NEW: Event uploader (can be disabled via config)
        self.event_uploader = EventUploader(self.config)

        # NEW: Google Drive uploader (can be disabled via config)
        self.gdrive_uploader = GoogleDriveUploader(self.config)

        # NEW: Save operation lock (prevent race conditions)
        self._save_lock = asyncio.Lock()
        
        # Signal handlers
        self._setup_signal_handlers()
        
        logger.info("=" * 60)
        logger.info("Train Detection System - Stable Version with Enhancements")
        logger.info("=" * 60)
        print("=" * 60)
        print("Train Detection System - Stable Version with Enhancements")
        print("=" * 60)
        print(f"Config file: {config_file}")
        print(f"Output directory: {self.output_dir}")
        print(f"Detection threshold: {self.threshold}g")
        print("=" * 60)
    
    def _load_config_file(self, config_file):
        """Load configuration from JSON file"""
        if not os.path.exists(config_file):
            logger.error(f"Config file not found: {config_file}")
            print(f"Config file not found: {config_file}")
            sys.exit(1)
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                logger.info(f"Configuration loaded from {config_file}")
                return config
        except Exception as e:
            logger.error(f"Config load error: {e}")
            print(f"Config load error: {e}")
            sys.exit(1)
    
    def _setup_signal_handlers(self):
        """Setup signal handlers (unified exit path)"""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _init_database(self):
        """Initialize database with migration support"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='events'
        """)
        
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # Check column count to detect schema mismatch
            cursor.execute("PRAGMA table_info(events)")
            columns = cursor.fetchall()
            
            if len(columns) != 9:
                logger.warning(f"Database schema mismatch: found {len(columns)} columns, expected 9")
                logger.warning("Backing up old table and creating new one")
                
                # Backup old table
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                try:
                    cursor.execute(f"ALTER TABLE events RENAME TO events_backup_{timestamp}")
                    logger.info(f"Old table renamed to events_backup_{timestamp}")
                    table_exists = False
                except sqlite3.Error as e:
                    logger.error(f"Failed to backup old table: {e}")
                    print(f"ERROR: Database schema mismatch. Please delete {self.db_path} and restart.")
                    conn.close()
                    return
        
        if not table_exists:
            cursor.execute('''
                CREATE TABLE events (
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
            logger.info("Events table created successfully")
        
        conn.commit()
        conn.close()
    
    async def _os_level_ble_cleanup(self, mac_address):
        """
        OS-level BLE cleanup (extreme cases)
        P0: Globally pause all BLE operations to prevent conflicts
        
        Trigger conditions:
        - Same device consecutive failures >= MAX_CONSECUTIVE_FAILURES
        - Time since last cleanup >= OS_CLEANUP_COOLDOWN seconds
        
        Operations:
        1. Pause all BLE operations
        2. Try bluetoothctl remove <MAC>
        3. If failed, try hciconfig hci0 reset (more aggressive)
        4. Cool down and resume BLE operations
        
        Constraints:
        - Only triggered in extreme cases
        - Has cooldown time
        - Logged
        - Not executed frequently
        """
        current_time = time.time()
        
        # Check cooldown time
        if mac_address in self.os_cleanup_history:
            last_cleanup = self.os_cleanup_history[mac_address]
            elapsed = current_time - last_cleanup
            if elapsed < self.OS_CLEANUP_COOLDOWN:
                logger.warning(
                    f"OS cleanup for {mac_address} skipped "
                    f"(cooldown: {elapsed:.0f}s / {self.OS_CLEANUP_COOLDOWN}s)"
                )
                return False
        
        logger.critical(
            f"TRIGGERING OS-LEVEL BLE CLEANUP for {mac_address}"
        )
        print(f"\nOS-level BLE cleanup for {mac_address}...")
        
        # P0: Pause all BLE operations
        logger.warning("Pausing all BLE operations...")
        print("Pausing all BLE operations...")
        self.ble_operations_paused = True
        
        # P0: Wait for current operations to complete
        await asyncio.sleep(2.0)
        
        success = False
        
        try:
            # Method 1: bluetoothctl remove (safer)
            logger.info(f"Attempting: bluetoothctl remove {mac_address}")
            
            result = subprocess.run(
                ['bluetoothctl', 'remove', mac_address],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info(f"bluetoothctl remove successful")
                success = True
            else:
                logger.warning(
                    f"bluetoothctl remove failed: {result.stderr}"
                )
                
                # Method 2: hciconfig reset (more aggressive, affects all devices)
                logger.warning("Attempting fallback: hciconfig hci0 reset")
                
                result = subprocess.run(
                    ['sudo', 'hciconfig', 'hci0', 'reset'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    logger.info("hciconfig reset successful")
                    success = True
                    # P0: Longer cooldown after reset
                    logger.info("Cooling down after hciconfig reset (10s)...")
                    await asyncio.sleep(10.0)
                else:
                    logger.error(f"hciconfig reset failed: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            logger.error("OS cleanup command timeout")
        except FileNotFoundError as e:
            logger.error(f"Command not found: {e}")
        except Exception as e:
            logger.error(f"OS cleanup error: {e}")
        
        finally:
            # P0: Always resume BLE operations
            logger.info("Cooling down before resuming BLE operations (5s)...")
            await asyncio.sleep(5.0)
            
            self.ble_operations_paused = False
            logger.info("BLE operations resumed")
            print("BLE operations resumed\n")
        
        # Record cleanup history
        if success:
            self.os_cleanup_history[mac_address] = current_time
            self.stats['total_os_cleanups'] += 1
            logger.info(
                f"OS cleanup completed for {mac_address} "
                f"(total: {self.stats['total_os_cleanups']})"
            )
            print(f"OS-level cleanup completed\n")
        else:
            logger.error(f"OS cleanup failed for {mac_address}")
            print(f"OS-level cleanup failed\n")
        
        return success
    
    async def start(self):
        """
        Start system
        1. Load configuration
        2. Serial connection of all IMUs (critical!)
        3. Start detection
        """
        print("\nLoading configuration...")
        
        config_devices = self.config.get('devices', [])
        enabled_devices = [d for d in config_devices if d.get('enabled', True)]
        
        if not enabled_devices:
            print("No devices configured")
            return False
        
        print(f"Found {len(enabled_devices)} device(s) in config\n")
        
        # Create IMU managers
        for dev_config in enabled_devices:
            number = dev_config['number']
            name = dev_config['name']
            mac = dev_config['mac']
            
            imu = IMUManager(number, name, mac, self._data_callback, self.config)
            self.imus[number] = imu
        
        # Serial connection of all devices (critical! No concurrency!)
        print("=" * 60)
        print("Connecting devices SERIALLY...")
        print("=" * 60)
        
        connected_count = 0
        for number in sorted(self.imus.keys()):
            imu = self.imus[number]
            
            print(f"\n[{number}/{len(self.imus)}] Connecting {imu.name}...")
            
            success = await imu.connect()
            
            if success:
                connected_count += 1
                # Wait a bit after successful connection (stability)
                await asyncio.sleep(1.0)
            else:
                print(f"Skipping {imu.name} (will retry later)")
                await asyncio.sleep(0.5)
        
        print("\n" + "=" * 60)
        print(f"Connection Summary: {connected_count}/{len(self.imus)} devices ready")
        print("=" * 60)
        
        if connected_count == 0:
            print("No devices connected")
            return False
        
        # Start detection
        self.running = True
        print("\nDetection started!")
        print(f"Monitoring {connected_count} device(s)...\n")

        # NEW: Perform initial calibration
        await self._perform_calibration()

        return True

    async def _perform_calibration(self):
        """
        NEW: Perform Z-axis calibration for all connected devices

        Calibration process:
        1. Check for vibration - skip if detected
        2. Collect Z-axis samples for CALIBRATION_DURATION
        3. Calculate average Z-axis offset
        4. Store offset for runtime subtraction

        Safety: Only calibrates when no vibration is detected
        """
        if self.calibrating:
            logger.warning("Calibration already in progress, skipping")
            return

        self.calibrating = True
        current_time = time.time()

        try:
            print("\n" + "=" * 60)
            print("Z-AXIS CALIBRATION")
            print("=" * 60)
            logger.info("Starting Z-axis calibration")

            # Step 1: Collect samples from all devices to check for vibration
            print("Checking for vibration before calibration...")
            vibration_check_samples = {}

            for num, imu in self.imus.items():
                if imu.is_ready:
                    vibration_check_samples[num] = []

            # Collect 1 second of samples to check for vibration
            start_time = time.time()
            while time.time() - start_time < 1.0:
                for num in vibration_check_samples.keys():
                    imu = self.imus[num]
                    if imu.current_data:
                        z_val = imu.current_data.get('AccZ', 0)
                        vibration_check_samples[num].append(z_val)
                await asyncio.sleep(0.02)  # 50Hz sampling

            # Check variance - if too high, skip calibration
            for num, samples in vibration_check_samples.items():
                if len(samples) < 10:
                    print(f"  IMU-{num}: Not enough samples, skipping calibration")
                    logger.warning(f"IMU-{num} calibration skipped: insufficient samples")
                    # NEW: Set timestamp to allow retry later
                    self.last_calibration_time = current_time - (self.calibration_interval_hours * 3600 - 300)  # Retry in 5 minutes
                    self.calibrating = False
                    return

                # Calculate variance
                mean_z = sum(samples) / len(samples)
                variance = sum((x - mean_z) ** 2 for x in samples) / len(samples)
                std_dev = variance ** 0.5

                if std_dev > self.calibration_vibration_threshold:
                    print(f"  Vibration detected (std: {std_dev:.3f}g), postponing calibration")
                    logger.warning(f"Calibration postponed: vibration detected (std: {std_dev:.3f}g)")
                    # NEW: Set timestamp even if skipped, to allow retry later
                    self.last_calibration_time = current_time - (self.calibration_interval_hours * 3600 - 300)  # Retry in 5 minutes
                    self.calibrating = False
                    return

            print("  No vibration detected, proceeding with calibration")

            # Step 2: Collect calibration samples
            print(f"Collecting {self.calibration_samples} samples from each device...")
            calibration_samples = {}

            for num, imu in self.imus.items():
                if imu.is_ready:
                    calibration_samples[num] = []

            # Collect samples for CALIBRATION_DURATION
            start_time = time.time()
            sample_count = 0
            while sample_count < self.calibration_samples:
                for num in calibration_samples.keys():
                    imu = self.imus[num]
                    if imu.current_data and len(calibration_samples[num]) < self.calibration_samples:
                        z_val = imu.current_data.get('AccZ', 0)
                        calibration_samples[num].append(z_val)

                # Check if all devices have enough samples
                if all(len(samples) >= self.calibration_samples for samples in calibration_samples.values()):
                    break

                await asyncio.sleep(0.02)  # 50Hz sampling

                # Timeout check
                if time.time() - start_time > self.calibration_duration * 2:
                    print("  Calibration timeout, using available samples")
                    break

            # Step 3: Calculate offsets
            for num, samples in calibration_samples.items():
                if len(samples) == 0:
                    logger.warning(f"IMU-{num}: No calibration samples, using offset 0")
                    self.z_axis_offset[num] = 0.0
                    continue

                # Calculate average Z-axis offset
                offset = sum(samples) / len(samples)
                self.z_axis_offset[num] = offset

                print(f"  IMU-{num}: Offset = {offset:.3f}g (from {len(samples)} samples)")
                logger.info(f"IMU-{num} Z-axis offset: {offset:.3f}g")

            # Initialize stop windows for all devices
            for num in self.imus.keys():
                self.z_stop_windows[num] = deque(maxlen=self.stop_window_size)

            self.last_calibration_time = current_time
            print("Calibration complete!")
            print("=" * 60 + "\n")
            logger.info("Z-axis calibration completed successfully")

        except Exception as e:
            logger.error(f"Calibration error: {e}")
            print(f"Calibration error: {e}")
        finally:
            self.calibrating = False

    async def shutdown(self):
        """
        Unified exit path
        1. Stop detection
        2. Save current recording
        3. Serial disconnect all IMUs
        """
        if not self.running:
            return
        
        print("\n" + "=" * 60)
        print("Shutting down...")
        print("=" * 60)
        
        self.running = False
        
        # Save recording in progress
        if self.recording:
            print("Saving current recording...")
            await self._end_recording()
        
        # Serial disconnect all devices
        print("\nDisconnecting devices serially...")
        for number in sorted(self.imus.keys()):
            imu = self.imus[number]
            if imu.is_ready:
                await imu.disconnect()
                await asyncio.sleep(0.5)  # Give system time to clean up
        
        print("\nShutdown complete")
        print("=" * 60)
    
    def _data_callback(self, device_number, timestamp, data):
        """
        IMU data callback (detection logic)

        NEW BEHAVIOR:
        - Uses ONLY Z-axis for detection (with calibration offset)
        - Global trigger: ANY device detection starts ALL devices recording
        - During recording: stop vibration detection, only check stop conditions
        - Stop conditions: ALL devices Z-axis below threshold + max duration check
        """
        if not self.running:
            return

        # Get Z-axis value and apply calibration offset
        acc_z_raw = data.get('AccZ', 0)
        offset = self.z_axis_offset.get(device_number, 0.0)
        acc_z = acc_z_raw - offset  # Calibrated Z-axis

        # DETECTION MODE: Check for vibration using Z-axis only
        if not self.recording:
            # Use absolute value of Z-axis to detect vibration in both directions
            z_magnitude = abs(acc_z)

            if z_magnitude > self.threshold:
                # NEW: Global trigger - start ALL devices recording
                self._trigger_detection(device_number, timestamp, z_magnitude)

        # RECORDING MODE: Collect data and check stop conditions
        else:
            # Record data from all devices
            if device_number not in self.event_data:
                self.event_data[device_number] = []
            self.event_data[device_number].append((timestamp, data.copy()))

            # NEW: Update Z-axis stop window for this device
            if device_number not in self.z_stop_windows:
                self.z_stop_windows[device_number] = deque(maxlen=self.stop_window_size)
            self.z_stop_windows[device_number].append(abs(acc_z))  # Store absolute calibrated Z

            # Check stop conditions
            elapsed = timestamp - self.trigger_time

            # NEW: Check maximum recording duration (hard limit)
            if elapsed >= self.max_record_seconds:
                logger.warning(f"Maximum recording duration reached ({self.max_record_seconds}s), force stopping")
                print(f"\n  Maximum duration reached, stopping recording...")
                asyncio.create_task(self._end_recording())
                return

            # NEW: Check if ALL devices have Z-axis below threshold
            if self._check_stop_condition():
                logger.info("Stop condition met: all devices Z-axis below threshold")
                print(f"\n  All devices stable, stopping recording...")
                asyncio.create_task(self._end_recording())
                return
    
    def _check_stop_condition(self):
        """
        NEW: Check if recording should stop

        Stop condition: ALL devices must have Z-axis values in their sliding windows
        that are ALL below the stop threshold

        Returns: True if should stop, False otherwise
        """
        # Need at least one device to check
        if not self.z_stop_windows:
            return False

        # NEW: Track if we checked at least one device
        checked_devices = 0

        # Check each connected device
        for num, imu in self.imus.items():
            if not imu.is_ready:
                continue  # Skip disconnected devices

            # Device must have a stop window
            if num not in self.z_stop_windows:
                return False  # Can't stop if we don't have data from all devices

            window = self.z_stop_windows[num]

            # Window must be full (or at least have some samples)
            if len(window) == 0:
                return False  # Can't stop without any samples

            # NEW: Count this device as checked
            checked_devices += 1

            # Check if ALL values in window are below threshold
            max_z_in_window = max(window)
            if max_z_in_window >= self.stop_threshold_z:
                return False  # This device still has vibration

        # NEW: If all devices disconnected during recording, can't stop safely
        if checked_devices == 0:
            return False

        # All devices have all values below threshold
        return True

    def _trigger_detection(self, device_number, timestamp, magnitude):
        """
        Trigger detection

        NEW: Global trigger - starts recording for ALL devices
        """
        # Prevent triggering if already recording (avoid data overwrite)
        if self.recording:
            logger.warning(f"Skipping trigger from IMU-{device_number}: already recording")
            return

        self.recording = True
        self.trigger_time = timestamp
        self.trigger_device = device_number

        # Generate unique event ID with milliseconds and counter
        base_id = datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S_%f')[:19]  # Include microseconds, truncate to milliseconds

        # Ensure uniqueness by adding counter if needed
        event_id = base_id
        counter = 1
        while (self.output_dir / f"event_{event_id}").exists():
            event_id = f"{base_id}_{counter}"
            counter += 1

        self.event_id = event_id
        self.event_data = {}

        # NEW: Clear Z-axis stop windows for fresh start
        for num in self.z_stop_windows.keys():
            self.z_stop_windows[num].clear()

        print(f"\nVIBRATION DETECTED! (Z-axis)")
        print(f"   Triggered by: IMU-{device_number}")
        print(f"   Time: {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"   Z-axis magnitude: {magnitude:.3f}g")
        print(f"   Recording ALL devices (max {self.max_record_seconds}s)...")

        # NEW: Upload event start (non-blocking, fire-and-forget)
        asyncio.create_task(
            self.event_uploader.upload_event_start(
                event_id,
                datetime.fromtimestamp(timestamp).isoformat(),
                device_number,
                magnitude
            )
        )

        # NEW: Collect buffer data from ALL devices (global trigger)
        for num, imu in self.imus.items():
            if imu.is_ready:
                buffer_data = imu.get_buffer_data()
                if buffer_data:
                    self.event_data[num] = buffer_data.copy()
                    print(f"   Captured {len(buffer_data)} samples from IMU-{num}")
    
    async def _end_recording(self):
        """
        End recording and save (async to prevent blocking)
        Uses executor for file I/O to avoid blocking event loop
        Protected by lock to prevent race conditions
        """
        # Use lock to prevent concurrent save operations
        async with self._save_lock:
            if not self.recording:
                return
            
            # Mark as not recording immediately to allow new detections
            self.recording = False
            
            duration = time.time() - self.trigger_time
            print(f"\nSaving event data...")
            print(f"   Duration: {duration:.2f}s")
            
            # Copy data to avoid race conditions
            event_id = self.event_id
            trigger_device = self.trigger_device
            trigger_time = self.trigger_time
            event_data_copy = {k: list(v) for k, v in self.event_data.items()}
            
            # Clear event data immediately
            self.event_data = {}
            
            # Save in executor to avoid blocking (with error handling)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self._save_event_data_sync,
                    event_id,
                    trigger_device,
                    trigger_time,
                    duration,
                    event_data_copy
                )
            except Exception as e:
                logger.error(f"Background save error: {e}")
                print(f"   Background save failed: {e}")
                return
            
            # Update statistics
            self.stats['total_events'] += 1
            self.stats['last_event_time'] = trigger_time

            # NEW: Calculate max acceleration and prepare summary data for upload
            max_acc = 0.0
            summary_devices = []

            for dev_num, data_list in event_data_copy.items():
                if not data_list:
                    continue

                # Calculate max acceleration for event_end
                for ts, data in data_list:
                    acc = (data.get('AccX', 0)**2 +
                          data.get('AccY', 0)**2 +
                          data.get('AccZ', 0)**2)**0.5
                    max_acc = max(max_acc, acc)

                # Calculate Z-axis statistics for summary
                z_values = []
                for ts, data in data_list:
                    acc_z_raw = data.get('AccZ', 0)
                    offset = self.z_axis_offset.get(dev_num, 0.0)
                    z_values.append(abs(acc_z_raw - offset))

                max_z = max(z_values) if z_values else 0.0
                avg_z = sum(z_values) / len(z_values) if z_values else 0.0

                summary_devices.append({
                    'device_number': dev_num,
                    'sample_count': len(data_list),
                    'max_z_acceleration': round(max_z, 3),
                    'avg_z_acceleration': round(avg_z, 3),
                    'calibration_offset': round(self.z_axis_offset.get(dev_num, 0.0), 3)
                })

            # NEW: Upload event end (non-blocking, fire-and-forget)
            asyncio.create_task(
                self.event_uploader.upload_event_end(
                    event_id,
                    datetime.fromtimestamp(trigger_time + duration).isoformat(),
                    duration,
                    round(max_acc, 3)
                )
            )

            # NEW: Upload event summary (non-blocking, fire-and-forget)
            asyncio.create_task(
                self.event_uploader.upload_event_summary(
                    event_id,
                    summary_devices
                )
            )

            # NEW: Upload to Google Drive (non-blocking, fire-and-forget)
            asyncio.create_task(
                self.gdrive_uploader.upload_event_folder(
                    str(self.output_dir / f"event_{event_id}")
                )
            )
    
    def _save_event_data_sync(self, event_id, trigger_device, trigger_time, duration, event_data_copy):
        """
        Synchronous file I/O (runs in executor)
        This prevents blocking the async event loop
        Includes robust error handling and disk space check
        """
        try:
            # Check available disk space
            try:
                stat = os.statvfs(self.output_dir)
                available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
                
                if available_mb < 100:  # Less than 100MB
                    logger.warning(f"Low disk space: {available_mb:.1f}MB available")
                    print(f"   WARNING: Low disk space ({available_mb:.1f}MB), save may fail")
            except Exception as e:
                logger.warning(f"Could not check disk space: {e}")
            
            # Create event directory
            event_dir = self.output_dir / f"event_{event_id}"
            try:
                event_dir.mkdir(exist_ok=True, parents=True)
            except OSError as e:
                logger.error(f"Failed to create event directory: {e}")
                print(f"   ERROR: Could not create directory: {e}")
                return
            
            # Save data files
            max_acc = 0
            saved_files = []
            
            for dev_num, data_list in event_data_copy.items():
                if not data_list:
                    continue
                
                csv_path = event_dir / f"device_{dev_num}.csv"
                
                try:
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
                            
                            acc = (data.get('AccX', 0)**2 + 
                                  data.get('AccY', 0)**2 + 
                                  data.get('AccZ', 0)**2)**0.5
                            max_acc = max(max_acc, acc)
                    
                    saved_files.append(dev_num)
                    print(f"   Saved IMU-{dev_num}: {len(data_list)} samples")
                    
                except IOError as e:
                    logger.error(f"Failed to save IMU-{dev_num} data: {e}")
                    print(f"   ERROR: Could not save IMU-{dev_num}: {e}")
                    continue
            
            if not saved_files:
                logger.error("No data files saved successfully!")
                print(f"   ERROR: Failed to save any data files")
                return
            
            # Save metadata
            metadata = {
                'event_id': event_id,
                'trigger_device': trigger_device,
                'trigger_time': datetime.fromtimestamp(trigger_time).isoformat(),
                'duration': duration,
                'threshold': self.threshold,
                'max_acceleration': max_acc,
                'num_devices': len(event_data_copy),
                'devices': list(event_data_copy.keys())
            }
            
            try:
                with open(event_dir / 'metadata.json', 'w') as f:
                    json.dump(metadata, f, indent=2)
            except IOError as e:
                logger.error(f"Failed to save metadata: {e}")
                print(f"   ERROR: Could not save metadata: {e}")
            
            # Save to database
            self._save_to_database(metadata, str(event_dir), trigger_time)
            
            print(f"   Event saved: {event_dir.name}")
            print(f"   Max acceleration: {max_acc:.3f}g")
            print(f"   Total events: {self.stats['total_events']}\n")
            
        except Exception as e:
            logger.error(f"Error saving event data: {e}")
            print(f"   ERROR saving event: {e}\n")
    
    def _save_to_database(self, metadata, data_path, trigger_time):
        """Save to database with explicit column names"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Use explicit column names to avoid schema mismatch issues
            cursor.execute('''
                INSERT INTO events 
                (event_id, start_time, end_time, duration, trigger_device, 
                 max_acceleration, num_devices, data_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metadata['event_id'],
                trigger_time,
                trigger_time + metadata['duration'],
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
            logger.error(f"Database error: {e}")
            print(f"   Database error: {e}")
            print(f"   TIP: If schema mismatch, delete {self.db_path} and restart")
    
    def print_status(self):
        """Print status"""
        current_time = time.time()  # NEW: Define current_time for calibration status
        uptime = current_time - self.stats['uptime_start']
        
        logger.info("=" * 60)
        logger.info("SYSTEM STATUS")
        logger.info(f"Uptime: {uptime/3600:.1f}h | Events: {self.stats['total_events']} | "
                   f"Reconnects: {self.stats['total_reconnects']} | "
                   f"OS Cleanups: {self.stats['total_os_cleanups']}")
        
        print("\n" + "=" * 60)
        print("SYSTEM STATUS")
        print("=" * 60)
        print(f"Uptime: {uptime/3600:.1f} hours")
        print(f"Total Events: {self.stats['total_events']}")
        print(f"Reconnects: {self.stats['total_reconnects']}")
        print(f"OS Cleanups: {self.stats['total_os_cleanups']}")
        
        if self.health_uploader.enabled:
            print(f"Health Upload Count: {self.health_uploader.upload_count}")
            print(f"Health Upload Failures: {self.health_uploader.upload_failures}")

        if self.event_uploader.enabled:
            print(f"Event Upload Count: {self.event_uploader.upload_count}")
            print(f"Event Upload Failures: {self.event_uploader.upload_failures}")

        if self.gdrive_uploader.enabled:
            print(f"Google Drive Upload Count: {self.gdrive_uploader.upload_count}")
            print(f"Google Drive Upload Failures: {self.gdrive_uploader.upload_failures}")

        if self.stats['last_event_time']:
            last = datetime.fromtimestamp(self.stats['last_event_time'])
            print(f"Last Event: {last.strftime('%Y-%m-%d %H:%M:%S')}")

        # NEW: Show calibration status
        if self.last_calibration_time > 0:
            hours_since_cal = (current_time - self.last_calibration_time) / 3600
            print(f"Last Calibration: {hours_since_cal:.1f}h ago")
            print(f"Z-axis Offsets: {', '.join(f'IMU-{num}:{offset:.3f}g' for num, offset in self.z_axis_offset.items())}")

        print(f"\nIMUs: {len(self.imus)}")
        for num in sorted(self.imus.keys()):
            imu = self.imus[num]
            status = "READY" if imu.is_ready else "DISCONNECTED"
            buffer = len(imu.buffer)
            
            # Display health status
            health_info = ""
            if imu.is_ready and imu.device:
                is_healthy, _ = imu.device.check_health(imu.DATA_TIMEOUT)
                window_healthy, _, window_stats = imu.device.check_sliding_window_health()
                
                if not is_healthy or not window_healthy:
                    health_info = " UNHEALTHY"
                
                if imu.device.consecutive_failures > 0:
                    health_info += f" (failures: {imu.device.consecutive_failures})"
                
                # Show sliding window stats
                if window_stats:
                    health_info += f" (window: {window_stats.get('unhealthy_percentage', 0):.0f}%)"
            
            print(f"  IMU-{num}: {status} (Buffer: {buffer}){health_info}")
            
            if imu.current_data:
                acc = imu.current_data
                # Display last data time
                if imu.device and imu.device.last_data_time > 0:
                    elapsed = time.time() - imu.device.last_data_time
                    time_info = f" (last data: {elapsed:.1f}s ago)"
                else:
                    time_info = ""
                
                print(f"    Acc: X={acc.get('AccX', 0):6.3f}g "
                      f"Y={acc.get('AccY', 0):6.3f}g "
                      f"Z={acc.get('AccZ', 0):6.3f}g{time_info}")
        
        print("=" * 60 + "\n")
    
    async def run(self):
        """
        Main run loop
        - Periodically print status
        - Monitor device health, automatic reconnection
        - Trigger OS cleanup (extreme cases)
        - NEW: Upload health data
        - NEW: Periodic calibration check
        - P0: Global throttling to prevent reconnection storm
        """
        logger.info("System running, press Ctrl+C to stop")
        print("Press Ctrl+C to stop\n")

        status_interval = self.config.get('status_report_interval', 30)
        last_status = time.time()
        health_check_interval = 2  # Check every 2 seconds
        last_health_check = time.time()

        try:
            while self.running:
                await asyncio.sleep(1)

                current_time = time.time()

                # NEW: Periodic calibration check (every N hours)
                if self.last_calibration_time > 0:  # Only if initial calibration done
                    hours_since_calibration = (current_time - self.last_calibration_time) / 3600
                    if hours_since_calibration >= self.calibration_interval_hours:
                        # Only calibrate when not recording
                        if not self.recording and not self.calibrating:
                            logger.info(f"Auto-calibration triggered ({hours_since_calibration:.1f}h since last)")
                            print(f"\nAuto-calibration due ({hours_since_calibration:.1f}h elapsed)...")
                            await self._perform_calibration()
                
                # Periodically print status
                if current_time - last_status >= status_interval:
                    self.print_status()
                    last_status = current_time
                    
                    # NEW: Upload health data
                    try:
                        await self.health_uploader.upload_health_data(
                            self.imus,
                            self.stats
                        )
                    except Exception as e:
                        # Do not let upload errors affect main loop
                        logger.debug(f"Health upload exception: {e}")
                
                # P0: If BLE operations are paused, skip all checks
                if self.ble_operations_paused:
                    continue
                
                # Health monitoring + automatic reconnection
                if current_time - last_health_check >= health_check_interval:
                    last_health_check = current_time
                    
                    for num, imu in self.imus.items():
                        if not imu.is_ready:
                            continue
                        
                        # P0: Global reconnection throttling check
                        time_since_last_reconnect = current_time - self.last_reconnect_time
                        if time_since_last_reconnect < self.reconnect_global_cooldown:
                            # Too fast, skip this device
                            logger.debug(
                                f"[IMU-{num}] Skipping check (global cooldown: "
                                f"{time_since_last_reconnect:.1f}s / {self.reconnect_global_cooldown}s)"
                            )
                            continue
                        
                        # Health check + reconnect
                        reconnected = await imu.check_and_reconnect()
                        
                        if reconnected:
                            # P0: Update global reconnect time
                            self.last_reconnect_time = current_time
                            self.stats['total_reconnects'] += 1
                            logger.info(
                                f"Total reconnects: {self.stats['total_reconnects']}"
                            )

                            # NEW: Upload reconnection warning (non-blocking)
                            asyncio.create_task(
                                self.event_uploader.upload_warning(
                                    'device_reconnected',
                                    num,
                                    imu.name,
                                    f"Device {imu.name} reconnected after health check failure",
                                    'medium'
                                )
                            )
                        
                        # Check if OS cleanup is needed
                        if imu.should_trigger_os_cleanup():
                            # P0: Global OS cleanup throttling check
                            time_since_last_os_cleanup = current_time - self.last_os_cleanup_global
                            if time_since_last_os_cleanup < self.os_cleanup_global_cooldown:
                                logger.warning(
                                    f"[IMU-{num}] OS cleanup requested but in GLOBAL cooldown "
                                    f"({time_since_last_os_cleanup:.0f}s / {self.os_cleanup_global_cooldown}s)"
                                )
                                continue
                            
                            logger.critical(
                                f"[IMU-{num}] Consecutive failures threshold reached, "
                                f"triggering OS cleanup"
                            )
                            
                            # Execute OS cleanup (automatically pauses all BLE operations)
                            cleanup_success = await self._os_level_ble_cleanup(imu.mac)

                            # NEW: Upload OS cleanup warning (non-blocking)
                            asyncio.create_task(
                                self.event_uploader.upload_warning(
                                    'os_cleanup_triggered',
                                    num,
                                    imu.name,
                                    f"OS-level BLE cleanup triggered for {imu.name} due to consecutive failures",
                                    'high'
                                )
                            )

                            # P0: Update global OS cleanup time
                            self.last_os_cleanup_global = current_time

                            if cleanup_success:
                                # Reset device failure count
                                if imu.device:
                                    imu.device.consecutive_failures = 0
                                
                                # Wait for system to stabilize then try to reconnect
                                await asyncio.sleep(3.0)
                                
                                logger.info(f"[IMU-{num}] Attempting reconnect after OS cleanup...")
                                await imu.connect()
                            
                            # P0: Forced wait after OS cleanup, don't check other devices
                            break
                
        except asyncio.CancelledError:
            logger.warning("Run loop cancelled")
            print("\nRun loop cancelled")
        finally:
            await self.shutdown()


async def main():
    """Main function"""
    # Check for config file argument
    config_file = "config.json"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    detector = TrainDetector(config_file=config_file)
    
    # Start
    success = await detector.start()
    
    if not success:
        print("Failed to start")
        return
    
    # Run
    await detector.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
