#!/usr/bin/env python3
"""
Mock Cloud Server for Testing
Receives uploaded event data and saves locally
"""

from flask import Flask, request, jsonify
import os
import json
from datetime import datetime

app = Flask(__name__)

UPLOAD_DIR = "cloud_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route('/api/upload', methods=['POST'])
def upload_event():
    """Receive event data upload"""
    try:
        metadata_json = request.form.get('metadata')
        if not metadata_json:
            return jsonify({'error': 'No metadata provided'}), 400
        
        metadata = json.loads(metadata_json)
        event_id = metadata.get('event_id', 'unknown')
        
        event_dir = os.path.join(UPLOAD_DIR, event_id)
        os.makedirs(event_dir, exist_ok=True)
        
        metadata_path = os.path.join(event_dir, 'metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        for filename, file_obj in request.files.items():
            filepath = os.path.join(event_dir, filename)
            file_obj.save(filepath)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Received event: {event_id}")
        
        return jsonify({
            'status': 'success',
            'event_id': event_id,
            'message': f'Event {event_id} uploaded successfully'
        }), 200
        
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def status():
    """Check server status"""
    events = [d for d in os.listdir(UPLOAD_DIR) if os.path.isdir(os.path.join(UPLOAD_DIR, d))]
    return jsonify({
        'status': 'online',
        'total_events': len(events),
        'upload_dir': UPLOAD_DIR
    })

if __name__ == '__main__':
    print("=" * 60)
    print("Mock Cloud Server Starting")
    print(f"Upload endpoint: http://localhost:8000/api/upload")
    print(f"Status endpoint: http://localhost:8000/api/status")
    print(f"Uploads will be saved to: {UPLOAD_DIR}/")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8000, debug=False)
