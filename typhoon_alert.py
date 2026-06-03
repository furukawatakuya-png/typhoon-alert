"""
台風6号 被害速報 自動通知スクリプト
気象庁API（r8）→ Slack #saas_旅客dx スレッドへ自動投稿
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

# 🔴緊急扱いの警報
RED_WARNINGS = ["暴風警報", "暴風雪警報", "大雨警報", "波浪警報", "高潮警報", "洪水警報"]
# 🟡注意報扱い
YELLOW_WARNINGS = ["大雨注意報", "洪水注意報", "強風注意報", "高潮注意報", "波浪注意報"]

TARGET_AREAS = {
    "010100": "北海道（宗谷）", "020000": "青森県", "030000": "岩手県",
    "040000": "宮城県", "050000": "秋田県", "060000": "山形県", "070000": "福島県",
    "080000": "茨城県", "090000": "栃木県", "100000": "群馬県", "110000": "埼玉県",
    "120000": "千葉県", "130000": "東京都", "140000": "神奈川県", "150000": "新潟県",
    "160000": "富山県", "170000": "石川県", "180000": "福井県", "190000": "山梨県",
    "200000": "長野県", "210000": "岐阜県", "220000": "静岡県", "230000": "愛知県",
    "240000": "三重県", "250000": "滋賀県", "260000": "京都府", "270000": "大阪府",
    "280000": "兵庫県", "290000": "奈良県", "300000": "和歌山県", "310000": "鳥取県",
    "320000": "島根県", "330000": "岡山県", "340000": "広島県", "350000": "山口県",
    "360000": "徳島県", "370000": "香川県", "380000": "愛媛県", "390000": "高知県",
    "400000": "福岡県", "410000": "佐賀県", "420000": "長崎県", "430000": "熊本県",
    "440000": "大分県", "450000": "宮崎県", "460100": "鹿児島県", "471000": "沖縄本島",
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


def post_to_thread(thread_ts, text):
    slack_api("chat.postMessage", {
        "channel": SLACK_CHANNEL_ID,
        "thread_ts": thread_ts,
        "text": text,
    })


def fetch_warnings():
    red_alerts = {}   # 🔴 警報
    yellow_areas = {} # 🟡 注意報

    for code, name in TARGET_AREAS.items():
        try:
            url = f"https://www.jma.go.jp/bosai/warning/data/r8/{code}.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data_list = json.loads(res.read().decode("utf-8"))

            if not isinstance(data_list, list):
                data_list = [data_list]

            for data in data_list:
                warning = data.get("warning", {})
                for item in warning.get("class10Items", []):
                    for kind in item.get("kinds", []):
                        status = kind.get("status", "")
                        wcode = str(kind.get("code", ""))
                        wname = WARNING_CODES.get(wcode, "")
                        if status in ("発表", "継続"):
                            if wname in RED_WARNINGS:
                                if name not in red_alerts:
                                    red_alerts[name] = set()
                                red_alerts[name].add(wname)
                            elif wname in YELLOW_WARNINGS:
                                if name not in yellow_areas:
                                    yellow_areas[name] = set()
                                yellow_areas[name].add(wname)
        except Exception as e:
            print(f"{name} エラー: {e}")

    return red_alerts, yellow_areas


def build_message(red_alerts, yellow_areas):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"*【台風6号 警報速報】*", f"確認時刻：{now}", ""]

    if red_alerts:
        lines.append("*🔴 警報（発令中）*")
        for area, warnings in sorted(red_alerts.items()):
            lines.append(f"  • *{area}*：{' / '.join(sorted(warnings))}")
        lines.append("")

    if yellow_areas:
        areas_str = "・".join(sorted(yellow_areas.keys()))
        lines.append(f"*🟡 注意報：* {areas_str}")
        lines.append("")

    if not red_alerts and not yellow_areas:
        lines.append("現在、台風関連の警報・注意報はありません。")

    lines.append("情報ソース：気象庁")
    return "\n".join(lines)


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
    thread_ts = state["thread_ts"]

    print("気象庁から情報を取得中...")
    red_alerts, yellow_areas = fetch_warnings()
    print(f"🔴 警報: {len(red_alerts)}エリア / 🟡 注意報: {len(yellow_areas)}エリア")

    # 🔴警報エリアに変化があれば通知
    red_key = f"red_{'_'.join(sorted(red_alerts.keys()))}_{datetime.now().strftime('%Y%m%d%H')}"
    if red_key not in state["sent_ids"] and (red_alerts or yellow_areas):
        text = build_message(red_alerts, yellow_areas)
        post_to_thread(thread_ts, text)
        state["sent_ids"].append(red_key)
        print("投稿完了")
    else:
        print("変化なし。投稿スキップ。")

    save_state(state)


if __name__ == "__main__":
    main()
