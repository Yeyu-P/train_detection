#!/usr/bin/env python3
"""
Cleanup Script - Force disconnect all IMU devices
Resolves connection residue issues
"""
import asyncio
import json
import sys

try:
    import bleak
except ImportError:
    print("bleak not installed! Run: pip3 install bleak")
    sys.exit(1)


async def disconnect_device(mac_address, name):
    """Disconnect specified device"""
    print(f"Disconnecting {name} ({mac_address})...")
    
    try:
        client = bleak.BleakClient(mac_address, timeout=5.0)
        
        # Try to connect then immediately disconnect
        await client.connect()
        
        if client.is_connected:
            await client.disconnect()
            print(f"   {name} disconnected")
            return True
        else:
            print(f"   {name} was not connected")
            return True
            
    except asyncio.TimeoutError:
        print(f"   {name} not found (already disconnected)")
        return True
    except Exception as e:
        print(f"   {name} error: {e}")
        return False


async def cleanup_all():
    """Clean up all device connections"""
    print("=" * 60)
    print("IMU Connection Cleanup Tool")
    print("=" * 60)
    
    # Read config file
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            devices = config.get('devices', [])
    except FileNotFoundError:
        print("config.json not found!")
        print("   Please run this script in the project directory")
        return
    except Exception as e:
        print(f"Config error: {e}")
        return
    
    if not devices:
        print("No devices in config")
        return
    
    print(f"\nFound {len(devices)} devices in config\n")
    
    # Disconnect all devices
    tasks = []
    for dev in devices:
        if dev.get('enabled', True):
            task = disconnect_device(dev['mac'], dev['name'])
            tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count results
    success = sum(1 for r in results if r is True)
    
    print("\n" + "=" * 60)
    print(f"Cleanup complete: {success}/{len(tasks)} devices processed")
    print("=" * 60)
    print("\nYou can now run train_detector_stable.py again")


async def force_cleanup_all_ble():
    """Scan and disconnect all Witmotion devices"""
    print("\nScanning for Witmotion devices...")
    
    devices = await bleak.BleakScanner.discover(timeout=5.0)
    
    witmotion_devices = [
        d for d in devices 
        if d.name and ('WT' in d.name.upper() or 'BLE' in d.name.upper())
    ]
    
    if not witmotion_devices:
        print("   No Witmotion devices found")
        return
    
    print(f"\nFound {len(witmotion_devices)} Witmotion device(s):\n")
    
    for device in witmotion_devices:
        print(f"   {device.address} - {device.name}")
        await disconnect_device(device.address, device.name)


def main():
    print("\nOptions:")
    print("1. Disconnect devices from config file (recommended)")
    print("2. Scan and disconnect all Witmotion devices")
    print("3. Both")
    
    try:
        choice = input("\nEnter choice [1-3]: ").strip()
    except KeyboardInterrupt:
        print("\n\nCancelled")
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
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()
