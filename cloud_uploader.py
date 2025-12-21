"""
Cloud Upload Module
Handles asynchronous upload of health status and data to remote endpoint
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Optional
import aiohttp


class CloudUploader:
    """
    Manages cloud uploads with retry logic and non-blocking operation
    """
    
    def __init__(self, config: Dict):
        """
        Initialize cloud uploader
        
        Args:
            config: Configuration dictionary with endpoint, timeout, etc.
        """
        self.enabled = config.get('enabled', False)
        self.endpoint = config.get('endpoint', 'http://localhost:8000/api/health')
        self.timeout = config.get('timeout_seconds', 5.0)
        self.retry_attempts = config.get('retry_attempts', 3)
        self.upload_interval = config.get('upload_interval_seconds', 60)
        self.include_raw_data = config.get('include_raw_data', False)
        
        self.last_upload_time = 0
        self.upload_queue = asyncio.Queue()
        self.stats = {
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'last_upload_time': None,
            'last_error': None
        }
        
        print(f"Cloud Uploader initialized: {self.endpoint}")
        print(f"  Enabled: {self.enabled}")
        print(f"  Upload interval: {self.upload_interval}s")

    async def upload_health_status(self, device_number: int, device_name: str, 
                                   mac_address: str, health_data: Dict,
                                   sliding_window_status: Dict) -> bool:
        """
        Upload device health status to cloud endpoint
        
        Args:
            device_number: Device identifier
            device_name: Device name
            mac_address: Device MAC address
            health_data: Health check results
            sliding_window_status: Sliding window analysis results
            
        Returns:
            Success status
        """
        if not self.enabled:
            return True
        
        # Rate limiting: check if enough time has passed since last upload
        current_time = time.time()
        if current_time - self.last_upload_time < self.upload_interval:
            return True
        
        payload = {
            'timestamp': datetime.now().isoformat(),
            'device': {
                'number': device_number,
                'name': device_name,
                'mac_address': mac_address
            },
            'health_status': health_data,
            'sliding_window': sliding_window_status,
            'uploader_stats': {
                'total_uploads': self.stats['total_uploads'],
                'success_rate': self._calculate_success_rate()
            }
        }
        
        success = await self._send_with_retry(payload)
        
        if success:
            self.last_upload_time = current_time
            self.stats['successful_uploads'] += 1
            self.stats['last_upload_time'] = datetime.now().isoformat()
        else:
            self.stats['failed_uploads'] += 1
        
        self.stats['total_uploads'] += 1
        
        return success

    async def _send_with_retry(self, payload: Dict) -> bool:
        """
        Send payload with retry logic
        
        Args:
            payload: JSON payload to send
            
        Returns:
            Success status
        """
        for attempt in range(self.retry_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.endpoint,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as response:
                        if response.status == 200:
                            return True
                        else:
                            error_msg = f"HTTP {response.status}"
                            self.stats['last_error'] = error_msg
                            if attempt < self.retry_attempts - 1:
                                await asyncio.sleep(1)  # Wait before retry
                            
            except asyncio.TimeoutError:
                error_msg = "Upload timeout"
                self.stats['last_error'] = error_msg
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(1)
                    
            except aiohttp.ClientError as e:
                error_msg = f"Connection error: {str(e)}"
                self.stats['last_error'] = error_msg
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                self.stats['last_error'] = error_msg
                break
        
        return False

    def _calculate_success_rate(self) -> float:
        """Calculate upload success rate"""
        if self.stats['total_uploads'] == 0:
            return 100.0
        return (self.stats['successful_uploads'] / self.stats['total_uploads']) * 100

    def get_stats(self) -> Dict:
        """Get upload statistics"""
        return {
            **self.stats,
            'success_rate': self._calculate_success_rate(),
            'enabled': self.enabled
        }

    async def upload_event_data(self, event_id: str, event_metadata: Dict) -> bool:
        """
        Upload train detection event metadata
        
        Args:
            event_id: Event identifier
            event_metadata: Event metadata dictionary
            
        Returns:
            Success status
        """
        if not self.enabled:
            return True
        
        payload = {
            'timestamp': datetime.now().isoformat(),
            'event_type': 'train_detection',
            'event_id': event_id,
            'metadata': event_metadata
        }
        
        return await self._send_with_retry(payload)


class MockCloudUploader(CloudUploader):
    """
    Mock uploader for testing without real endpoint
    Simulates upload success/failure
    """
    
    def __init__(self, config: Dict, success_rate: float = 0.95):
        """
        Initialize mock uploader
        
        Args:
            config: Configuration dictionary
            success_rate: Probability of successful upload (0.0 to 1.0)
        """
        super().__init__(config)
        self.success_rate = success_rate
        self.uploaded_payloads = []
        print(f"Mock Cloud Uploader - Success rate: {success_rate*100}%")

    async def _send_with_retry(self, payload: Dict) -> bool:
        """
        Simulate upload with configurable success rate
        
        Args:
            payload: JSON payload
            
        Returns:
            Simulated success status
        """
        # Store payload for testing/debugging
        self.uploaded_payloads.append({
            'timestamp': datetime.now().isoformat(),
            'payload': payload
        })
        
        # Simulate network delay
        await asyncio.sleep(0.1)
        
        # Simulate success/failure based on success_rate
        import random
        success = random.random() < self.success_rate
        
        if not success:
            self.stats['last_error'] = "Simulated network failure"
        
        return success

    def get_uploaded_payloads(self):
        """Get all uploaded payloads (for testing)"""
        return self.uploaded_payloads
