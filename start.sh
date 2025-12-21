#!/bin/bash
# 快速启动脚本

echo "=========================================="
echo "🚂 Train Detection System"
echo "=========================================="

# 检查Python版本
python3 --version

# 检查依赖
echo ""
echo "📦 Checking dependencies..."
pip3 list | grep bleak

if [ $? -ne 0 ]; then
    echo "⚠️  bleak not installed, installing..."
    pip3 install -r requirements.txt
fi

echo ""
echo "Choose an option:"
echo "1) Run tests (recommended first time)"
echo "2) Start detection system"
echo "3) Start detection in background"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "🧪 Running tests..."
        python3 test_detector.py
        ;;
    2)
        echo ""
        echo "🎯 Starting detection system..."
        python3 train_detector.py
        ;;
    3)
        echo ""
        echo "🎯 Starting in background..."
        nohup python3 train_detector.py > detector.log 2>&1 &
        echo "✅ Started! Check logs with: tail -f detector.log"
        echo "Stop with: pkill -f train_detector.py"
        ;;
    *)
        echo "Invalid choice"
        ;;
esac
