#!/bin/bash

# Celeryワーカー起動スクリプト
echo "Starting Celery workers for Q/A generation..."

# ログディレクトリ作成
mkdir -p logs

# 既存のCeleryプロセスを終了（クリーンスタート用）
pkill -f "celery worker" 2>/dev/null

# 少し待つ
sleep 2

# 高優先度ワーカー（3プロセス）
echo "Starting high priority worker..."
celery -A celery_config worker \
    --loglevel=info \
    --concurrency=3 \
    --hostname=worker_high@%h \
    --queues=high_priority \
    --logfile=logs/worker_high.log &

# 通常優先度ワーカー（2プロセス）
echo "Starting normal priority worker..."
celery -A celery_config worker \
    --loglevel=info \
    --concurrency=2 \
    --hostname=worker_normal@%h \
    --queues=normal_priority \
    --logfile=logs/worker_normal.log &

# 低優先度ワーカー（1プロセス）
echo "Starting low priority worker..."
celery -A celery_config worker \
    --loglevel=info \
    --concurrency=1 \
    --hostname=worker_low@%h \
    --queues=low_priority \
    --logfile=logs/worker_low.log &

# Flower（モニタリング）起動
echo "Starting Flower monitoring..."
celery -A celery_config flower \
    --port=${FLOWER_PORT:-5555} \
    --basic_auth=${FLOWER_BASIC_AUTH:-admin:password} &

echo ""
echo "✅ Celery workers started successfully!"
echo ""
echo "📊 Monitor at: http://localhost:5555"
echo "   Username: admin"
echo "   Password: password"
echo ""
echo "📝 Logs are available in:"
echo "   - logs/worker_high.log"
echo "   - logs/worker_normal.log"
echo "   - logs/worker_low.log"
echo ""
echo "To stop all workers, run: pkill -f 'celery worker'"