"""
台風6号 被害速報 自動通知スクリプト
気象庁API → Slack #saas_旅客dx スレッドへ自動投稿
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = "C05RTKDQUNL"
STATE_FILE = Path(__file__).parent / "state.json"

WARNING_CODES = {
    "01": "暴風警報", "02": "暴風雪警報", "03": "大雨警報", "04": "大雪警報",
    "05": "波浪警報", "06": "高潮警報", "10": "大雨注意報", "11": "洪水注意報",
    "12": "強風注意報", "13": "風雪注意報", "14": "波浪注意報", "15": "高潮注意報",
    "16": "大雪注意報", "17": "雷注意報",
}

# 台風関連のみ（波浪・乾燥などは除外）
TYPHOON_RELATED = ["暴風警報", "暴風雪警報", "大雨警報", "洪水警報", "高潮警報",
                   "大雨注意報", "洪水注意報", "強風注意報", "高潮注意報", "土砂災害"]

LEVEL_MAP = {
    "red":    {"emoji": "🔴", "label": "緊急",  "keywords": ["暴風警報", "特別警報", "高潮警報", "土砂災害"]},
    "orange": {"emoji": "🟠", "label": "注意",  "keywords": ["大雨警報", "洪水警報", "強風注意報"]},
    "yellow": {"emoji": "🟡", "label": "軽微",  "keywords": ["大雨注意報", "洪水注意報", "高潮注意報"]},
    "green":  {"emoji": "🟢", "label": "解除",  "keywords": ["解除"]},
}

TARGET_AREAS = {
    "460100": "鹿児島県", "450000": "宮崎県", "440000": "大分県",
    "430000": "熊本県", "420000": "長崎県", "410000": "佐賀県",
    "400000": "福岡県", "390000": "高知県", "380000": "愛媛県",
    "370000": "香川県", "360000": "徳島県", "350000": "山口県",
    "340000": "広島県", "330000": "岡山県", "280000": "兵庫県",
    "270000": "大阪府", "260000": "京都府", "240000": "三重県",
    "220000": "静岡県", "230000": "愛知県", "130000": "東京都",
    "140000": "神奈川県", "471000": "沖縄本島",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"thread_ts": None, "sent_ids": [], "parent_posted": False}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def slack_api(method, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def post_parent_message():
    today = datetime.now().strftime("%Y年%m月%d日")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m月%d日")
    res = slack_api("chat.postMessage", {
        "channel": SLACK_CHANNEL_ID,
        "text": (
            "━━━━━━━━━━━━━━\n"
            "【台風6号 被害速報】\n"
            f"対象期間：{today}〜{tomorrow} 23:59\n"
            "このスレッドに最新情報を自動投稿します\n"
            "━━━━━━━━━━━━━━"
        )
    })
    return res.get("ts")


def post_to_thread(thread_ts, text):
    slack_api("chat.postMessage", {
        "channel": SLACK_CHANNEL_ID,
        "thread_ts": thread_ts,
        "text": text,
    })


def classify(content):
    for level_key in ["red", "orange", "yellow", "green"]:
        for kw in LEVEL_MAP[level_key]["keywords"]:
            if kw in content:
                return level_key
    return "yellow"


def fetch_warnings():
    alerts = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    for area_code, area_name in TARGET_AREAS.items():
        try:
            url = f"https://www.jma.go.jp/bosai/warning/data/warning/{area_code}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))
            for at in data.get("areaTypes", []):
                for area in at.get("areas", []):
                    for w in area.get("warnings", []):
                        status = w.get("status", "")
                        wcode = str(w.get("code", ""))
                        wname = WARNING_CODES.get(wcode, "")
                        if status in ("発表", "継続") and wname in TYPHOON_RELATED:
                            alert_id = f"{area_code}_{wcode}_{datetime.now().strftime('%Y%m%d%H')}"
                            alerts.append({
                                "id": alert_id,
                                "time": now_str,
                                "area": area_name,
                                "content": wname,
                                "source": "気象庁",
                            })
        except Exception as e:
            print(f"{area_name} エラー: {e}")
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
        f"• 情報ソース：{alert['source']}"
    )


def is_within_period():
    end = (datetime.now() + timedelta(days=1)).replace(hour=23, minute=59)
    return datetime.now() <= end


def main():
    if not SLACK_BOT_TOKEN:
        print("エラー: SLACK_BOT_TOKEN が設定されていません")
        return

    if not is_within_period():
        print("通知期間終了。終了します。")
        return

    state = load_state()

    if not state["parent_posted"]:
        ts = post_parent_message()
        state["thread_ts"] = ts
        state["parent_posted"] = True
        save_state(state)
        time.sleep(2)

    thread_ts = state["thread_ts"]
    print("気象庁から情報を取得中...")
    alerts = fetch_warnings()
    print(f"{len(alerts)} 件の台風関連情報を取得")

    new_count = 0
    for alert in alerts:
        if alert["id"] in state["sent_ids"]:
            continue
        text = format_alert(alert)
        post_to_thread(thread_ts, text)
        state["sent_ids"].append(alert["id"])
        new_count += 1
        print(f"投稿: {alert['area']} - {alert['content']}")
        time.sleep(1)

    if new_count == 0:
        print("新しい情報はありませんでした")

    save_state(state)
    print(f"完了: {new_count} 件投稿")


if __name__ == "__main__":
    main()
