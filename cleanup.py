#!/usr/bin/env python3
"""
清理脚本 - 强制断开所有IMU设备连接
用于解决连接残留问题
"""
import asyncio
import json
import sys

try:
    import bleak
except ImportError:
    print("❌ bleak not installed! Run: pip3 install bleak")
    sys.exit(1)


async def disconnect_device(mac_address, name):
    """断开指定设备"""
    print(f"🔌 Disconnecting {name} ({mac_address})...")
    
    try:
        client = bleak.BleakClient(mac_address, timeout=5.0)
        
        # 尝试连接然后立即断开
        await client.connect()
        
        if client.is_connected:
            await client.disconnect()
            print(f"   ✅ {name} disconnected")
            return True
        else:
            print(f"   ℹ️  {name} was not connected")
            return True
            
    except asyncio.TimeoutError:
        print(f"   ℹ️  {name} not found (already disconnected)")
        return True
    except Exception as e:
        print(f"   ⚠️  {name} error: {e}")
        return False


async def cleanup_all():
    """清理所有设备连接"""
    print("=" * 60)
    print("🧹 IMU Connection Cleanup Tool")
    print("=" * 60)
    
    # 读取配置文件
    try:
        with open('witmotion_config.json', 'r') as f:
            config = json.load(f)
            devices = config.get('devices', [])
    except FileNotFoundError:
        print("❌ witmotion_config.json not found!")
        print("   Please run this script in the project directory")
        return
    except Exception as e:
        print(f"❌ Config error: {e}")
        return
    
    if not devices:
        print("❌ No devices in config")
        return
    
    print(f"\n📋 Found {len(devices)} devices in config\n")
    
    # 断开所有设备
    tasks = []
    for dev in devices:
        if dev.get('enabled', True):
            task = disconnect_device(dev['mac'], dev['name'])
            tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 统计结果
    success = sum(1 for r in results if r is True)
    
    print("\n" + "=" * 60)
    print(f"✅ Cleanup complete: {success}/{len(tasks)} devices processed")
    print("=" * 60)
    print("\nYou can now run train_detector.py again")


async def force_cleanup_all_ble():
    """扫描并断开所有Witmotion设备"""
    print("\n🔍 Scanning for Witmotion devices...")
    
    devices = await bleak.BleakScanner.discover(timeout=5.0)
    
    witmotion_devices = [
        d for d in devices 
        if d.name and ('WT' in d.name.upper() or 'BLE' in d.name.upper())
    ]
    
    if not witmotion_devices:
        print("   ℹ️  No Witmotion devices found")
        return
    
    print(f"\n📱 Found {len(witmotion_devices)} Witmotion device(s):\n")
    
    for device in witmotion_devices:
        print(f"   • {device.address} - {device.name}")
        await disconnect_device(device.address, device.name)


def main():
    print("\nOptions:")
    print("1. Disconnect devices from config file (recommended)")
    print("2. Scan and disconnect all Witmotion devices")
    print("3. Both")
    
    try:
        choice = input("\nEnter choice [1-3]: ").strip()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled")
        return
    
    try:
        if choice == '1':
            asyncio.run(cleanup_all())
        elif choice == '2':
            asyncio.run(force_cleanup_all_ble())
        elif choice == '3':
            asyncio.run(cleanup_all())
            asyncio.run(force_cleanup_all_ble())
        else:
            print("Invalid choice")
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
