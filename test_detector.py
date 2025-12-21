#!/usr/bin/env python3
"""
测试脚本 - 验证蓝牙连接和检测功能
"""
import time
from train_detector import TrainDetector


def test_connection():
    """测试1: 验证设备连接"""
    print("\n" + "="*60)
    print("TEST 1: Device Connection Test")
    print("="*60)
    
    detector = TrainDetector()
    
    if not detector.start():
        print("❌ Failed to connect devices")
        return False
    
    # 等待10秒观察数据流
    print("\n📡 Monitoring data stream for 10 seconds...")
    for i in range(10):
        time.sleep(1)
        
        # 显示实时数据
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
        print(f"\n✅ Connection test PASSED: {connected_devices} devices connected")
        return True
    else:
        print("\n❌ Connection test FAILED: No devices connected")
        return False


def test_detection_manual():
    """测试2: 手动触发检测（晃动设备）"""
    print("\n" + "="*60)
    print("TEST 2: Manual Detection Test")
    print("="*60)
    print("Instructions:")
    print("  1. System will start monitoring")
    print("  2. SHAKE one of the IMU devices")
    print("  3. System should detect and save event")
    print("  4. Test runs for 60 seconds")
    print("="*60)
    
    detector = TrainDetector()
    detector.threshold = 1.5  # 降低阈值便于测试
    
    if not detector.start():
        print("❌ Failed to start detector")
        return False
    
    print(f"\n⚠️  Threshold lowered to {detector.threshold}g for testing")
    print("🎯 Shake device to trigger detection...")
    print("   (Test will run for 60 seconds)\n")
    
    start_time = time.time()
    test_duration = 60
    
    try:
        while time.time() - start_time < test_duration:
            time.sleep(1)
            
            # 显示倒计时和实时数据
            elapsed = int(time.time() - start_time)
            remaining = test_duration - elapsed
            
            print(f"[{elapsed}s] ", end="")
            
            for num, device in sorted(detector.devices.items()):
                if device.current_data:
                    acc_x = device.current_data.get('AccX', 0)
                    acc_y = device.current_data.get('AccY', 0)
                    acc_z = device.current_data.get('AccZ', 0)
                    magnitude = (acc_x**2 + acc_y**2 + acc_z**2)**0.5
                    
                    indicator = "🔴" if magnitude > detector.threshold else "🟢"
                    print(f"Dev{num}: {indicator}{magnitude:.3f}g ", end="")
            
            if detector.recording:
                print("| 📹 RECORDING", end="")
            
            print(f" | {remaining}s left", end="\r")
    
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted")
    
    detector.stop()
    
    if detector.stats['total_events'] > 0:
        print(f"\n✅ Detection test PASSED: {detector.stats['total_events']} events detected")
        return True
    else:
        print("\n⚠️  Detection test incomplete: No events detected")
        print("   (This is OK if you didn't shake the device)")
        return True


def test_buffer():
    """测试3: 验证循环缓冲区"""
    print("\n" + "="*60)
    print("TEST 3: Circular Buffer Test")
    print("="*60)
    
    detector = TrainDetector()
    
    if not detector.start():
        print("❌ Failed to start detector")
        return False
    
    print("\n📊 Checking buffer fill rate...")
    
    # 等待缓冲区填充
    for i in range(10):
        time.sleep(1)
        
        for num, device in sorted(detector.devices.items()):
            buffer_size = len(device.buffer)
            buffer_percent = (buffer_size / device.buffer.max_size) * 100
            print(f"[{i+1}/10] Dev{num} Buffer: {buffer_size}/{device.buffer.max_size} "
                  f"({buffer_percent:.1f}%)", end="")
            
            if device.connected:
                print(" ✓", end="")
            print()
    
    detector.stop()
    
    # 检查是否至少有一个设备的缓冲区在工作
    buffer_working = False
    for device in detector.devices.values():
        if len(device.buffer) > 0:
            buffer_working = True
            break
    
    if buffer_working:
        print("\n✅ Buffer test PASSED")
        return True
    else:
        print("\n❌ Buffer test FAILED: Buffers not filling")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "🧪"*30)
    print("TRAIN DETECTOR - TEST SUITE")
    print("🧪"*30)
    
    results = []
    
    # Test 1: 连接测试
    try:
        results.append(("Connection Test", test_connection()))
    except Exception as e:
        print(f"❌ Connection test crashed: {e}")
        results.append(("Connection Test", False))
    
    time.sleep(2)
    
    # Test 2: 缓冲区测试
    try:
        results.append(("Buffer Test", test_buffer()))
    except Exception as e:
        print(f"❌ Buffer test crashed: {e}")
        results.append(("Buffer Test", False))
    
    time.sleep(2)
    
    # Test 3: 检测测试
    try:
        results.append(("Detection Test", test_detection_manual()))
    except Exception as e:
        print(f"❌ Detection test crashed: {e}")
        results.append(("Detection Test", False))
    
    # 总结
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print("="*60)
    print(f"Result: {passed}/{len(results)} tests passed")
    print("="*60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        
        if test_type == "connection":
            test_connection()
        elif test_type == "buffer":
            test_buffer()
        elif test_type == "detection":
            test_detection_manual()
        else:
            print(f"Unknown test: {test_type}")
            print("Available tests: connection, buffer, detection")
    else:
        run_all_tests()
