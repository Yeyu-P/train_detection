#!/usr/bin/env python3
"""
Test Script - Professional Edition
Validates functionality of enhanced detection system
"""
import time
import json
import sys
from pathlib import Path

# Attempt to import main components
try:
    from train_detector_pro import TrainDetector, IMUDevice, CircularBuffer
    from witmotion_device_model_pro import DeviceModel
    from cloud_uploader import CloudUploader, MockCloudUploader
except ImportError as e:
    print(f"Import error: {e}")
    print("Ensure all files are in the same directory")
    sys.exit(1)


def test_configuration_loading():
    """Test 1: Configuration Loading"""
    print("\n" + "="*60)
    print("TEST 1: Configuration Loading")
    print("="*60)
    
    try:
        # Test with existing config
        detector = TrainDetector(config_file="system_config.json")
        
        # Verify key parameters loaded
        assert detector.threshold > 0, "Threshold not loaded"
        assert detector.min_duration > 0, "Min duration not loaded"
        assert len(detector.config.get('devices', [])) > 0, "No devices in config"
        
        print("PASS: Configuration loaded successfully")
        print(f"  Threshold: {detector.threshold}g")
        print(f"  Devices configured: {len(detector.config.get('devices', []))}")
        print(f"  Sliding window enabled: {detector.sliding_window_config.get('enabled', False)}")
        
        return True
        
    except Exception as e:
        print(f"FAIL: Configuration loading failed - {e}")
        return False


def test_circular_buffer():
    """Test 2: Circular Buffer Functionality"""
    print("\n" + "="*60)
    print("TEST 2: Circular Buffer")
    print("="*60)
    
    try:
        buffer = CircularBuffer(max_seconds=2, sample_rate=10)
        
        # Add data points
        for i in range(30):
            timestamp = time.time() + i * 0.1
            data = {'AccX': i * 0.1, 'AccY': 0, 'AccZ': 1.0}
            buffer.add(timestamp, data)
        
        # Verify buffer size (should max at 2s * 10Hz = 20 samples)
        assert len(buffer) == 20, f"Buffer size incorrect: {len(buffer)}"
        
        # Verify data retrieval
        all_data = buffer.get_all()
        assert len(all_data) == 20, "Buffer retrieval failed"
        
        # Verify FIFO behavior (oldest data should be dropped)
        first_acc = all_data[0][1]['AccX']
        assert first_acc >= 1.0, "FIFO behavior incorrect"  # First 10 should be dropped
        
        print("PASS: Circular buffer working correctly")
        print(f"  Buffer size: {len(buffer)}/20")
        print(f"  Oldest AccX: {first_acc:.1f}")
        
        return True
        
    except Exception as e:
        print(f"FAIL: Circular buffer test failed - {e}")
        return False


