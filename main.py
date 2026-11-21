"""Telegram alerts for KOSPI and CNN Fear & Greed, run periodically by GitHub Actions."""
import json
import logging
import os
import re
import sys
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path(__file__).with_name("state.json")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
MACROMICRO_CHARTS_URL = "https://en.macromicro.me/trader-insights"
CNN_READING_PATTERN = re.compile(
    r'<h6 class="stat-name">\s*US - CNN Fear and Greed Index\s*</h6>\s*'
    r'<div class="date-label">\s*<time>\s*(\d{4}-\d{2}-\d{2})\s*</time>\s*</div>\s*'
    r'<div class="stat-val">\s*<span class="val">\s*(\d+(?:\.\d+)?)\s*</span>'
)
CNN_THRESHOLD = 10
DEFAULT = {"upper": 4000.0, "lower": 3800.0, "enabled": True, "update_offset": 0}


def load_state():
    if not STATE_PATH.exists():
        return DEFAULT.copy()
    state = DEFAULT.copy()
    state.update(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    return state


def save_state(state):
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_PATH)


def telegram(method, payload):
    for attempt in range(3):
        try:
            response = requests.post(
                f"{API}/{method}",
                json=payload,
                timeout=10
            )
            break
    
        except requests.exceptions.RequestException as e:
            logging.warning(
                "Telegram API 요청 실패 (%d/3): %s",
                attempt + 1,
                e
            )
    
            if attempt == 2:
                return None
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description', 'unknown')}")
    return data["result"]


def send(message):
    return telegram("sendMessage", {"chat_id": CHAT_ID, "text": message})


def fetch_kospi(require_fresh=False):
    """Return (value, timestamp), or (None, None) for unavailable/invalid/stale data."""
    try:
        history = yf.Ticker("^KS11").history(
            period="5d", interval="5m", auto_adjust=False
        )
        if history.empty:
            logging.warning("코스피 시세 데이터가 없습니다. 알림을 생략합니다.")
            return None, None

        last = history.iloc[-1]
        value = float(last["Close"])
        stamp = history.index[-1].to_pydatetime().astimezone(KST)

        if not (0 < value < 100000):
            logging.warning("비정상적인 코스피 지수 값: %s", value)
            return None, None

        if require_fresh:
            age = (datetime.now(KST) - stamp).total_seconds()
            if not (-120 <= age <= 20 * 60):
                logging.warning(
                    "시세가 오래되었거나 시각이 유효하지 않아 알림을 생략합니다: %s",
                    stamp.strftime("%Y-%m-%d %H:%M"),
                )
                return None, None

        return value, stamp
    except Exception as exc:
        logging.warning("코스피 시세 조회 실패, 이번 조회를 생략합니다: %s", exc)
        return None, None


def market_open(now):
    return now.weekday() < 5 and time(9, 0) <= now.time() <= time(15, 30)


def handle_command(text, state):
    parts = text.strip().split()
    if not parts:
        return None
    command = parts[0].split("@")[0].lower()
    if command in ("/start", "/help"):
        return ("📋 코스피 알림 명령어\n"
                "/upper 4200 — 상한 변경\n/lower 3700 — 하한 변경\n"
                "/status — 설정 확인\n/price — 최근 지수\n"
                "/on — 알림 켜기\n/off — 알림 끄기\n"
                "/cnntest — CNN 공포·탐욕 지수 테스트 알림")
    if command in ("/upper", "/lower"):
        if len(parts) != 2:
            return f"사용법: {command} 4200"
        try:
            value = float(parts[1].replace(",", ""))
        except ValueError:
            return "숫자를 입력해 주세요. 예: /upper 4200"
        if not (0 < value < 100000):
            return "지수는 0보다 크고 100000보다 작아야 합니다."
        key = "upper" if command == "/upper" else "lower"
        if key == "upper" and value <= state["lower"]:
            return f"상한은 현재 하한 {state['lower']:,.0f}보다 커야 합니다."
        if key == "lower" and value >= state["upper"]:
            return f"하한은 현재 상한 {state['upper']:,.0f}보다 작아야 합니다."
        before = state[key]
        state[key] = value
        return f"✅ {'상한' if key == 'upper' else '하한'} 변경 완료\n기존: {before:,.0f}\n변경: {value:,.0f}"
    if command == "/status":
        return (f"📊 KOSPI 알림 설정\n상한: {state['upper']:,.0f} 이상\n"
                f"하한: {state['lower']:,.0f} 이하\n"
                f"알림: {'활성화' if state['enabled'] else '중지'}\n확인 주기: 약 5분")
    if command == "/on":
        state["enabled"] = True
        return "🔔 코스피 지수 알림을 켰습니다."
    if command == "/off":
        state["enabled"] = False
        return "🔕 코스피 지수 알림을 중지했습니다. 명령어는 계속 사용할 수 있습니다."
    if command == "/price":
        value, stamp = fetch_kospi(require_fresh=False)
        if value is None:
            return "⚠️ 현재 코스피 시세를 조회할 수 없습니다. 잠시 후 다시 시도해 주세요."
        return (f"📈 최근 코스피: {value:,.2f}\n"
                f"시세 시각: {stamp:%Y-%m-%d %H:%M} KST\n"
                "※ 장외에는 마지막 거래 시세이며 지연될 수 있습니다.")
    if command == "/cnntest":
        reading = fetch_fear_greed()
        if reading is None:
            return ("🧪 CNN 공포·탐욕 지수 테스트 알림\n"
                    "텔레그램 발송 확인 · CNN 지수 조회 실패")
        return format_fear_greed_alert(*reading, test=True)
    return None


