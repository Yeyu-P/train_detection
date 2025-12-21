#!/usr/bin/env python3
"""
Bluetooth Device Cleanup Utility
Force disconnect all IMU devices to resolve connection conflicts
"""

import asyncio
import json
import sys
from bleak import BleakScanner

async def disconnect_device(mac_address):
    """Attempt to disconnect a device by MAC address"""
    try:
        print(f"Disconnecting {mac_address}...")
        
        # Use system bluetoothctl to disconnect
        process = await asyncio.create_subprocess_exec(
            'bluetoothctl', 'disconnect', mac_address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 or b'not connected' in stderr.lower():
            print(f"  ✓ {mac_address} disconnected")
            return True
        else:
            print(f"  ✗ {mac_address} failed: {stderr.decode().strip()}")
            return False
            
    except Exception as e:
        print(f"  ✗ {mac_address} error: {e}")
        return False

async def cleanup_from_config(config_file="train_detection_config.json"):
    """Disconnect devices listed in config file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        devices = config.get('devices', [])
        if not devices:
            print("No devices found in config file")
            return
        
        print(f"Found {len(devices)} devices in config")
        print("=" * 50)
        
        tasks = []
        for device in devices:
            mac = device.get('mac')
            if mac:
                tasks.append(disconnect_device(mac))
        
        await asyncio.gather(*tasks)
        
    except FileNotFoundError:
        print(f"Config file '{config_file}' not found")
        print("Please run this script in the same directory as train_detection_config.json")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error parsing config file '{config_file}'")
        sys.exit(1)

async def cleanup_all_devices():
    """Scan and disconnect all nearby Bluetooth devices"""
    print("Scanning for nearby Bluetooth devices...")
    print("=" * 50)
    
    try:
        devices = await BleakScanner.discover(timeout=5.0)
        
        if not devices:
            print("No devices found")
            return
        
        print(f"Found {len(devices)} devices")
        print()
        
        tasks = []
        for device in devices:
            print(f"Found: {device.name or 'Unknown'} ({device.address})")
            tasks.append(disconnect_device(device.address))
        
        print()
        await asyncio.gather(*tasks)
        
    except Exception as e:
        print(f"Scan failed: {e}")

async def restart_bluetooth():
    """Restart Bluetooth service"""
    print("\nRestarting Bluetooth service...")
    print("=" * 50)
    
    try:
        # Stop bluetooth
        process = await asyncio.create_subprocess_exec(
            'sudo', 'systemctl', 'restart', 'bluetooth',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode == 0:
            print("✓ Bluetooth service restarted")
            await asyncio.sleep(2)
            return True
        else:
            print("✗ Failed to restart Bluetooth service")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def print_menu():
    """Print menu options"""
    print("\n" + "=" * 50)
    print("Bluetooth Device Cleanup Utility")
    print("=" * 50)
    print("1. Disconnect devices from config file")
    print("2. Scan and disconnect all devices")
    print("3. Restart Bluetooth service")
    print("4. Full cleanup (1 + 3)")
    print("5. Exit")
    print("=" * 50)

async def main():
    """Main cleanup routine"""
    if len(sys.argv) > 1:
        # Command line mode
        option = sys.argv[1]
        if option == "--config" or option == "-c":
            await cleanup_from_config()
        elif option == "--all" or option == "-a":
            await cleanup_all_devices()
        elif option == "--restart" or option == "-r":
            await restart_bluetooth()
        elif option == "--full" or option == "-f":
            await cleanup_from_config()
            await restart_bluetooth()
        else:
            print("Usage:")
            print("  python3 cleanup.py              # Interactive menu")
            print("  python3 cleanup.py --config     # Disconnect config devices")
            print("  python3 cleanup.py --all        # Disconnect all devices")
            print("  python3 cleanup.py --restart    # Restart Bluetooth")
            print("  python3 cleanup.py --full       # Config + Restart")
    else:
        # Interactive mode
        while True:
            print_menu()
            choice = input("Select option (1-5): ").strip()
            
            if choice == '1':
                await cleanup_from_config()
            elif choice == '2':
                await cleanup_all_devices()
            elif choice == '3':
                await restart_bluetooth()
            elif choice == '4':
                await cleanup_from_config()
                await restart_bluetooth()
            elif choice == '5':
                print("Exiting...")
                break
            else:
                print("Invalid option")
            
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
