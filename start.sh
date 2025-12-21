#!/bin/bash
# 快速启动脚本

echo "=========================================="
echo "🚂 Train Detection System - 启动脚本"
echo "=========================================="

echo ""
echo "选择启动模式:"
echo "1) 启动数据接收服务器 (upload_server.py)"
echo "2) 启动检测系统 (train_detector.py)"
echo "3) 同时启动两个（推荐）"
echo "4) 测试连接 (test_detector.py)"
echo ""
read -p "请选择 [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 启动数据接收服务器..."
        python3 upload_server.py
        ;;
    2)
        echo ""
        echo "🎯 启动检测系统..."
        python3 train_detector.py
        ;;
    3)
        echo ""
        echo "🚀 启动数据接收服务器 (后台)..."
        python3 upload_server.py > upload_server.log 2>&1 &
        SERVER_PID=$!
        echo "   服务器PID: $SERVER_PID"
        echo "   日志: tail -f upload_server.log"
        
        echo ""
        echo "⏳ 等待3秒让服务器启动..."
        sleep 3
        
        echo ""
        echo "🎯 启动检测系统..."
        python3 train_detector.py
        
        # 清理
        echo ""
        echo "⚠️  停止后台服务器..."
        kill $SERVER_PID 2>/dev/null
        ;;
    4)
        echo ""
        echo "🧪 运行测试..."
        python3 test_detector.py
        ;;
    *)
        echo "无效选择"
        ;;
esac
