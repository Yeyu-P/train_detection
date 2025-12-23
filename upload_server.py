#!/usr/bin/env python3
"""
IMU Health Monitoring Upload Server
Receives and processes health data from train detection system
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from aiohttp import web
import sqlite3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('upload_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HealthDataStore:
    """Store health data to SQLite database"""
    
    def __init__(self, db_path="health_data.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # System status table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                uptime_hours REAL,
                total_events INTEGER,
                total_reconnects INTEGER,
                total_os_cleanups INTEGER,
                upload_count INTEGER,
                upload_failures INTEGER
            )
        ''')

        # IMU status table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS imu_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id INTEGER,
                timestamp TEXT,
                imu_number INTEGER,
                imu_name TEXT,
                mac_address TEXT,
                is_ready BOOLEAN,
                state TEXT,
                consecutive_failures INTEGER,
                buffer_size INTEGER,
                time_since_last_data REAL,
                basic_health_status BOOLEAN,
                basic_health_reason TEXT,
                window_health_status BOOLEAN,
                window_health_reason TEXT,
                window_total_checks INTEGER,
                window_unhealthy_count INTEGER,
                window_unhealthy_percentage REAL,
                acc_x REAL,
                acc_y REAL,
                acc_z REAL,
                FOREIGN KEY (system_id) REFERENCES system_status(id)
            )
        ''')

        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                imu_number INTEGER,
                imu_name TEXT,
                alert_type TEXT,
                severity TEXT,
                message TEXT,
                resolved BOOLEAN DEFAULT 0
            )
        ''')

        # NEW: Train events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS train_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                event_type TEXT,
                trigger_time TEXT,
                end_time TEXT,
                duration REAL,
                trigger_device INTEGER,
                z_magnitude REAL,
                max_acceleration REAL,
                created_at TEXT
            )
        ''')

        # NEW: Event summary table (per-device statistics)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                device_number INTEGER,
                sample_count INTEGER,
                max_z_acceleration REAL,
                avg_z_acceleration REAL,
                calibration_offset REAL,
                FOREIGN KEY (event_id) REFERENCES train_events(event_id)
            )
        ''')

        # NEW: Warnings table (separate from alerts for system warnings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                warning_type TEXT,
                device_number INTEGER,
                device_name TEXT,
                message TEXT,
                severity TEXT
            )
        ''')

        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    def store_health_data(self, data):
        """Store received health data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Parse timestamp
            timestamp = data.get('timestamp', datetime.now().isoformat())
            system = data.get('system', {})
            
            # Calculate uptime
            uptime_start = system.get('uptime_start', 0)
            if uptime_start > 0:
                uptime_hours = (datetime.now().timestamp() - uptime_start) / 3600
            else:
                uptime_hours = 0
            
            # Insert system status
            cursor.execute('''
                INSERT INTO system_status 
                (timestamp, uptime_hours, total_events, total_reconnects, 
                 total_os_cleanups, upload_count, upload_failures)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                uptime_hours,
                system.get('total_events', 0),
                system.get('total_reconnects', 0),
                system.get('total_os_cleanups', 0),
                system.get('upload_count', 0),
                system.get('upload_failures', 0)
            ))
            
            system_id = cursor.lastrowid
            
            # Insert IMU status
            imus = data.get('imus', [])
            for imu in imus:
                device_health = imu.get('device_health', {})
                basic_health = device_health.get('basic_health', {})
                sliding_window = device_health.get('sliding_window', {})
                window_stats = sliding_window.get('stats', {})
                current_data = imu.get('current_data', {})
                
                cursor.execute('''
                    INSERT INTO imu_status
                    (system_id, timestamp, imu_number, imu_name, mac_address,
                     is_ready, state, consecutive_failures, buffer_size,
                     time_since_last_data, basic_health_status, basic_health_reason,
                     window_health_status, window_health_reason,
                     window_total_checks, window_unhealthy_count, window_unhealthy_percentage,
                     acc_x, acc_y, acc_z)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    system_id,
                    timestamp,
                    imu.get('number', 0),
                    imu.get('name', ''),
                    imu.get('mac', ''),
                    imu.get('is_ready', False),
                    device_health.get('state', 'unknown'),
                    device_health.get('consecutive_failures', 0),
                    imu.get('buffer_size', 0),
                    device_health.get('time_since_last_data', -1),
                    basic_health.get('healthy', True),
                    basic_health.get('reason', ''),
                    sliding_window.get('healthy', True),
                    sliding_window.get('reason', ''),
                    window_stats.get('total_checks', 0),
                    window_stats.get('unhealthy_count', 0),
                    window_stats.get('unhealthy_percentage', 0.0),
                    current_data.get('AccX', 0.0),
                    current_data.get('AccY', 0.0),
                    current_data.get('AccZ', 0.0)
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Database storage error: {e}")
            return False
    
    def generate_alerts(self, data):
        """Generate alerts based on health data"""
        alerts = []
        
        try:
            imus = data.get('imus', [])
            timestamp = data.get('timestamp', datetime.now().isoformat())
            
            for imu in imus:
                imu_number = imu.get('number', 0)
                imu_name = imu.get('name', 'Unknown')
                device_health = imu.get('device_health', {})
                
                # Alert: Device not ready
                if not imu.get('is_ready', False):
                    alerts.append({
                        'timestamp': timestamp,
                        'imu_number': imu_number,
                        'imu_name': imu_name,
                        'alert_type': 'device_offline',
                        'severity': 'high',
                        'message': f"IMU-{imu_number} ({imu_name}) is not ready"
                    })
                
                # Alert: High consecutive failures
                consecutive_failures = device_health.get('consecutive_failures', 0)
                if consecutive_failures >= 2:
                    alerts.append({
                        'timestamp': timestamp,
                        'imu_number': imu_number,
                        'imu_name': imu_name,
                        'alert_type': 'high_failures',
                        'severity': 'medium',
                        'message': f"IMU-{imu_number} has {consecutive_failures} consecutive failures"
                    })
                
                # Alert: Sliding window unhealthy
                sliding_window = device_health.get('sliding_window', {})
                window_stats = sliding_window.get('stats', {})
                unhealthy_percentage = window_stats.get('unhealthy_percentage', 0.0)
                
                if unhealthy_percentage >= 50.0 and not sliding_window.get('healthy', True):
                    alerts.append({
                        'timestamp': timestamp,
                        'imu_number': imu_number,
                        'imu_name': imu_name,
                        'alert_type': 'sliding_window_failure',
                        'severity': 'medium',
                        'message': f"IMU-{imu_number} sliding window: {unhealthy_percentage:.1f}% unhealthy"
                    })
                
                # Alert: No data for extended period
                time_since_last_data = device_health.get('time_since_last_data', 0)
                if time_since_last_data > 10.0:
                    alerts.append({
                        'timestamp': timestamp,
                        'imu_number': imu_number,
                        'imu_name': imu_name,
                        'alert_type': 'no_data',
                        'severity': 'high',
                        'message': f"IMU-{imu_number} no data for {time_since_last_data:.1f}s"
                    })
            
            # Store alerts to database
            if alerts:
                self._store_alerts(alerts)
            
            return alerts
            
        except Exception as e:
            logger.error(f"Alert generation error: {e}")
            return []
    
    def _store_alerts(self, alerts):
        """Store alerts to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for alert in alerts:
                cursor.execute('''
                    INSERT INTO alerts
                    (timestamp, imu_number, imu_name, alert_type, severity, message)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    alert['timestamp'],
                    alert['imu_number'],
                    alert['imu_name'],
                    alert['alert_type'],
                    alert['severity'],
                    alert['message']
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Alert storage error: {e}")
    
    def get_recent_status(self, limit=10):
        """Get recent system status"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, uptime_hours, total_events, 
                       total_reconnects, total_os_cleanups
                FROM system_status
                ORDER BY id DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'timestamp': row[0],
                    'uptime_hours': row[1],
                    'total_events': row[2],
                    'total_reconnects': row[3],
                    'total_os_cleanups': row[4]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Query error: {e}")
            return []
    
    def get_active_alerts(self):
        """Get unresolved alerts"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, imu_number, imu_name, 
                       alert_type, severity, message
                FROM alerts
                WHERE resolved = 0
                ORDER BY id DESC
                LIMIT 50
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'timestamp': row[0],
                    'imu_number': row[1],
                    'imu_name': row[2],
                    'alert_type': row[3],
                    'severity': row[4],
                    'message': row[5]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Query error: {e}")
            return []


class HealthMonitoringServer:
    """HTTP server for receiving IMU health data"""
    
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.data_store = HealthDataStore()
        self.app = web.Application()
        self._setup_routes()
        
        # Statistics
        self.total_requests = 0
        self.total_errors = 0
        self.last_update_time = None
    
    def _setup_routes(self):
        """Setup HTTP routes"""
        # Health monitoring
        self.app.router.add_post('/api/imu/status', self.handle_status)
        self.app.router.add_get('/api/system/recent', self.handle_get_recent)
        self.app.router.add_get('/api/alerts/active', self.handle_get_alerts)
        self.app.router.add_get('/api/stats', self.handle_get_stats)

        # NEW: Train event endpoints
        self.app.router.add_post('/api/events/start', self.handle_event_start)
        self.app.router.add_post('/api/events/end', self.handle_event_end)
        self.app.router.add_post('/api/events/summary', self.handle_event_summary)
        self.app.router.add_post('/api/warnings', self.handle_warning)

        # Web interface
        self.app.router.add_get('/', self.handle_index)
    
    async def handle_status(self, request):
        """Handle IMU status upload"""
        self.total_requests += 1
        
        try:
            # Parse JSON data with validation
            try:
                data = await request.json()
            except json.JSONDecodeError as e:
                self.total_errors += 1
                logger.error(f"Invalid JSON: {e}")
                return web.Response(status=400, text="Invalid JSON format")
            
            # Validate required fields
            if not isinstance(data, dict):
                self.total_errors += 1
                return web.Response(status=400, text="Data must be a JSON object")
            
            if 'imus' not in data:
                self.total_errors += 1
                return web.Response(status=400, text="Missing required field: imus")
            
            if not isinstance(data['imus'], list):
                self.total_errors += 1
                return web.Response(status=400, text="Field 'imus' must be an array")
            
            # Log receipt
            num_imus = len(data.get('imus', []))
            logger.info(f"Received status from {num_imus} IMUs")
            
            # Store to database
            success = self.data_store.store_health_data(data)
            
            if not success:
                self.total_errors += 1
                return web.Response(status=500, text="Storage failed")
            
            # Generate alerts
            alerts = self.data_store.generate_alerts(data)
            
            # Log alerts
            for alert in alerts:
                severity = alert['severity'].upper()
                logger.warning(f"[{severity}] {alert['message']}")
            
            # Update timestamp
            self.last_update_time = datetime.now()
            
            # Print summary to console
            self._print_status_summary(data, alerts)
            
            return web.json_response({
                'status': 'ok',
                'alerts_generated': len(alerts)
            })
            
        except Exception as e:
            self.total_errors += 1
            logger.error(f"Status handling error: {e}")
            return web.Response(status=500, text=str(e))
    
    async def handle_get_recent(self, request):
        """Get recent system status"""
        try:
            limit = int(request.query.get('limit', '10'))
            recent = self.data_store.get_recent_status(limit)
            return web.json_response(recent)
        except Exception as e:
            logger.error(f"Recent status error: {e}")
            return web.Response(status=500, text=str(e))
    
    async def handle_get_alerts(self, request):
        """Get active alerts"""
        try:
            alerts = self.data_store.get_active_alerts()
            return web.json_response(alerts)
        except Exception as e:
            logger.error(f"Alerts query error: {e}")
            return web.Response(status=500, text=str(e))
    
    async def handle_get_stats(self, request):
        """Get server statistics"""
        return web.json_response({
            'total_requests': self.total_requests,
            'total_errors': self.total_errors,
            'error_rate': self.total_errors / max(self.total_requests, 1),
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None
        })

    async def handle_event_start(self, request):
        """Handle train detection start event"""
        self.total_requests += 1

        try:
            data = await request.json()

            event_id = data.get('event_id')
            logger.info(f"Train detected: {event_id}")
            print(f"\n🚂 TRAIN DETECTED: {event_id}")
            print(f"   Trigger device: IMU-{data.get('trigger_device')}")
            print(f"   Z-magnitude: {data.get('z_magnitude')}g")
            print(f"   Time: {data.get('trigger_time')}\n")

            # Store to database
            conn = sqlite3.connect(self.data_store.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR IGNORE INTO train_events
                (event_id, event_type, trigger_time, trigger_device, z_magnitude, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                event_id,
                data.get('event_type', 'train_detected'),
                data.get('trigger_time'),
                data.get('trigger_device'),
                data.get('z_magnitude'),
                datetime.now().isoformat()
            ))

            conn.commit()
            conn.close()

            return web.json_response({'status': 'ok'})

        except Exception as e:
            self.total_errors += 1
            logger.error(f"Event start error: {e}")
            return web.Response(status=500, text=str(e))

    async def handle_event_end(self, request):
        """Handle train passed (end) event"""
        self.total_requests += 1

        try:
            data = await request.json()

            event_id = data.get('event_id')
            logger.info(f"Train passed: {event_id}")
            print(f"\n✅ TRAIN PASSED: {event_id}")
            print(f"   Duration: {data.get('duration')}s")
            print(f"   Max acceleration: {data.get('max_acceleration')}g")
            print(f"   End time: {data.get('end_time')}\n")

            # Update database
            conn = sqlite3.connect(self.data_store.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE train_events
                SET end_time = ?, duration = ?, max_acceleration = ?
                WHERE event_id = ?
            ''', (
                data.get('end_time'),
                data.get('duration'),
                data.get('max_acceleration'),
                event_id
            ))

            conn.commit()
            conn.close()

            return web.json_response({'status': 'ok'})

        except Exception as e:
            self.total_errors += 1
            logger.error(f"Event end error: {e}")
            return web.Response(status=500, text=str(e))

    async def handle_event_summary(self, request):
        """Handle event summary with per-device statistics"""
        self.total_requests += 1

        try:
            data = await request.json()

            event_id = data.get('event_id')
            devices = data.get('devices', [])

            logger.info(f"Event summary: {event_id} ({len(devices)} devices)")
            print(f"\n📊 EVENT SUMMARY: {event_id}")
            for dev in devices:
                print(f"   IMU-{dev.get('device_number')}: {dev.get('sample_count')} samples, "
                      f"max_z={dev.get('max_z_acceleration')}g")

            # Store to database
            conn = sqlite3.connect(self.data_store.db_path)
            cursor = conn.cursor()

            for dev in devices:
                cursor.execute('''
                    INSERT INTO event_summary
                    (event_id, device_number, sample_count, max_z_acceleration,
                     avg_z_acceleration, calibration_offset)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    event_id,
                    dev.get('device_number'),
                    dev.get('sample_count'),
                    dev.get('max_z_acceleration'),
                    dev.get('avg_z_acceleration'),
                    dev.get('calibration_offset')
                ))

            conn.commit()
            conn.close()

            return web.json_response({'status': 'ok'})

        except Exception as e:
            self.total_errors += 1
            logger.error(f"Event summary error: {e}")
            return web.Response(status=500, text=str(e))

    async def handle_warning(self, request):
        """Handle system warnings"""
        self.total_requests += 1

        try:
            data = await request.json()

            warning_type = data.get('warning_type')
            severity = data.get('severity', 'medium')

            severity_icon = '⚠️' if severity == 'medium' else '🔴'
            logger.warning(f"{severity_icon} {data.get('message')}")
            print(f"\n{severity_icon} WARNING: {warning_type}")
            print(f"   Device: IMU-{data.get('device_number')} ({data.get('device_name')})")
            print(f"   Message: {data.get('message')}\n")

            # Store to database
            conn = sqlite3.connect(self.data_store.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO warnings
                (timestamp, warning_type, device_number, device_name, message, severity)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data.get('timestamp'),
                warning_type,
                data.get('device_number'),
                data.get('device_name'),
                data.get('message'),
                severity
            ))

            conn.commit()
            conn.close()

            return web.json_response({'status': 'ok'})

        except Exception as e:
            self.total_errors += 1
            logger.error(f"Warning error: {e}")
            return web.Response(status=500, text=str(e))
    
    async def handle_index(self, request):
        """Comprehensive status page with train events"""
        try:
            # Get recent train events
            conn = sqlite3.connect(self.data_store.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT event_id, trigger_time, end_time, duration, trigger_device,
                       z_magnitude, max_acceleration
                FROM train_events
                ORDER BY id DESC
                LIMIT 10
            ''')
            train_events = cursor.fetchall()

            # Get recent warnings
            cursor.execute('''
                SELECT timestamp, warning_type, device_number, device_name, message, severity
                FROM warnings
                ORDER BY id DESC
                LIMIT 10
            ''')
            warnings = cursor.fetchall()

            conn.close()

            # Build train events HTML
            train_events_html = ""
            for event in train_events:
                event_id, trigger_time, end_time, duration, trigger_dev, z_mag, max_acc = event
                status = "✅ Completed" if end_time else "🚂 In Progress"
                duration_str = f"{duration:.1f}s" if duration else "N/A"
                max_acc_str = f"{max_acc:.2f}g" if max_acc else "N/A"

                train_events_html += f"""
                <tr>
                    <td>{status}</td>
                    <td>{event_id}</td>
                    <td>IMU-{trigger_dev}</td>
                    <td>{z_mag:.2f}g</td>
                    <td>{duration_str}</td>
                    <td>{max_acc_str}</td>
                    <td>{trigger_time[:19] if trigger_time else 'N/A'}</td>
                </tr>
                """

            # Build warnings HTML
            warnings_html = ""
            for warn in warnings:
                timestamp, warn_type, dev_num, dev_name, message, severity = warn
                severity_icon = "🔴" if severity == "high" else "⚠️"
                warnings_html += f"""
                <tr>
                    <td>{severity_icon} {severity.upper()}</td>
                    <td>{warn_type}</td>
                    <td>IMU-{dev_num}</td>
                    <td>{message}</td>
                    <td>{timestamp[:19] if timestamp else 'N/A'}</td>
                </tr>
                """

            html = f"""
            <html>
            <head>
                <title>Train Detection System - Monitoring Dashboard</title>
                <meta http-equiv="refresh" content="30">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 20px;
                        background-color: #f5f5f5;
                    }}
                    h1 {{
                        color: #333;
                        border-bottom: 3px solid #4CAF50;
                        padding-bottom: 10px;
                    }}
                    h2 {{
                        color: #555;
                        margin-top: 30px;
                        border-bottom: 2px solid #2196F3;
                        padding-bottom: 5px;
                    }}
                    .status-box {{
                        background-color: white;
                        padding: 15px;
                        border-radius: 5px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        margin-bottom: 20px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        background-color: white;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    th {{
                        background-color: #4CAF50;
                        color: white;
                        padding: 12px;
                        text-align: left;
                    }}
                    td {{
                        padding: 10px;
                        border-bottom: 1px solid #ddd;
                    }}
                    tr:hover {{
                        background-color: #f5f5f5;
                    }}
                    .warning-table th {{
                        background-color: #ff9800;
                    }}
                    .stats {{
                        display: flex;
                        gap: 20px;
                        margin-bottom: 20px;
                    }}
                    .stat-card {{
                        flex: 1;
                        background-color: white;
                        padding: 15px;
                        border-radius: 5px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    .stat-value {{
                        font-size: 24px;
                        font-weight: bold;
                        color: #4CAF50;
                    }}
                    .stat-label {{
                        color: #777;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <h1>🚂 Train Detection System - Monitoring Dashboard</h1>

                <div class="status-box">
                    <p><strong>Server Status:</strong> 🟢 Running</p>
                    <p><strong>Last Update:</strong> {self.last_update_time or 'Never'}</p>
                    <p><strong>Auto-refresh:</strong> Every 30 seconds</p>
                </div>

                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">{len(train_events)}</div>
                        <div class="stat-label">Recent Train Events</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self.total_requests}</div>
                        <div class="stat-label">Total Requests</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self.total_errors}</div>
                        <div class="stat-label">Total Errors</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{len(warnings)}</div>
                        <div class="stat-label">Recent Warnings</div>
                    </div>
                </div>

                <h2>🚂 Recent Train Events</h2>
                <table>
                    <tr>
                        <th>Status</th>
                        <th>Event ID</th>
                        <th>Trigger Device</th>
                        <th>Z-Magnitude</th>
                        <th>Duration</th>
                        <th>Max Acceleration</th>
                        <th>Time</th>
                    </tr>
                    {train_events_html if train_events_html else '<tr><td colspan="7">No train events yet</td></tr>'}
                </table>

                <h2>⚠️ Recent Warnings</h2>
                <table class="warning-table">
                    <tr>
                        <th>Severity</th>
                        <th>Type</th>
                        <th>Device</th>
                        <th>Message</th>
                        <th>Time</th>
                    </tr>
                    {warnings_html if warnings_html else '<tr><td colspan="5">No warnings</td></tr>'}
                </table>

                <h2>API Endpoints</h2>
                <div class="status-box">
                    <h3>Health Monitoring</h3>
                    <ul>
                        <li>POST /api/imu/status - Receive IMU health data</li>
                        <li>GET /api/system/recent?limit=10 - Recent system status</li>
                        <li>GET /api/alerts/active - Active alerts</li>
                        <li>GET /api/stats - Server statistics</li>
                    </ul>
                    <h3>Train Events</h3>
                    <ul>
                        <li>POST /api/events/start - Train detection start</li>
                        <li>POST /api/events/end - Train passed (end)</li>
                        <li>POST /api/events/summary - Event summary data</li>
                        <li>POST /api/warnings - System warnings</li>
                    </ul>
                </div>
            </body>
            </html>
            """
            return web.Response(text=html, content_type='text/html')

        except Exception as e:
            logger.error(f"Index page error: {e}")
            return web.Response(text=f"Error: {e}", status=500)
    
    def _print_status_summary(self, data, alerts):
        """Print status summary to console"""
        print("\n" + "=" * 60)
        print("RECEIVED STATUS UPDATE")
        print("=" * 60)
        
        system = data.get('system', {})
        print(f"Events: {system.get('total_events', 0)} | "
              f"Reconnects: {system.get('total_reconnects', 0)} | "
              f"OS Cleanups: {system.get('total_os_cleanups', 0)}")
        
        imus = data.get('imus', [])
        print(f"\nIMUs: {len(imus)}")
        
        for imu in imus:
            status = "READY" if imu.get('is_ready', False) else "OFFLINE"
            device_health = imu.get('device_health', {})
            window = device_health.get('sliding_window', {})
            window_stats = window.get('stats', {})
            
            health_info = ""
            if not window.get('healthy', True):
                pct = window_stats.get('unhealthy_percentage', 0)
                health_info = f" [Window: {pct:.0f}% unhealthy]"
            
            failures = device_health.get('consecutive_failures', 0)
            if failures > 0:
                health_info += f" [Failures: {failures}]"
            
            print(f"  IMU-{imu.get('number', 0)}: {status}{health_info}")
        
        if alerts:
            print(f"\nAlerts: {len(alerts)}")
            for alert in alerts:
                severity_symbol = "!" if alert['severity'] == 'high' else "*"
                print(f"  {severity_symbol} {alert['message']}")
        
        print("=" * 60 + "\n")
    
    def run(self):
        """Start the server"""
        print("=" * 60)
        print("IMU Health Monitoring Server")
        print("=" * 60)
        print(f"Listening on http://{self.host}:{self.port}")
        print(f"Database: {self.data_store.db_path}")
        print("=" * 60)
        print("\nWaiting for health data...\n")
        
        web.run_app(self.app, host=self.host, port=self.port, print=lambda x: None)


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='IMU Health Monitoring Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--db', default='health_data.db', help='Database file path')
    
    args = parser.parse_args()
    
    # Create server
    server = HealthMonitoringServer(host=args.host, port=args.port)
    server.data_store.db_path = args.db
    server.data_store._init_database()
    
    # Run
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n\nServer stopped")


if __name__ == "__main__":
    main()
