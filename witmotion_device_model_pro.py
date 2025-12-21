# coding:UTF-8
"""
Witmotion IMU Device Model - Professional Edition
Handles BLE communication with Witmotion IMU sensors
"""
import time
import asyncio
import bleak
from collections import deque


class DeviceModel:
    """
    Device model for Witmotion IMU sensors
    Manages BLE connection, data parsing, and configuration
    """
    
    # BLE UUID constants for Witmotion devices
    TARGET_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9a34fb"
    TARGET_CHAR_READ_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
    TARGET_CHAR_WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9a34fb"
    
    # Frequency mapping for output rate configuration
    FREQ_MAP = {
        0.1: 0x0001,
        0.5: 0x0002,
        1: 0x0003,
        2: 0x0004,
        5: 0x0005,
        10: 0x0006,
        20: 0x0007,
        50: 0x0008,
        100: 0x0009,
        200: 0x000B,
    }

    def __init__(self, device_name, mac_address, data_callback):
        """
        Initialize device model
        
        Args:
            device_name: Human-readable device name
            mac_address: BLE MAC address
            data_callback: Callback function for processed data
        """
        self.deviceName = device_name
        self.mac = mac_address
        self.callback_method = data_callback
        
        # BLE client state
        self.client = None
        self.writer_characteristic = None
        self.isOpen = False
        
        # Data storage
        self.deviceData = {}
        self.TempBytes = []
        
        # Sliding window for health monitoring
        self.sliding_window = deque(maxlen=50)  # Default window size
        self.window_config = {
            'enabled': False,
            'size': 50,
            'threshold': 1.5,
            'trigger_percentage': 70.0
        }

    def configure_sliding_window(self, enabled=True, size=50, threshold=1.5, trigger_percentage=70.0):
        """
        Configure sliding window parameters for health monitoring
        
        Args:
            enabled: Enable/disable sliding window monitoring
            size: Number of samples in the window
            threshold: Acceleration threshold in g
            trigger_percentage: Percentage of samples exceeding threshold to trigger alert
        """
        self.window_config = {
            'enabled': enabled,
            'size': size,
            'threshold': threshold,
            'trigger_percentage': trigger_percentage
        }
        self.sliding_window = deque(maxlen=size)

    def check_sliding_window_health(self):
        """
        Check if recent data indicates potential health issues
        
        Returns:
            dict: Health status with details
                - healthy: bool
                - exceeded_count: int
                - percentage: float
                - threshold: float
        """
        if not self.window_config['enabled'] or len(self.sliding_window) < 10:
            return {
                'healthy': True,
                'exceeded_count': 0,
                'percentage': 0.0,
                'threshold': self.window_config['threshold'],
                'window_size': len(self.sliding_window)
            }
        
        threshold = self.window_config['threshold']
        exceeded_count = sum(1 for magnitude in self.sliding_window if magnitude > threshold)
        percentage = (exceeded_count / len(self.sliding_window)) * 100
        
        healthy = percentage < self.window_config['trigger_percentage']
        
        return {
            'healthy': healthy,
            'exceeded_count': exceeded_count,
            'percentage': percentage,
            'threshold': threshold,
            'window_size': len(self.sliding_window),
            'trigger_percentage': self.window_config['trigger_percentage']
        }

    def set(self, key, value):
        """Store device data by key"""
        self.deviceData[key] = value

    def get(self, key):
        """Retrieve device data by key"""
        return self.deviceData.get(key, None)

    def remove(self, key):
        """Delete device data by key"""
        if key in self.deviceData:
            del self.deviceData[key]

    async def openDevice(self):
        """
        Open BLE connection to device and start data streaming
        Maintains connection until closeDevice() is called
        """
        try:
            async with bleak.BleakClient(self.mac) as client:
                self.client = client
                self.isOpen = True
                
                notify_characteristic = None

                # Find required characteristics
                for service in client.services:
                    if service.uuid == self.TARGET_SERVICE_UUID:
                        for characteristic in service.characteristics:
                            if characteristic.uuid == self.TARGET_CHAR_READ_UUID:
                                notify_characteristic = characteristic
                            if characteristic.uuid == self.TARGET_CHAR_WRITE_UUID:
                                self.writer_characteristic = characteristic
                        if notify_characteristic:
                            break
                
                # Set default output frequency to 50Hz
                await self.setOutputFreq(50)

                if notify_characteristic:
                    # Start receiving data notifications
                    await client.start_notify(notify_characteristic.uuid, self.onDataReceived)

                    # Keep connection alive
                    try:
                        while self.isOpen:
                            await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        print(f"Device {self.deviceName} connection cancelled")
                    finally:
                        # Stop notifications on exit
                        try:
                            await client.stop_notify(notify_characteristic.uuid)
                        except:
                            pass
        except Exception as e:
            print(f"Device {self.deviceName} error: {e}")
        finally:
            # Ensure cleanup
            self.isOpen = False
            self.client = None
            print(f"Device {self.deviceName} disconnected cleanly")

    def closeDevice(self):
        """Close device connection"""
        self.isOpen = False

    def onDataReceived(self, sender, data):
        """
        BLE data reception callback
        Accumulates bytes until a complete frame is received
        
        Args:
            sender: BLE characteristic handle
            data: Raw byte data
        """
        tempdata = bytes.fromhex(data.hex())
        for var in tempdata:
            self.TempBytes.append(var)
            # Check for valid frame header (0x55 0x61)
            if len(self.TempBytes) == 2 and (self.TempBytes[0] != 0x55 or self.TempBytes[1] != 0x61):
                del self.TempBytes[0]
                continue
            # Process complete frame (20 bytes)
            if len(self.TempBytes) == 20:
                self.processData(self.TempBytes[2:])
                self.TempBytes.clear()

    def processData(self, data_bytes):
        """
        Parse raw IMU data frame
        Extracts acceleration, gyroscope, and angle data
        
        Args:
            data_bytes: 18 bytes of sensor data
        """
        # Parse acceleration (±16g range)
        Ax = self.getSignInt16(data_bytes[1] << 8 | data_bytes[0]) / 32768 * 16
        Ay = self.getSignInt16(data_bytes[3] << 8 | data_bytes[2]) / 32768 * 16
        Az = self.getSignInt16(data_bytes[5] << 8 | data_bytes[4]) / 32768 * 16
        
        # Parse gyroscope (±2000°/s range)
        Gx = self.getSignInt16(data_bytes[7] << 8 | data_bytes[6]) / 32768 * 2000
        Gy = self.getSignInt16(data_bytes[9] << 8 | data_bytes[8]) / 32768 * 2000
        Gz = self.getSignInt16(data_bytes[11] << 8 | data_bytes[10]) / 32768 * 2000
        
        # Parse angles (±180° range)
        AngX = self.getSignInt16(data_bytes[13] << 8 | data_bytes[12]) / 32768 * 180
        AngY = self.getSignInt16(data_bytes[15] << 8 | data_bytes[14]) / 32768 * 180
        AngZ = self.getSignInt16(data_bytes[17] << 8 | data_bytes[16]) / 32768 * 180
        
        # Store processed data
        self.set("AccX", round(Ax, 3))
        self.set("AccY", round(Ay, 3))
        self.set("AccZ", round(Az, 3))
        self.set("AsX", round(Gx, 3))
        self.set("AsY", round(Gy, 3))
        self.set("AsZ", round(Gz, 3))
        self.set("AngX", round(AngX, 3))
        self.set("AngY", round(AngY, 3))
        self.set("AngZ", round(AngZ, 3))
        
        # Update sliding window with magnitude
        if self.window_config['enabled']:
            magnitude = (Ax**2 + Ay**2 + Az**2)**0.5
            self.sliding_window.append(magnitude)
        
        # Trigger callback with processed data
        self.callback_method(self)

    @staticmethod
    def getSignInt16(num):
        """
        Convert unsigned 16-bit to signed 16-bit
        
        Args:
            num: Unsigned 16-bit integer
            
        Returns:
            Signed 16-bit integer
        """
        if num >= pow(2, 15):
            num -= pow(2, 16)
        return num

    async def sendData(self, data):
        """
        Send data to device via BLE
        
        Args:
            data: Byte array to send
        """
        try:
            if self.client is not None and self.writer_characteristic is not None:
                await self.client.write_gatt_char(self.writer_characteristic.uuid, bytearray(data))
        except Exception as ex:
            print(f"Send data error: {ex}")

    async def readReg(self, reg_addr):
        """
        Read device register
        
        Args:
            reg_addr: Register address
        """
        await self.sendData(self.get_readBytes(reg_addr))

    async def writeReg(self, reg_addr, value):
        """
        Write device register
        
        Args:
            reg_addr: Register address
            value: Value to write
        """
        await self.unlock()
        await asyncio.sleep(0.1)
        await self.sendData(self.get_writeBytes(reg_addr, value))
        await asyncio.sleep(0.1)
        await self.save()

    async def startAccCalibration(self):
        """Start acceleration calibration"""
        await self.writeReg(0x01, 0x0001)
        
    async def setOutputFreq(self, freq=50):
        """
        Set device output frequency
        
        Args:
            freq: Desired frequency in Hz (will round to nearest supported)
        """
        register = 0x03
        closest_freq = max((f for f in self.FREQ_MAP if f <= freq), default=50)
        
        await self.unlock()
        await asyncio.sleep(0.1)
        await self.sendData(self.get_writeBytes(register, self.FREQ_MAP[closest_freq]))
        await asyncio.sleep(0.1)
        await self.save()

    @staticmethod
    def get_readBytes(reg_addr):
        """
        Build read command packet
        
        Args:
            reg_addr: Register address
            
        Returns:
            Command byte array
        """
        return [0xff, 0xaa, 0x27, reg_addr, 0]

    @staticmethod
    def get_writeBytes(reg_addr, value):
        """
        Build write command packet
        
        Args:
            reg_addr: Register address
            value: Value to write
            
        Returns:
            Command byte array
        """
        return [0xff, 0xaa, reg_addr, value & 0xff, value >> 8]

    async def unlock(self):
        """Unlock device for configuration changes"""
        cmd = self.get_writeBytes(0x69, 0xb588)
        await self.sendData(cmd)

    async def save(self):
        """Save configuration changes to device"""
        cmd = self.get_writeBytes(0x00, 0x0000)
        await self.sendData(cmd)
