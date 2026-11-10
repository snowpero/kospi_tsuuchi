"""Telegram-controlled KOSPI alerts, run periodically by GitHub Actions."""
import json
import logging
import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path(__file__).with_name("state.json")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
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
    telegram("sendMessage", {"chat_id": CHAT_ID, "text": message})


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
                "/on — 알림 켜기\n/off — 알림 끄기")
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


def main():
    state = load_state()
    try:
        process_updates(state)
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
