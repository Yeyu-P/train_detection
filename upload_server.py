#!/usr/bin/env python3
"""
Example upload endpoint server
Simple Flask server to receive IMU health status uploads
"""
from flask import Flask, request, jsonify
from datetime import datetime
import json

app = Flask(__name__)

# Store received data in memory (for demonstration)
received_data = []


@app.route('/api/imu/status', methods=['POST'])
def receive_status():
    """Receive IMU health status"""
    try:
        data = request.json
        
        # Log receipt
        timestamp = data.get('timestamp', datetime.now().isoformat())
        devices = data.get('devices', [])
        
        print(f"\n[{timestamp}] Received status from {len(devices)} devices")
        
        # Print device summaries
        for device in devices:
            print(f"  Device {device['device_number']} ({device['device_name']}):")
            print(f"    Connected: {device['connected']}")
            print(f"    Health: {device['exceeded_percentage']:.1f}% exceeded")
            print(f"    Total checks: {device['total_checks']}")
        
        # Store data
        received_data.append({
            'received_at': datetime.now().isoformat(),
            'payload': data
        })
        
        # Keep only last 100 entries
        if len(received_data) > 100:
            received_data.pop(0)
        
        return jsonify({
            "status": "ok",
            "message": "Data received successfully",
            "devices_count": len(devices)
        }), 200
        
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


@app.route('/api/imu/history', methods=['GET'])
def get_history():
    """Get upload history"""
    return jsonify({
        "total_uploads": len(received_data),
        "history": received_data[-10:]  # Last 10 entries
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "uptime": "running",
        "total_uploads": len(received_data)
    }), 200


def main():
    """Run the server"""
    print("=" * 60)
    print("IMU Status Upload Server")
    print("=" * 60)
    print("Endpoints:")
    print("  POST /api/imu/status   - Receive IMU status")
    print("  GET  /api/imu/history  - View upload history")
    print("  GET  /health           - Health check")
    print("=" * 60)
    print("\nStarting server on http://0.0.0.0:8080")
    print("Press Ctrl+C to stop\n")
    
    try:
        app.run(host='0.0.0.0', port=8080, debug=False)
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == '__main__':
    main()