def process_updates(state):
    updates = telegram("getUpdates", {"offset": state["update_offset"], "limit": 100, "timeout": 0})
    if updates is None:
        logging.warning(
            "Telegram 명령어 조회 실패. 이번 실행을 건너뜁니다."
        )
        return
    
    for update in updates:
        update_id = int(update["update_id"])
        message = update.get("message") or update.get("edited_message") or {}
        sender_chat = str(message.get("chat", {}).get("id", ""))
        content = message.get("text", "")
        if sender_chat == CHAT_ID and content.startswith("/"):
            response = handle_command(content, state)
            if response:
                send(response)
                logging.info("Processed Telegram command: %s", content.split()[0])
        # Never respond to unknown chats. Persist offset to prevent replay.
        state["update_offset"] = update_id + 1
        save_state(state)
    if len(updates) == 100:
        logging.warning("100 updates received; remaining messages will be processed next run")


def check_alert(state):
    now = datetime.now(KST)
    if not state["enabled"]:
        logging.info("Threshold alerts disabled")
        return
    if not market_open(now):
        logging.info("Outside regular KOSPI hours: %s", now.isoformat())
        return
    value, stamp = fetch_kospi(require_fresh=True)
    if value is None:
        logging.info("유효한 코스피 시세가 없어 이번 알림을 건너뜁니다.")
        return
    if value >= state["upper"]:
        condition = f"상한 {state['upper']:,.0f} 이상"
        icon = "📈"
    elif value <= state["lower"]:
        condition = f"하한 {state['lower']:,.0f} 이하"
        icon = "📉"
    else:
        logging.info("KOSPI %.2f: within threshold range", value)
        return
    send(f"{icon} 코스피 지수 알림\n현재 지수: {value:,.2f}\n"
         f"충족 조건: {condition}\n시세 시각: {stamp:%Y-%m-%d %H:%M} KST\n"
         "※ 시세는 지연될 수 있습니다.")
    logging.info("Threshold notification sent")


@lru_cache(maxsize=1)
def fetch_fear_greed():
    """Read the public Market Sentiment card once per workflow run."""
    try:
        response = requests.get(MACROMICRO_CHARTS_URL, timeout=10)
        response.raise_for_status()
        match = CNN_READING_PATTERN.search(response.text)
        if match is None:
            raise ValueError("CNN index date and score not found in MacroMicro Charts")
        reading_date = date.fromisoformat(match[1])
        score = float(match[2])
        if not 0 <= score <= 100:
            raise ValueError("CNN score is outside the valid range")
    except (requests.RequestException, ValueError) as exc:
        logging.warning("MacroMicro에서 CNN 공포·탐욕 지수 조회 실패: %s", exc)
        return None
    return score, reading_date


def format_fear_greed_alert(score, reading_date, *, test=False):
    title = "🧪 CNN 공포·탐욕 지수 테스트 알림" if test else "😨 CNN 공포·탐욕 지수 알림"
    return (f"{title}\n현재 지수: {int(score + 0.5)} (원래 점수: {score:g})\n"
            f"자동 알림 기준: {CNN_THRESHOLD} 이하\n"
            f"지수 기준일: {reading_date:%Y-%m-%d}\n"
            f"출처: MacroMicro Charts\n{MACROMICRO_CHARTS_URL}")


def check_fear_greed_alert(state):
    reading = fetch_fear_greed()
    if reading is None:
        return
    score, reading_date = reading
    # Older state records whether an alert was sent, without its score.
    legacy_alert_sent = state.pop("fear_greed_alert_sent", False)
    if score > CNN_THRESHOLD:
        state.pop("fear_greed_alert_score", None)
        return

    rounded_score = int(score + 0.5)
    if legacy_alert_sent:
        state.setdefault("fear_greed_alert_score", rounded_score)
    if state.get("fear_greed_alert_score") == rounded_score:
        return
    if send(format_fear_greed_alert(score, reading_date)) is not None:
        state["fear_greed_alert_score"] = rounded_score


def main():
    state = load_state()
    try:
        process_updates(state)
    finally:
        save_state(state)
    try:
        check_fear_greed_alert(state)
    finally:
        save_state(state)
    check_alert(state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        main()
    except Exception:
        logging.exception("KOSPI bot failed")
        sys.exit(1)
