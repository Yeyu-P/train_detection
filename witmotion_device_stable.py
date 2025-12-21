# coding:UTF-8
"""
Witmotion BLE Device Model - Production Stable Version with Sliding Window
Strict adherence to BlueZ constraints: serial connection, explicit resource management, complete error handling
"""
import asyncio
import time
import logging
from enum import Enum
from collections import deque
import bleak

logger = logging.getLogger(__name__)


class DeviceState(Enum):
    """Device state machine"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCOVERING = "discovering"
    READY = "ready"
    ERROR = "error"


class DeviceModel:
    """IMU device model with complete state machine and resource management"""
    
    # Device UUID constants
    TARGET_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9a34fb"
    READ_CHARACTERISTIC_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
    WRITE_CHARACTERISTIC_UUID = "0000ffe9-0000-1000-8000-00805f9a34fb"
    
    def __init__(self, device_name, mac, callback_method, config):
        self.deviceName = device_name
        self.mac = mac
        self.callback_method = callback_method
        self.config = config
        
        # Timeout settings from config
        timeouts = config.get('timeouts', {})
        self.CONNECT_TIMEOUT = timeouts.get('connect_timeout', 15.0)
        self.GATT_TIMEOUT = timeouts.get('gatt_timeout', 10.0)
        self.FIRST_DATA_TIMEOUT = timeouts.get('first_data_timeout', 5.0)
        
        # State management
        self.state = DeviceState.DISCONNECTED
        self.client = None
        self.writer_characteristic = None
        self.notify_characteristic = None
        
        # Raw data queue (decoupled BLE callback)
        self.raw_data_queue = asyncio.Queue(maxsize=100)
        
        # Data reception
        self.deviceData = {}
        self.TempBytes = []
        self.first_data_received = False
        self.last_data_time = 0
        
        # Health monitoring with sliding window
        health_config = config.get('health_monitoring', {})
        self.last_health_check = 0
        self.consecutive_failures = 0
        
        # NEW: Sliding window for health detection
        window_size = health_config.get('sliding_window_size', 50)
        self.health_window = deque(maxlen=window_size)
        self.trigger_percentage = health_config.get('trigger_percentage', 70.0)
        
        # Frequency mapping
        self.freqMap = {
            0.1: 0x0001, 0.5: 0x0002, 1: 0x0003, 2: 0x0004,
            5: 0x0005, 10: 0x0006, 20: 0x0007, 50: 0x0008,
            100: 0x0009, 200: 0x000B,
        }
        
        logger.info(f"[{self.deviceName}] Initialized (MAC: {self.mac})")
        print(f"[{self.deviceName}] Initialized (MAC: {self.mac})")
    
    async def connect(self):
        """
        Connection flow (strictly serial):
        1. Create client
        2. Connect (with timeout)
        3. Discover services (with timeout)
        4. Start notification
        5. Wait for first data (verify connection)
        
        Returns: (success: bool, error_msg: str)
        """
        if self.state != DeviceState.DISCONNECTED:
            return False, f"Invalid state: {self.state}"
        
        self.state = DeviceState.CONNECTING
        print(f"[{self.deviceName}] Connecting to {self.mac}...")
        
        try:
            # Step 1: Create client
            self.client = bleak.BleakClient(
                self.mac,
                timeout=self.CONNECT_TIMEOUT
            )
            
            # Step 2: Connect (with timeout)
            try:
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=self.CONNECT_TIMEOUT
                )
            except asyncio.TimeoutError:
                await self._cleanup()
                return False, "Connection timeout"
            
            if not self.client.is_connected:
                await self._cleanup()
                return False, "Connection failed"
            
            self.state = DeviceState.CONNECTED
            print(f"[{self.deviceName}] Connected, discovering services...")
            
            # Step 3: Discover services and characteristics (with timeout)
            self.state = DeviceState.DISCOVERING
            try:
                success = await asyncio.wait_for(
                    self._discover_services(),
                    timeout=self.GATT_TIMEOUT
                )
                if not success:
                    await self._cleanup()
                    return False, "Service discovery failed"
            except asyncio.TimeoutError:
                await self._cleanup()
                return False, "Service discovery timeout"
            
            # Step 4: Set default frequency (silent, no print)
            try:
                await asyncio.wait_for(
                    self.setOutputFreq(50),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                print(f"[{self.deviceName}] Warning: freq setup timeout (non-fatal)")
            except Exception as e:
                print(f"[{self.deviceName}] Warning: freq setup error: {e}")
            
            # Step 5: Start notification
            try:
                await self.client.start_notify(
                    self.notify_characteristic.uuid,
                    self._on_data_received
                )
            except Exception as e:
                await self._cleanup()
                return False, f"Start notify failed: {e}"
            
            # Step 6: Wait for first data (verify connection actually works)
            self.first_data_received = False
            logger.info(f"[{self.deviceName}] Waiting for first data...")
            print(f"[{self.deviceName}] Waiting for first data...")
            
            # Start data processing task
            self.data_task = asyncio.create_task(self.process_data_queue())
            
            start_time = time.time()
            while not self.first_data_received:
                if time.time() - start_time > self.FIRST_DATA_TIMEOUT:
                    await self._cleanup()
                    return False, "No data received (timeout)"
                await asyncio.sleep(0.1)
            
            self.state = DeviceState.READY
            self.consecutive_failures = 0
            self.health_window.clear()  # Clear old health data on reconnection
            logger.info(f"[{self.deviceName}] READY (data flowing)")
            print(f"[{self.deviceName}] READY (data flowing)")
            return True, "Connected successfully"
            
        except Exception as e:
            await self._cleanup()
            return False, f"Connection error: {e}"
    
    async def _discover_services(self):
        """Discover services and characteristics"""
        if not self.client or not self.client.is_connected:
            return False
        
        try:
            services = self.client.services
            
            for service in services:
                if service.uuid == self.TARGET_SERVICE_UUID:
                    for char in service.characteristics:
                        if char.uuid == self.READ_CHARACTERISTIC_UUID:
                            self.notify_characteristic = char
                        elif char.uuid == self.WRITE_CHARACTERISTIC_UUID:
                            self.writer_characteristic = char
                    break
            
            if not self.notify_characteristic or not self.writer_characteristic:
                print(f"[{self.deviceName}] Required characteristics not found")
                return False
            
            print(f"[{self.deviceName}] Services discovered")
            return True
            
        except Exception as e:
            print(f"[{self.deviceName}] Service discovery error: {e}")
            return False
    
    async def disconnect(self):
        """
        Disconnect flow (complete cleanup):
        1. Stop notification
        2. Disconnect
        3. Clean up all resources
        """
        print(f"[{self.deviceName}] Disconnecting...")
        await self._cleanup()
        print(f"[{self.deviceName}] Disconnected")
    
    async def _cleanup(self):
        """Resource cleanup (idempotent, can be called multiple times)"""
        old_state = self.state
        
        # Step 0: Cancel data processing task
        if hasattr(self, 'data_task') and self.data_task and not self.data_task.done():
            self.data_task.cancel()
            try:
                await self.data_task
            except asyncio.CancelledError:
                pass
        
        # Step 1: Stop notification
        if self.client and self.client.is_connected and self.notify_characteristic:
            try:
                await asyncio.wait_for(
                    self.client.stop_notify(self.notify_characteristic.uuid),
                    timeout=2.0
                )
                logger.info(f"[{self.deviceName}] Notification stopped")
            except Exception as e:
                logger.warning(f"[{self.deviceName}] Stop notify error: {e}")
        
        # Step 2: Disconnect
        if self.client and self.client.is_connected:
            try:
                await asyncio.wait_for(
                    self.client.disconnect(),
                    timeout=2.0
                )
                logger.info(f"[{self.deviceName}] BLE disconnected")
            except Exception as e:
                logger.warning(f"[{self.deviceName}] Disconnect error: {e}")
        
        # Step 3: Clean up state (prevent state regression)
        self.client = None
        self.writer_characteristic = None
        self.notify_characteristic = None
        
        # Clear data queue
        while not self.raw_data_queue.empty():
            try:
                self.raw_data_queue.get_nowait()
            except:
                break
        
        # State machine constraint: only allow one-way migration to DISCONNECTED
        if old_state in [DeviceState.CONNECTED, DeviceState.DISCOVERING, DeviceState.READY]:
            self.state = DeviceState.DISCONNECTED
            logger.info(f"[{self.deviceName}] State: {old_state.value} -> DISCONNECTED")
        
        self.first_data_received = False
    
    def _on_data_received(self, sender, data):
        """
        BLE notification callback (called in BLE thread)
        CRITICAL: Only minimal work - cache raw data to queue
        Prohibit business logic here to prevent blocking BLE stack
        """
        try:
            # Only cache raw bytes, return immediately
            raw_bytes = bytes.fromhex(data.hex())
            
            # Non-blocking put to queue
            try:
                self.raw_data_queue.put_nowait((time.time(), raw_bytes))
            except asyncio.QueueFull:
                # Queue full, drop oldest data (don't block)
                logger.warning(f"[{self.deviceName}] Data queue full, dropping old data")
                try:
                    self.raw_data_queue.get_nowait()
                    self.raw_data_queue.put_nowait((time.time(), raw_bytes))
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"[{self.deviceName}] BLE callback error: {e}")
    
    def _process_data(self, bytes_data):
        """Parse IMU data"""
        try:
            Ax = self._get_sign_int16(bytes_data[1] << 8 | bytes_data[0]) / 32768 * 16
            Ay = self._get_sign_int16(bytes_data[3] << 8 | bytes_data[2]) / 32768 * 16
            Az = self._get_sign_int16(bytes_data[5] << 8 | bytes_data[4]) / 32768 * 16
            Gx = self._get_sign_int16(bytes_data[7] << 8 | bytes_data[6]) / 32768 * 2000
            Gy = self._get_sign_int16(bytes_data[9] << 8 | bytes_data[8]) / 32768 * 2000
            Gz = self._get_sign_int16(bytes_data[11] << 8 | bytes_data[10]) / 32768 * 2000
            AngX = self._get_sign_int16(bytes_data[13] << 8 | bytes_data[12]) / 32768 * 180
            AngY = self._get_sign_int16(bytes_data[15] << 8 | bytes_data[14]) / 32768 * 180
            AngZ = self._get_sign_int16(bytes_data[17] << 8 | bytes_data[16]) / 32768 * 180
            
            self.deviceData = {
                "AccX": round(Ax, 3),
                "AccY": round(Ay, 3),
                "AccZ": round(Az, 3),
                "AsX": round(Gx, 3),
                "AsY": round(Gy, 3),
                "AsZ": round(Gz, 3),
                "AngX": round(AngX, 3),
                "AngY": round(AngY, 3),
                "AngZ": round(AngZ, 3)
            }
            
            # Callback to upper layer
            if self.callback_method:
                self.callback_method(self)
                
        except Exception as e:
            logger.error(f"[{self.deviceName}] Parse error: {e}")
    
    async def process_data_queue(self):
        """
        Asynchronous data processing task (runs in asyncio loop)
        Fetch raw data from queue, perform parsing and business processing
        """
        while self.state != DeviceState.DISCONNECTED:
            try:
                # Wait for data with timeout
                timestamp, raw_bytes = await asyncio.wait_for(
                    self.raw_data_queue.get(),
                    timeout=0.1
                )
                
                # Process data packet (protocol parsing)
                for byte_val in raw_bytes:
                    self.TempBytes.append(byte_val)
                    
                    # Check packet header
                    if len(self.TempBytes) == 2:
                        if self.TempBytes[0] != 0x55 or self.TempBytes[1] != 0x61:
                            del self.TempBytes[0]
                            continue
                    
                    # Complete packet (20 bytes)
                    if len(self.TempBytes) == 20:
                        self._process_data(self.TempBytes[2:])
                        self.TempBytes.clear()
                        
                        # Mark first frame
                        if not self.first_data_received:
                            self.first_data_received = True
                            logger.info(f"[{self.deviceName}] First data received")
                        
                        # Update health status
                        self.last_data_time = timestamp
                        
            except asyncio.TimeoutError:
                # Timeout is normal, continue loop
                continue
            except Exception as e:
                logger.error(f"[{self.deviceName}] Data queue processing error: {e}")
                await asyncio.sleep(0.1)
    
    @staticmethod
    def _get_sign_int16(num):
        """Convert to signed int16"""
        if num >= pow(2, 15):
            num -= pow(2, 16)
        return num
    
    async def _send_data(self, data):
        """Send data to device"""
        if not self.client or not self.client.is_connected or not self.writer_characteristic:
            raise Exception("Device not ready")
        
        try:
            await self.client.write_gatt_char(
                self.writer_characteristic.uuid,
                bytearray(data),
                response=False
            )
        except Exception as e:
            raise Exception(f"Send failed: {e}")
    
    async def setOutputFreq(self, freq=50):
        """Set output frequency"""
        closest_freq = max((f for f in self.freqMap if f <= freq), default=50)
        
        await self._unlock()
        await asyncio.sleep(0.1)
        
        await self._send_data(self._get_write_bytes(0x03, self.freqMap[closest_freq]))
        await asyncio.sleep(0.1)
        
        await self._save()
    
    async def startAccCalibration(self):
        """Start accelerometer calibration"""
        await self._unlock()
        await asyncio.sleep(0.1)
        
        await self._send_data(self._get_write_bytes(0x01, 0x0001))
        await asyncio.sleep(0.1)
        
        await self._save()
    
    async def _unlock(self):
        """Unlock device"""
        cmd = self._get_write_bytes(0x69, 0xb588)
        await self._send_data(cmd)
    
    async def _save(self):
        """Save settings"""
        cmd = self._get_write_bytes(0x00, 0x0000)
        await self._send_data(cmd)
    
    @staticmethod
    def _get_write_bytes(reg_addr, value):
        """Construct write command"""
        return [0xff, 0xaa, reg_addr, value & 0xff, value >> 8]
    
    @staticmethod
    def _get_read_bytes(reg_addr):
        """Construct read command"""
        return [0xff, 0xaa, 0x27, reg_addr, 0]
    
    def is_ready(self):
        """Check if device is ready"""
        return self.state == DeviceState.READY
    
    def is_connected(self):
        """Check if connected"""
        return self.state in [DeviceState.CONNECTED, DeviceState.DISCOVERING, DeviceState.READY]
    
    def get_state(self):
        """Get current state"""
        return self.state
    
    def update_health_window(self, is_healthy):
        """
        NEW: Update sliding window with health check result
        
        Args:
            is_healthy: bool indicating if current check passed
        """
        current_time = time.time()
        self.health_window.append({
            'timestamp': current_time,
            'healthy': is_healthy
        })
    
    def check_sliding_window_health(self):
        """
        NEW: Check health based on sliding window percentage
        
        Returns: (is_healthy: bool, reason: str, stats: dict)
        """
        if len(self.health_window) == 0:
            return True, "No data in window", {}
        
        # Filter checks from last 1 second
        current_time = time.time()
        recent_checks = [
            check for check in self.health_window
            if current_time - check['timestamp'] <= 1.0
        ]
        
        if len(recent_checks) == 0:
            return True, "No recent checks", {}
        
        # Calculate percentage of unhealthy checks
        unhealthy_count = sum(1 for check in recent_checks if not check['healthy'])
        total_count = len(recent_checks)
        unhealthy_percentage = (unhealthy_count / total_count) * 100
        
        stats = {
            'total_checks': total_count,
            'unhealthy_count': unhealthy_count,
            'unhealthy_percentage': unhealthy_percentage,
            'threshold': self.trigger_percentage
        }
        
        if unhealthy_percentage >= self.trigger_percentage:
            reason = (f"Sliding window failure: {unhealthy_percentage:.1f}% "
                     f"unhealthy (threshold: {self.trigger_percentage}%)")
            return False, reason, stats
        
        return True, "Sliding window healthy", stats
    
    def check_health(self, data_timeout=3.0):
        """
        Health check: detect "dead connection"
        
        Conditions:
        - State is READY
        - But no data received for more than data_timeout seconds
        
        Returns: (is_healthy: bool, reason: str)
        """
        current_time = time.time()
        
        # Not in READY state, don't check
        if self.state != DeviceState.READY:
            return True, "Not in READY state"
        
        # Never received data
        if self.last_data_time == 0:
            return True, "No data received yet (initial state)"
        
        # Check data timeout
        elapsed = current_time - self.last_data_time
        if elapsed > data_timeout:
            logger.warning(
                f"[{self.deviceName}] Health check FAILED: "
                f"No data for {elapsed:.1f}s (threshold: {data_timeout}s)"
            )
            return False, f"No data for {elapsed:.1f}s (dead connection)"
        
        return True, "Healthy"
    
    def increment_failure(self):
        """Increment failure count"""
        self.consecutive_failures += 1
        logger.warning(
            f"[{self.deviceName}] Consecutive failures: {self.consecutive_failures}"
        )
        return self.consecutive_failures
    
    def reset_failure(self):
        """Reset failure count"""
        if self.consecutive_failures > 0:
            logger.info(f"[{self.deviceName}] Resetting failure count from {self.consecutive_failures}")
        self.consecutive_failures = 0
    
    def get_health_stats(self):
        """
        NEW: Get comprehensive health statistics for upload
        
        Returns: dict with health metrics
        """
        current_time = time.time()
        
        # Get sliding window statistics
        window_healthy, window_reason, window_stats = self.check_sliding_window_health()
        
        # Get basic health check
        basic_healthy, basic_reason = self.check_health()
        
        return {
            'device_name': self.deviceName,
            'mac': self.mac,
            'state': self.state.value,
            'is_ready': self.is_ready(),
            'last_data_time': self.last_data_time,
            'time_since_last_data': current_time - self.last_data_time if self.last_data_time > 0 else -1,
            'consecutive_failures': self.consecutive_failures,
            'basic_health': {
                'healthy': basic_healthy,
                'reason': basic_reason
            },
            'sliding_window': {
                'healthy': window_healthy,
                'reason': window_reason,
                'stats': window_stats
            },
            'current_data': self.deviceData.copy() if self.deviceData else {}
        }