def test_sliding_window_config():
    """Test 3: Sliding Window Configuration"""
    print("\n" + "="*60)
    print("TEST 3: Sliding Window Configuration")
    print("="*60)
    
    try:
        # Create device model with callback
        def dummy_callback(device_model):
            pass
        
        device = DeviceModel("TestDevice", "00:00:00:00:00:00", dummy_callback)
        
        # Configure sliding window
        device.configure_sliding_window(
            enabled=True,
            size=50,
            threshold=1.5,
            trigger_percentage=70.0
        )
        
        # Verify configuration
        assert device.window_config['enabled'] == True
        assert device.window_config['size'] == 50
        assert device.window_config['threshold'] == 1.5
        assert device.window_config['trigger_percentage'] == 70.0
        
        # Simulate data points
        for i in range(60):
            # 80% of samples will exceed threshold
            magnitude = 2.0 if i < 48 else 0.5
            device.sliding_window.append(magnitude)
        
        # Check health status
        health_status = device.check_sliding_window_health()
        
        assert health_status['window_size'] == 50  # Should be limited to window size
        assert not health_status['healthy']  # Should be unhealthy (80% > 70%)
        assert health_status['percentage'] > 70.0
        
        print("PASS: Sliding window configuration working")
        print(f"  Window size: {health_status['window_size']}")
        print(f"  Exceeded percentage: {health_status['percentage']:.1f}%")
        print(f"  Health status: {'Healthy' if health_status['healthy'] else 'Unhealthy'}")
        
        return True
        
    except Exception as e:
        print(f"FAIL: Sliding window test failed - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cloud_uploader():
    """Test 4: Cloud Uploader (Mock Mode)"""
    print("\n" + "="*60)
    print("TEST 4: Cloud Uploader (Mock)")
    print("="*60)
    
    try:
        import asyncio
        
        # Create mock uploader
        config = {
            'enabled': True,
            'endpoint': 'http://localhost:8000/api/health',
            'timeout_seconds': 5.0,
            'retry_attempts': 3,
            'upload_interval_seconds': 1  # Short interval for testing
        }
        
        uploader = MockCloudUploader(config, success_rate=0.9)
        
        # Test health status upload
        async def run_upload_test():
            health_data = {
                'is_healthy': True,
                'first_frame_received': True,
                'last_valid_time': time.time()
            }
            
            sliding_window_status = {
                'healthy': True,
                'exceeded_count': 10,
                'percentage': 20.0,
                'window_size': 50
            }
            
            # Perform multiple uploads
            results = []
            for i in range(5):
                result = await uploader.upload_health_status(
                    device_number=1,
                    device_name="TestDevice",
                    mac_address="00:00:00:00:00:00",
                    health_data=health_data,
                    sliding_window_status=sliding_window_status
                )
                results.append(result)
                await asyncio.sleep(1.1)  # Wait for interval
            
            return results
        
        # Run async test
        results = asyncio.run(run_upload_test())
        
        # Verify uploads occurred
        stats = uploader.get_stats()
        assert stats['total_uploads'] > 0, "No uploads recorded"
        
        print("PASS: Cloud uploader working")
        print(f"  Total uploads: {stats['total_uploads']}")
        print(f"  Successful: {stats['successful_uploads']}")
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Payloads captured: {len(uploader.get_uploaded_payloads())}")
        
        return True
        
    except Exception as e:
        print(f"FAIL: Cloud uploader test failed - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_imu_device_health():
    """Test 5: IMU Device Health Monitoring"""
    print("\n" + "="*60)
    print("TEST 5: IMU Device Health Monitoring")
    print("="*60)
    
    try:
        # Create IMU device
        config = {
            'buffer': {'max_seconds': 5, 'sample_rate_hz': 50},
            'health_check': {
                'first_frame_timeout_seconds': 10.0,
                'data_stale_timeout_seconds': 3.0
            }
        }
        
        def dummy_callback(device_num, timestamp, data):
            pass
        
        device = IMUDevice(
            number=1,
            name="TestDevice",
            mac="00:00:00:00:00:00",
            callback=dummy_callback,
            config=config
        )
        
        # Simulate device model for callback
        class MockDeviceModel:
            def __init__(self):
                self.deviceData = {
                    'AccX': 0.1, 'AccY': 0.05, 'AccZ': 1.0,
                    'AngX': 0, 'AngY': 0, 'AngZ': 0,
                    'AsX': 0, 'AsY': 0, 'AsZ': 0
                }
            
            def check_sliding_window_health(self):
                return {
                    'healthy': True,
                    'exceeded_count': 0,
                    'percentage': 0.0,
                    'last_check_time': time.time()
                }
        
        # Trigger data callback
        mock_model = MockDeviceModel()
        device.data_callback(mock_model)
        
        # Check health
        health_status = device.check_health(config['health_check'])
        
        assert device.health_status['first_frame_received'] == True
        assert device.health_status['is_healthy'] == True
        assert device.connected == True
        
        print("PASS: IMU device health monitoring working")
        print(f"  First frame received: {device.health_status['first_frame_received']}")
        print(f"  Is healthy: {device.health_status['is_healthy']}")
        print(f"  Connected: {device.connected}")
        print(f"  Buffer size: {len(device.buffer)}")
        
        return True
        
    except Exception as e:
        print(f"FAIL: IMU device health test failed - {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests and provide summary"""
    print("\n" + "🧪"*30)
    print("TRAIN DETECTOR PROFESSIONAL EDITION - TEST SUITE")
    print("🧪"*30)
    
    tests = [
        ("Configuration Loading", test_configuration_loading),
        ("Circular Buffer", test_circular_buffer),
        ("Sliding Window", test_sliding_window_config),
        ("Cloud Uploader", test_cloud_uploader),
        ("IMU Device Health", test_imu_device_health)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\nEXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
        
        time.sleep(1)  # Brief pause between tests
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {test_name}: {status}")
        if result:
            passed += 1
    
    print("="*60)
    print(f"Result: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed - review output above")
    
    print("="*60)
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
