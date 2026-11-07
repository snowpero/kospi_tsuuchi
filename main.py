"""KOSPI threshold notifications using Yahoo Finance and Telegram."""
import logging
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")
UPPER = float(os.getenv("KOSPI_UPPER", "4000"))
LOWER = float(os.getenv("KOSPI_LOWER", "3800"))


def in_market_hours(now: datetime) -> bool:
    # Weekday and regular trading hours; exchange holidays are not checked.
    return now.weekday() < 5 and time(9, 0) <= now.time() <= time(15, 30)


def fetch_kospi() -> tuple[float, datetime]:
    # Yahoo Finance index symbol. Intraday quotes may be delayed or unavailable.
    history = yf.Ticker("^KS11").history(period="1d", interval="5m", auto_adjust=False)
    if history.empty:
        raise RuntimeError("KOSPI intraday data unavailable")
    last = history.iloc[-1]
    value = float(last["Close"])
    timestamp = history.index[-1].to_pydatetime().astimezone(KST)
    if not (0 < value < 100000):
        raise RuntimeError(f"Unexpected KOSPI value: {value}")
    # Avoid sending notifications for stale quotes (e.g. on exchange holidays).
    age_seconds = (datetime.now(KST) - timestamp).total_seconds()
    if age_seconds < -120 or age_seconds > 20 * 60:
        raise RuntimeError(f"Stale KOSPI quote ({timestamp.isoformat()})")
    return value, timestamp


def notify(message: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=15,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram API returned an error")


def main() -> None:
    now = datetime.now(KST)
    if not in_market_hours(now):
        logging.info("Outside regular KOSPI hours: %s", now.isoformat())
        return
    if LOWER >= UPPER:
        raise ValueError("KOSPI_LOWER must be smaller than KOSPI_UPPER")
    value, quote_time = fetch_kospi()
    if value >= UPPER:
        condition = f"상한 {UPPER:,.0f} 이상"
        icon = "📈"
    elif value <= LOWER:
        condition = f"하한 {LOWER:,.0f} 이하"
        icon = "📉"
    else:
        logging.info("No alert: KOSPI %.2f", value)
        return
    message = (
        f"{icon} 코스피 지수 알림\n"
        f"현재 지수: {value:,.2f}\n"
        f"충족 조건: {condition}\n"
        f"시세 시각: {quote_time:%Y-%m-%d %H:%M} KST\n"
        f"확인 시각: {now:%Y-%m-%d %H:%M} KST\n"
        "※ 시세는 지연될 수 있습니다."
    )
    notify(message)
    logging.info("Notification sent for KOSPI %.2f", value)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        main()
    except Exception:
        logging.exception("KOSPI monitoring failed")
        sys.exit(1)
