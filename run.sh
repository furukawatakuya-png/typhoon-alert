#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "エラー: SLACK_WEBHOOK_URL が設定されていません"
    echo "実行方法: SLACK_WEBHOOK_URL=https://hooks.slack.com/... bash run.sh"
    exit 1
fi

echo "台風6号 監視開始（15分ごとに自動チェック）"
echo "停止するには Ctrl+C を押してください"
echo ""

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M')] チェック中..."
    python3 "$SCRIPT_DIR/typhoon_alert.py"
    echo "次回チェックまで15分待機..."
    sleep 900
done
