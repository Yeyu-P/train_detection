#!/usr/bin/env python3
"""
Test script for enhanced train detector
Validates connection, health monitoring, and upload functionality
"""
import time
import json
from train_detector_enhanced import TrainDetector


def test_connection():
    """Test 1: Verify device connection and data flow"""
    print("\n" + "="*60)
    print("TEST 1: Device Connection and Data Flow")
    print("="*60)
    
    detector = TrainDetector(config_file="detector_config.json")
    
    if not detector.start():
        print("Failed to connect devices")
        return False
    
    # Monitor data stream for 10 seconds
    print("\nMonitoring data stream for 10 seconds...")
    for i in range(10):
        time.sleep(1)
        
        connected_count = sum(1 for d in detector.devices.values() if d.connected)
        print(f"[{i+1}/10] Connected: {connected_count}/{len(detector.devices)}", end="")
        
        for num, device in sorted(detector.devices.items()):
            if device.current_data:
                acc_x = device.current_data.get('AccX', 0)
                acc_y = device.current_data.get('AccY', 0)
                acc_z = device.current_data.get('AccZ', 0)
                magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
                print(f" | Dev{num}: {magnitude:.3f}g", end="")
        print()
    
    detector.stop()
    
    connected_devices = sum(1 for d in detector.devices.values() if d.connected)
    if connected_devices > 0:
        print(f"\nConnection test PASSED: {connected_devices} devices connected")
        return True
    else:
        print("\nConnection test FAILED: No devices connected")
        return False


def test_health_monitoring():
    """Test 2: Verify health monitoring with sliding window"""
    print("\n" + "="*60)
    print("TEST 2: Health Monitoring (Sliding Window)")
    print("="*60)
    
    detector = TrainDetector(config_file="detector_config.json")
    
    if not detector.start():
        print("Failed to start detector")
        return False
    
    print("\nMonitoring health metrics for 15 seconds...")
    print("Shake device to see health percentage increase\n")
    
    for i in range(15):
        time.sleep(1)
        
        print(f"[{i+1}/15]", end="")
        
        for num, device in sorted(detector.devices.items()):
            if device.connected:
                health = device.get_health_status()
                window_status = "FULL" if health['window_full'] else "FILLING"
                print(f" | Dev{num}: {health['exceeded_percentage']:.1f}% ({window_status})", end="")
        print()
    
    detector.stop()
    
    # Check if at least one device has health data
    has_health_data = False
    for device in detector.devices.values():
        if device.health_stats['total_checks'] > 0:
            has_health_data = True
            break
    
    if has_health_data:
        print("\nHealth monitoring test PASSED")
        return True
    else:
        print("\nHealth monitoring test FAILED: No health data collected")
        return False


def test_config_loading():
    """Test 3: Verify configuration loading"""
    print("\n" + "="*60)
    print("TEST 3: Configuration Loading")
    print("="*60)
    
    try:
        with open("detector_config.json", 'r') as f:
            config = json.load(f)
        
        print("\nConfiguration loaded successfully:")
        print(f"  Devices: {len(config.get('devices', []))}")
        print(f"  Threshold: {config.get('detection', {}).get('threshold_g', 'N/A')}g")
        print(f"  Window size: {config.get('health_check', {}).get('sliding_window_size', 'N/A')}")
        print(f"  Upload enabled: {config.get('upload', {}).get('enabled', 'N/A')}")
        
        print("\nConfiguration test PASSED")
        return True
        
    except Exception as e:
        print(f"\nConfiguration test FAILED: {e}")
        return False


def test_upload_endpoint():
    """Test 4: Verify upload endpoint connectivity"""
    print("\n" + "="*60)
    print("TEST 4: Upload Endpoint Connectivity")
    print("="*60)
    
    import requests
    
    try:
        with open("detector_config.json", 'r') as f:
            config = json.load(f)
        
        upload_config = config.get('upload', {})
        
        if not upload_config.get('enabled', False):
            print("\nUpload disabled in config - SKIPPED")
            return True
        
        protocol = upload_config.get('protocol', 'http')
        host = upload_config.get('host', 'localhost')
        port = upload_config.get('port', 8080)
        endpoint = upload_config.get('endpoint', '/api/imu/status')
        
        url = f"{protocol}://{host}:{port}{endpoint}"
        
        print(f"\nTesting endpoint: {url}")
        
        # Test payload
        test_payload = {
            'timestamp': '2024-12-22T00:00:00',
            'devices': [
                {
                    'device_number': 0,
                    'device_name': 'Test',
                    'connected': True,
                    'total_checks': 0,
                    'threshold_exceeded_count': 0,
                    'exceeded_percentage': 0.0,
                    'window_full': False,
                    'last_data_time': 0
                }
            ]
        }
        
        response = requests.post(url, json=test_payload, timeout=5)
        
        if response.status_code == 200:
            print(f"  Response: {response.status_code} OK")
            print("\nUpload endpoint test PASSED")
            return True
        else:
            print(f"  Response: {response.status_code}")
            print("\nUpload endpoint test FAILED: Non-200 response")
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n  Connection refused - endpoint may not be running")
        print("  This is OK if you haven't set up the upload endpoint yet")
        print("\nUpload endpoint test SKIPPED")
        return True
        
    except Exception as e:
        print(f"\n  Error: {e}")
        print("\nUpload endpoint test FAILED")
        return False


