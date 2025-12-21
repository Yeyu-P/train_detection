#!/usr/bin/env python3
"""
简单的数据接收服务器
用于接收train_detector上传的数据
"""
from flask import Flask, request, jsonify
from datetime import datetime
import json

app = Flask(__name__)

# 存储接收到的数据
received_data = []

@app.route('/api/data', methods=['POST'])
def receive_data():
    """接收上传的数据"""
    try:
        data = request.get_json()
        
        # 打印接收到的数据
        print("\n" + "="*60)
        print(f"📥 Received data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # 打印设备状态
        if 'devices' in data:
            print(f"\n📱 Devices: {len(data['devices'])}")
            for device in data['devices']:
                print(f"\n  Device {device['number']}: {device['name']}")
                if 'sliding_window' in device:
                    sw = device['sliding_window']
                    status = "✅ Healthy" if sw.get('healthy', True) else "⚠️ Alert"
                    print(f"    Sliding Window: {status}")
                    print(f"    Percentage: {sw.get('percentage', 0):.1f}%")
                    print(f"    Exceeded: {sw.get('exceeded_count', 0)}/{sw.get('window_size', 0)}")
        
        # 打印统计信息
        if 'stats' in data:
            print(f"\n📊 Stats:")
            print(f"  Total Events: {data['stats'].get('total_events', 0)}")
        
        print("\n" + "="*60)
        
        # 保存到列表
        received_data.append({
            'received_at': datetime.now().isoformat(),
            'data': data
        })
        
        # 保存到文件（可选）
        with open('received_data.json', 'w') as f:
            json.dump(received_data, f, indent=2)
        
        return jsonify({'status': 'success', 'message': 'Data received'}), 200
        
    except Exception as e:
        print(f"❌ Error receiving data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/data', methods=['GET'])
def get_data():
    """查看接收到的数据"""
    return jsonify({
        'total_uploads': len(received_data),
        'data': received_data[-10:]  # 返回最近10条
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'running',
        'total_received': len(received_data),
        'last_received': received_data[-1]['received_at'] if received_data else None
    })


@app.route('/', methods=['GET'])
def index():
    """首页"""
    return f"""
    <html>
    <head><title>Data Receiver</title></head>
    <body>
        <h1>🚂 Train Detector Data Receiver</h1>
        <p>Server is running!</p>
        <p>Total uploads received: {len(received_data)}</p>
        <p>Last upload: {received_data[-1]['received_at'] if received_data else 'None'}</p>
        <hr>
        <h2>API Endpoints:</h2>
        <ul>
            <li>POST /api/data - Receive data</li>
            <li>GET /api/data - View received data</li>
            <li>GET /api/health - Health check</li>
        </ul>
        <hr>
        <h2>Recent Uploads:</h2>
        <pre>{json.dumps(received_data[-5:], indent=2)}</pre>
    </body>
    </html>
    """


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Starting Data Receiver Server")
    print("="*60)
    print("📡 Listening on: http://localhost:8000")
    print("📥 Upload endpoint: http://localhost:8000/api/data")
    print("📊 View data: http://localhost:8000/api/data")
    print("💚 Health check: http://localhost:8000/api/health")
    print("🌐 Web interface: http://localhost:8000")
    print("="*60)
    print("\nPress Ctrl+C to stop\n")
    
    # 启动服务器
    app.run(host='0.0.0.0', port=8000, debug=False)
