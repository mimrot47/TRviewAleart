"""
TradingView Breakout Alert Engine -> Telegram
------------------------------------------------
- Pulls live/closed OHLC data from TradingView (via tvkit)
- Computes previous completed 1-hour candle HIGH & LOW
- If current price > prev 1H HIGH  -> BREAKOUT alert
- If current price < prev 1H LOW   -> BREAKDOWN alert
- Sends alert to YOUR Telegram chat (bot API)
"""

import asyncio
import os
import time
import requests
from datetime import datetime, timezone

from tvkit import OHLCV


# ============================================================
# CONFIGURATION
# ============================================================
SYMBOL       = "BINANCE:BTCUSDT"     # TradingView symbol
INTERVAL     = "1H"                  # 1-hour candles
BARS_TO_FETCH = 3                    # fetch a few for safety

# Loop settings
POLL_SECONDS   = 30                  # check every 30 seconds
COOLDOWN_SECS  = 3600                # don't re-alert same direction for 1h

# Telegram credentials
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8343689252:AAEOpn4ZmeMgtKqKxM2k1nsxidv0eH_obQc")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "1064846152")


# ============================================================
# TELEGRAM SENDER
# ============================================================
def send_telegram_alert(message: str) -> bool:
    """Send a Markdown message to your Telegram chat."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram alert sent.")
            return True
        print(f"❌ Telegram error {r.status_code}: {r.text}")
        return False
    except Exception as e:
        print(f"❌ Telegram request failed: {e}")
        return False


# ============================================================
# TRADINGVIEW DATA + BREAKOUT LOGIC
# ============================================================
# Cooldown tracker so we don't spam
_last_alert = {"UP": 0.0, "DOWN": 0.0}


def _in_cooldown(direction: str) -> bool:
    return (time.time() - _last_alert[direction]) < COOLDOWN_SECS


def _mark_alert(direction: str):
    _last_alert[direction] = time.time()


async def fetch_ohlc():
    """Fetch recent OHLC bars from TradingView via tvkit."""
    async with OHLCV() as client:
        bars = await client.get_historical_ohlcv(
            SYMBOL, interval=INTERVAL, bars_count=BARS_TO_FETCH
        )
        return bars


async def check_breakout():
    """Single check: fetch data, compare, alert if needed."""
    try:
        bars = await fetch_ohlc()
    except Exception as e:
        print(f"⚠️ Data fetch failed: {e}")
        return

    if len(bars) < 2:
        print("⚠️ Not enough bars returned.")
        return

    # Previous completed candle = second-to-last
    prev_candle = bars[-2]
    current_price = bars[-1].close

    prev_high = prev_candle.high
    prev_low  = prev_candle.low

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{now_str}] {SYMBOL} price={current_price} | "
          f"prevH={prev_high} prevL={prev_low}")

    # ---- BREAKOUT ----
    if current_price > prev_high:
        if _in_cooldown("UP"):
            print("↺ Breakout in cooldown, skipping.")
            return
        msg = (
            f"🚀 *BREAKOUT ALERT*\n"
            f"*Symbol:* `{SYMBOL}`\n"
            f"*Interval:* {INTERVAL}\n"
            f"*Price:* `{current_price}`\n"
            f"*Prev 1H High:* `{prev_high}`\n"
            f"*Time:* {now_str}"
        )
        if send_telegram_alert(msg):
            _mark_alert("UP")

    # ---- BREAKDOWN ----
    elif current_price < prev_low:
        if _in_cooldown("DOWN"):
            print("↺ Breakdown in cooldown, skipping.")
            return
        msg = (
            f"📉 *BREAKDOWN ALERT*\n"
            f"*Symbol:* `{SYMBOL}`\n"
            f"*Interval:* {INTERVAL}\n"
            f"*Price:* `{current_price}`\n"
            f"*Prev 1H Low:* `{prev_low}`\n"
            f"*Time:* {now_str}"
        )
        if send_telegram_alert(msg):
            _mark_alert("DOWN")

    else:
        print("— No breakout (price inside prev 1H range).")


# ============================================================
# MAIN LOOP
# ============================================================
async def main_loop():
    # Sanity check credentials
    if "PUT_YOUR" in BOT_TOKEN or "PUT_YOUR" in CHAT_ID:
        print("❌ Please set BOT_TOKEN and CHAT_ID inside the script.")
        return

    print(f"🤖 Alert engine started for {SYMBOL} @ {INTERVAL}")
    send_telegram_alert(f"✅ Alert engine started for `{SYMBOL}` ({INTERVAL})")

    while True:
        try:
            await check_breakout()
        except Exception as e:
            print(f"⚠️ Loop error: {e}")

        print(f"⏳ Sleeping {POLL_SECONDS}s...\n")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")