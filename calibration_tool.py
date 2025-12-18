#!/usr/bin/env python3
# coding:UTF-8
"""
阈值标定工具
用于采集背景噪音和火车通过时的数据，确定合适的检测阈值
"""

import json
import asyncio
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import deque
from witmotion_device_model_clean import DeviceModel

class CalibrationTool:
    def __init__(self, config_file, duration=60):
        self.config_file = config_file
        self.duration = duration  # 采集时长(秒)
        self.devices = {}
        self.data_buffers = {}
        self.start_time = None
        
        # 创建输出目录
        self.output_dir = Path("calibration_data")
        self.output_dir.mkdir(exist_ok=True)
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s'
        )
    
    def data_callback(self, device):
        """数据回调"""
        device_name = device.deviceName
        
        acc_x = device.get("AccX")
        acc_y = device.get("AccY")
        acc_z = device.get("AccZ")
        
        if acc_x is None:
            return
        
        # 计算合成加速度
        magnitude = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        # 保存数据
        if device_name not in self.data_buffers:
            self.data_buffers[device_name] = {
                'acc_x': [],
                'acc_y': [],
                'acc_z': [],
                'magnitude': []
            }
        
        self.data_buffers[device_name]['acc_x'].append(acc_x)
        self.data_buffers[device_name]['acc_y'].append(acc_y)
        self.data_buffers[device_name]['acc_z'].append(acc_z)
        self.data_buffers[device_name]['magnitude'].append(magnitude)
    
    async def start_device(self, device_config):
        """启动设备"""
        device_name = device_config['name']
        mac = device_config['mac']
        
        try:
            logging.info(f"连接设备: {device_name}")
            device = DeviceModel(device_name, mac, self.data_callback)
            self.devices[device_name] = device
            await device.openDevice()
        except Exception as e:
            logging.error(f"设备 {device_name} 启动失败: {e}")
    
    def analyze_and_save(self):
        """分析数据并保存结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results = {}
        
        print("\n" + "="*60)
        print("标定结果")
        print("="*60)
        
        for device_name, data in self.data_buffers.items():
            mag_array = np.array(data['magnitude'])
            
            # 统计分析
            stats = {
                'mean': float(np.mean(mag_array)),
                'std': float(np.std(mag_array)),
                'min': float(np.min(mag_array)),
                'max': float(np.max(mag_array)),
                'median': float(np.median(mag_array)),
                'p95': float(np.percentile(mag_array, 95)),
                'p99': float(np.percentile(mag_array, 99)),
                'sample_count': len(mag_array)
            }
            
            # 建议阈值 = 均值 + 3倍标准差
            suggested_threshold = stats['mean'] + 3 * stats['std']
            stats['suggested_threshold'] = float(suggested_threshold)
            
            results[device_name] = stats
            
            # 打印结果
            print(f"\n设备: {device_name}")
            print(f"  样本数: {stats['sample_count']}")
            print(f"  均值: {stats['mean']:.3f}g")
            print(f"  标准差: {stats['std']:.3f}g")
            print(f"  最小值: {stats['min']:.3f}g")
            print(f"  最大值: {stats['max']:.3f}g")
            print(f"  95分位: {stats['p95']:.3f}g")
            print(f"  99分位: {stats['p99']:.3f}g")
            print(f"  建议阈值: {suggested_threshold:.3f}g")
        
        # 保存结果
        result_file = self.output_dir / f"calibration_{timestamp}.json"
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n结果已保存到: {result_file}")
        print("="*60)
        
        return results
    
    async def run(self):
        """运行标定"""
        # 加载配置
        with open(self.config_file, 'r') as f:
            config = json.load(f)
        
        enabled_devices = [d for d in config['devices'] if d['enabled']]
        
        if not enabled_devices:
            logging.error("没有启用的设备")
            return
        
        print(f"\n开始采集数据，持续 {self.duration} 秒...")
        print("请保持环境安静（采集背景噪音）")
        print("或者等待火车通过（采集信号特征）\n")
        
        # 启动所有设备
        tasks = [self.start_device(config) for config in enabled_devices]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 等待数据采集
        self.start_time = asyncio.get_event_loop().time()
        
        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - self.start_time
                remaining = self.duration - elapsed
                
                if remaining <= 0:
                    break
                
                # 显示进度
                print(f"\r采集中... 剩余时间: {remaining:.1f}秒", end='', flush=True)
                await asyncio.sleep(1)
        
        except KeyboardInterrupt:
            print("\n\n采集已手动停止")
        
        finally:
            # 关闭设备
            for device in self.devices.values():
                device.closeDevice()
            
            # 分析结果
            if self.data_buffers:
                self.analyze_and_save()
            else:
                print("\n没有采集到数据")


def main():
    import sys
    
    config_file = sys.argv[1] if len(sys.argv) > 1 else "witmotion_config.json"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    tool = CalibrationTool(config_file, duration)
    asyncio.run(tool.run())


if __name__ == "__main__":
    main()