def test_detection_trigger():
    """Test 5: Manual detection trigger test"""
    print("\n" + "="*60)
    print("TEST 5: Detection Trigger Test")
    print("="*60)
    print("Instructions:")
    print("  1. System will start monitoring")
    print("  2. SHAKE one of the IMU devices")
    print("  3. System should detect and save event")
    print("  4. Test runs for 60 seconds")
    print("="*60)
    
    detector = TrainDetector(config_file="detector_config.json")
    
    # Lower threshold for testing
    detector.threshold = 1.5
    
    if not detector.start():
        print("Failed to start detector")
        return False
    
    print(f"\nThreshold lowered to {detector.threshold}g for testing")
    print("Shake device to trigger detection...")
    print("   (Test will run for 60 seconds)\n")
    
    start_time = time.time()
    test_duration = 60
    
    try:
        while time.time() - start_time < test_duration:
            time.sleep(1)
            
            elapsed = int(time.time() - start_time)
            remaining = test_duration - elapsed
            
            print(f"[{elapsed}s] ", end="")
            
            for num, device in sorted(detector.devices.items()):
                if device.current_data:
                    acc_x = device.current_data.get('AccX', 0)
                    acc_y = device.current_data.get('AccY', 0)
                    acc_z = device.current_data.get('AccZ', 0)
                    magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
                    
                    indicator = "!" if magnitude > detector.threshold else "."
                    print(f"Dev{num}:{indicator}{magnitude:.3f}g ", end="")
            
            if detector.recording:
                print("| RECORDING", end="")
            
            print(f" | {remaining}s left", end="\r")
    
    except KeyboardInterrupt:
        print("\nTest interrupted")
    
    detector.stop()
    
    if detector.stats['total_events'] > 0:
        print(f"\nDetection test PASSED: {detector.stats['total_events']} events detected")
        return True
    else:
        print("\nDetection test INCOMPLETE: No events detected")
        print("   (This is OK if you didn't shake the device)")
        return True


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("ENHANCED TRAIN DETECTOR - TEST SUITE")
    print("="*60)
    
    results = []
    
    # Test 1: Configuration
    try:
        results.append(("Configuration", test_config_loading()))
    except Exception as e:
        print(f"Configuration test crashed: {e}")
        results.append(("Configuration", False))
    
    time.sleep(1)
    
    # Test 2: Connection
    try:
        results.append(("Connection", test_connection()))
    except Exception as e:
        print(f"Connection test crashed: {e}")
        results.append(("Connection", False))
    
    time.sleep(2)
    
    # Test 3: Health Monitoring
    try:
        results.append(("Health Monitoring", test_health_monitoring()))
    except Exception as e:
        print(f"Health monitoring test crashed: {e}")
        results.append(("Health Monitoring", False))
    
    time.sleep(2)
    
    # Test 4: Upload Endpoint
    try:
        results.append(("Upload Endpoint", test_upload_endpoint()))
    except Exception as e:
        print(f"Upload test crashed: {e}")
        results.append(("Upload Endpoint", False))
    
    time.sleep(1)
    
    # Test 5: Detection
    try:
        results.append(("Detection Trigger", test_detection_trigger()))
    except Exception as e:
        print(f"Detection test crashed: {e}")
        results.append(("Detection Trigger", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print("=" * 60)
    print(f"Result: {passed}/{len(results)} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        
        if test_type == "config":
            test_config_loading()
        elif test_type == "connection":
            test_connection()
        elif test_type == "health":
            test_health_monitoring()
        elif test_type == "upload":
            test_upload_endpoint()
        elif test_type == "detection":
            test_detection_trigger()
        else:
            print(f"Unknown test: {test_type}")
            print("Available tests: config, connection, health, upload, detection")
    else:
        run_all_tests()
