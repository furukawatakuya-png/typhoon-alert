"""
台風6号 被害速報 自動通知スクリプト
気象庁API → Slack #saas_旅客dx へ自動投稿
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
STATE_FILE = Path(__file__).parent / "state.json"

# 重要度マッピング
LEVEL_MAP = {
    "red": {
        "emoji": "🔴",
        "label": "緊急",
        "advice": "架電停止推奨",
        "detail": "顧客エリアに重大被害。架電は翌日以降に延期してください。",
        "keywords": ["特別警報", "氾濫発生", "緊急安全確保", "避難指示", "土砂災害警戒情報"],
    },
    "orange": {
        "emoji": "🟠",
        "label": "注意",
        "advice": "状況確認を優先",
        "detail": "架電前に顧客エリアの状況確認を。冒頭で配慮の一言を。",
        "keywords": ["大雨警報", "洪水警報", "高潮警報", "暴風警報", "避難勧告", "通行止め", "運休", "停電", "断水"],
    },
    "yellow": {
        "emoji": "🟡",
        "label": "軽微",
        "advice": "通常架電可",
        "detail": "軽微な影響。冒頭で天候への一言添えて架電可能です。",
        "keywords": ["大雨注意報", "洪水注意報", "強風注意報", "波浪注意報"],
    },
    "green": {
        "emoji": "🟢",
        "label": "解除",
        "advice": "通常運用へ復帰",
        "detail": "警戒情報が解除。通常架電を再開してください。",
        "keywords": ["解除", "復旧"],
    },
}

# 監視対象エリア（気象庁エリアコード）
TARGET_AREAS = {
    "010100": "宗谷地方", "010200": "上川・留萌地方", "010300": "網走・北見・紋別地方",
    "010400": "十勝地方", "010500": "釧路・根室地方", "010600": "胆振・日高地方",
    "010700": "石狩・空知・後志地方", "010800": "渡島・檜山地方",
    "020000": "青森県", "030000": "岩手県", "040000": "宮城県",
    "050000": "秋田県", "060000": "山形県", "070000": "福島県",
    "080000": "茨城県", "090000": "栃木県", "100000": "群馬県",
    "110000": "埼玉県", "120000": "千葉県", "130000": "東京都",
    "140000": "神奈川県", "150000": "新潟県", "160000": "富山県",
    "170000": "石川県", "180000": "福井県", "190000": "山梨県",
    "200000": "長野県", "210000": "岐阜県", "220000": "静岡県",
    "230000": "愛知県", "240000": "三重県", "250000": "滋賀県",
    "260000": "京都府", "270000": "大阪府", "280000": "兵庫県",
    "290000": "奈良県", "300000": "和歌山県", "310000": "鳥取県",
    "320000": "島根県", "330000": "岡山県", "340000": "広島県",
    "350000": "山口県", "360000": "徳島県", "370000": "香川県",
    "380000": "愛媛県", "390000": "高知県", "400000": "福岡県",
    "410000": "佐賀県", "420000": "長崎県", "430000": "熊本県",
    "440000": "大分県", "450000": "宮崎県", "460100": "鹿児島県",
    "471000": "沖縄本島地方",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"thread_ts": None, "sent_ids": [], "parent_posted": False}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def classify(text):
    for level_key in ["red", "orange", "yellow", "green"]:
        for kw in LEVEL_MAP[level_key]["keywords"]:
            if kw in text:
                return level_key
    return "yellow"


def post_slack(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.read().decode()


def post_parent_message():
    today = datetime.now().strftime("%Y年%m月%d日")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m月%d日")
    payload = {
        "text": (
            "━━━━━━━━━━━━━━\n"
            "【台風6号 被害速報】\n"
            f"対象期間：{today}〜{tomorrow} 23:59\n"
            "このスレッドに最新情報を自動投稿します\n"
            "━━━━━━━━━━━━━━"
        )
    }
    post_slack(payload)
    print("親メッセージを投稿しました")


def fetch_jma_warnings():
    """気象庁から警報・注意報情報を取得"""
    alerts = []
    url = "https://www.jma.go.jp/bosai/warning/data/warning/010100.json"  # テスト用：宗谷地方

    # 全エリア巡回（台風影響が大きい南日本を優先）
    priority_areas = ["460100", "450000", "440000", "430000", "420000", "410000", "400000",
                      "390000", "380000", "370000", "360000", "350000", "340000", "470000"]

    for area_code in priority_areas:
        try:
            url = f"https://www.jma.go.jp/bosai/warning/data/warning/{area_code}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))

            area_name = TARGET_AREAS.get(area_code, area_code)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            # 警報情報を抽出
            for item in data.get("areaTypes", []):
                for area in item.get("areas", []):
                    for warning in area.get("warnings", []):
                        status = warning.get("status", "")
                        wtype = warning.get("type", "")
                        if status in ("発表", "継続", "解除") and wtype:
                            content = f"{wtype} {status}"
                            alert_id = f"{area_code}_{wtype}_{status}_{datetime.now().strftime('%Y%m%d%H')}"
                            alerts.append({
                                "id": alert_id,
                                "time": now_str,
                                "area": f"{area_name}（{area.get('name', '')}）",
                                "content": content,
                                "source": "気象庁",
                            })
        except Exception as e:
            print(f"エリア {area_code} 取得エラー: {e}")
            continue

    return alerts


def format_alert(alert):
    level_key = classify(alert["content"])
    lv = LEVEL_MAP[level_key]
    return (
        f"{lv['emoji']} *{lv['label']}*\n\n"
        f"*【台風6号速報】*\n"
        f"• 発生時刻：{alert['time']}\n"
        f"• エリア：{alert['area']}\n"
        f"• 内容：{alert['content']}\n"
        f"• 影響レベル：{lv['emoji']} {lv['label']}\n"
        f"• 情報ソース：{alert['source']}\n\n"
        f"*【IS向けコメント】*\n"
        f"→ *{lv['advice']}*\n"
        f"_{lv['detail']}_"
    )


def is_within_period():
    end = (datetime.now() + timedelta(days=1)).replace(hour=23, minute=59, second=0)
    return datetime.now() <= end


def main():
    if not WEBHOOK_URL:
        print("エラー: SLACK_WEBHOOK_URL が設定されていません")
        return

    if not is_within_period():
        print("通知期間終了。終了します。")
        return

    state = load_state()

    # 初回のみ親メッセージ投稿
    if not state["parent_posted"]:
        post_parent_message()
        state["parent_posted"] = True
        save_state(state)
        time.sleep(2)

    # 気象庁から情報取得
    print("気象庁から情報を取得中...")
    alerts = fetch_jma_warnings()
    print(f"{len(alerts)} 件の情報を取得")

    # 未送信のみ通知
    new_count = 0
    for alert in alerts:
        if alert["id"] in state["sent_ids"]:
            continue
        text = format_alert(alert)
        post_slack({"text": text})
        state["sent_ids"].append(alert["id"])
        new_count += 1
        print(f"投稿: {alert['area']} - {alert['content']}")
        time.sleep(1)  # レート制限対策

    if new_count == 0:
        print("新しい情報はありませんでした")

    save_state(state)
    print(f"完了: {new_count} 件投稿")


if __name__ == "__main__":
    main()
