#!/usr/bin/env python3
# coding:UTF-8
"""
服务器端 - 数据接收API
接收来自树莓派的数据并存储到数据库
"""

from flask import Flask, request, jsonify
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import logging

app = Flask(__name__)

# ==================== 配置 ====================
class ServerConfig:
    # 服务器配置
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = False
    
    # API密钥（需要和树莓派配置文件中的一致）
    API_KEY = 'your-secret-key-here'
    
    # 数据库路径
    DB_PATH = 'train_monitoring.db'
    
    # 日志路径
    LOG_FILE = 'server.log'


# ==================== 数据库管理 ====================
class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 火车通过事件表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS train_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration REAL NOT NULL,
                peak_acceleration REAL NOT NULL,
                background_rms REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                received_at TEXT NOT NULL,
                INDEX idx_device (device),
                INDEX idx_start_time (start_time)
            )
        ''')
        
        # 设备状态表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                system_name TEXT,
                location TEXT,
                devices_json TEXT NOT NULL,
                network_stats_json TEXT,
                received_at TEXT NOT NULL,
                INDEX idx_timestamp (timestamp)
            )
        ''')
        
        # 接收日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receive_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                INDEX idx_timestamp (timestamp)
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("数据库初始化完成")
    
    def insert_event(self, event_data):
        """插入火车通过事件"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO train_events 
            (device, start_time, end_time, duration, peak_acceleration, 
             background_rms, sample_count, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_data['device'],
            event_data['start_time'],
            event_data['end_time'],
            event_data['duration'],
            event_data['peak_acceleration'],
            event_data['background_rms'],
            event_data['sample_count'],
            datetime.now().isoformat()
        ))
        
        conn.commit()
        event_id = cursor.lastrowid
        conn.close()
        
        return event_id
    
    def insert_status(self, status_data):
        """插入设备状态"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO device_status 
            (timestamp, system_name, location, devices_json, network_stats_json, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            status_data.get('timestamp'),
            status_data.get('system_name'),
            status_data.get('location'),
            json.dumps(status_data.get('devices', [])),
            json.dumps(status_data.get('network_stats', {})),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        status_id = cursor.lastrowid
        conn.close()
        
        return status_id
    
    def log_receive(self, endpoint, success, error_message=None):
        """记录接收日志"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO receive_log (timestamp, endpoint, success, error_message)
            VALUES (?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            endpoint,
            1 if success else 0,
            error_message
        ))
        
        conn.commit()
        conn.close()
    
    def get_recent_events(self, limit=50):
        """获取最近的事件"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM train_events 
            ORDER BY start_time DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_stats(self):
        """获取统计信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 总事件数
        cursor.execute('SELECT COUNT(*) as total FROM train_events')
        total_events = cursor.fetchone()['total']
        
        # 今日事件数
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(*) as today_count 
            FROM train_events 
            WHERE start_time LIKE ?
        ''', (f'{today}%',))
        today_events = cursor.fetchone()['today_count']
        
        # 每个设备的事件数
        cursor.execute('''
            SELECT device, COUNT(*) as count 
            FROM train_events 
            GROUP BY device
        ''')
        device_counts = {row['device']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'total_events': total_events,
            'today_events': today_events,
            'device_counts': device_counts
        }


# ==================== 全局变量 ====================
db = Database(ServerConfig.DB_PATH)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(ServerConfig.LOG_FILE),
        logging.StreamHandler()
    ]
)


# ==================== API端点 ====================

def verify_api_key():
    """验证API密钥"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    
    try:
        token = auth_header.split('Bearer ')[1]
        return token == ServerConfig.API_KEY
    except:
        return False


@app.route('/')
def index():
    """首页 - 显示基本信息"""
    return jsonify({
        'service': 'Train Monitoring System API',
        'version': '1.0',
        'status': 'running'
    })


@app.route('/api/events', methods=['POST'])
def receive_event():
    """接收火车通过事件"""
    if not verify_api_key():
        db.log_receive('/api/events', False, 'Unauthorized')
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        
        # 验证必要字段
        required_fields = ['device', 'start_time', 'end_time', 'duration', 
                          'peak_acceleration', 'background_rms', 'sample_count']
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f'Missing field: {field}')
        
        # 插入数据库
        event_id = db.insert_event(data)
        
        # 记录日志
        db.log_receive('/api/events', True)
        logging.info(f"接收事件: 设备={data['device']}, 时长={data['duration']}s, ID={event_id}")
        
        return jsonify({
            'status': 'success',
            'event_id': event_id
        }), 200
    
    except Exception as e:
        error_msg = str(e)
        db.log_receive('/api/events', False, error_msg)
        logging.error(f"接收事件失败: {error_msg}")
        return jsonify({'error': error_msg}), 400


@app.route('/api/status', methods=['POST'])
def receive_status():
    """接收设备状态"""
    if not verify_api_key():
        db.log_receive('/api/status', False, 'Unauthorized')
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        
        # 插入数据库
        status_id = db.insert_status(data)
        
        # 记录日志
        db.log_receive('/api/status', True)
        logging.debug(f"接收状态: 系统={data.get('system_name')}, ID={status_id}")
        
        return jsonify({
            'status': 'success',
            'status_id': status_id
        }), 200
    
    except Exception as e:
        error_msg = str(e)
        db.log_receive('/api/status', False, error_msg)
        logging.error(f"接收状态失败: {error_msg}")
        return jsonify({'error': error_msg}), 400


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计信息（公开端点，用于快速查看）"""
    try:
        stats = db.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        logging.error(f"获取统计失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/events/recent', methods=['GET'])
def get_recent_events():
    """获取最近的事件（公开端点，用于快速查看）"""
    try:
        limit = request.args.get('limit', 50, type=int)
        events = db.get_recent_events(limit)
        return jsonify({'events': events}), 200
    except Exception as e:
        logging.error(f"获取事件失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== 主程序 ====================
if __name__ == '__main__':
    logging.info("=" * 60)
    logging.info("服务器启动")
    logging.info(f"监听: {ServerConfig.HOST}:{ServerConfig.PORT}")
    logging.info(f"数据库: {ServerConfig.DB_PATH}")
    logging.info("=" * 60)
    
    app.run(
        host=ServerConfig.HOST,
        port=ServerConfig.PORT,
        debug=ServerConfig.DEBUG
    )
