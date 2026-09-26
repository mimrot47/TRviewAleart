"""
TradingView 1H Green/Red Candle Breakout Alert Engine -> Telegram

===============================================================
LOGIC
===============================================================

Previous completed 1H candle:

1. GREEN candle:
       Close > Open

   If current price > previous candle HIGH:
       -> GREEN HIGH BREAKOUT alert

2. RED candle:
       Close < Open

   If current price < previous candle LOW:
       -> RED LOW BREAKDOWN alert

3. DOJI:
       Close == Open

   -> No alert

===============================================================
TELEGRAM
===============================================================

Windows PowerShell:

$env:TELEGRAM_BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
$env:TELEGRAM_CHAT_ID="1064846152"

Check:

echo $env:TELEGRAM_BOT_TOKEN
echo $env:TELEGRAM_CHAT_ID

Run:

python alert_engine.py
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

SYMBOL = "OANDA:XAUUSD"

INTERVAL = "1H"

# Fetch 3 candles:
# - older candle
# - previous completed candle
# - current candle
BARS_TO_FETCH = 3


# Check TradingView every 30 seconds
POLL_SECONDS = 30


# Same breakout direction cooldown
# 3600 = 1 hour
COOLDOWN_SECS = 3600


# ============================================================
# TELEGRAM ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    ""
).strip()


# ============================================================
# GLOBAL STATE
# ============================================================

_last_alert = {
    "UP": 0.0,
    "DOWN": 0.0
}


# Previous candle identity
# Used to reset breakout state when a new 1H candle starts.
_previous_candle_key = None


# Prevent sending multiple alerts for exactly
# the same candle breakout.
_breakout_alerted_for_candle = {
    "UP": None,
    "DOWN": None
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_utc_time():
    """
    Return current UTC datetime.
    """

    return datetime.now(timezone.utc)


def get_utc_string():
    """
    Return current UTC time as readable string.
    """

    return get_utc_time().strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def validate_telegram_config():
    """
    Validate Telegram environment variables.
    """

    print()
    print("=" * 55)
    print("TELEGRAM CONFIGURATION")
    print("=" * 55)

    token_exists = bool(BOT_TOKEN)
    chat_exists = bool(CHAT_ID)

    if token_exists:

        print("✅ TELEGRAM_BOT_TOKEN loaded")

        print(
            f"   Token length: {len(BOT_TOKEN)}"
        )

    else:

        print(
            "❌ TELEGRAM_BOT_TOKEN is missing"
        )

    if chat_exists:

        print(
            f"✅ TELEGRAM_CHAT_ID loaded: {CHAT_ID}"
        )

    else:

        print(
            "❌ TELEGRAM_CHAT_ID is missing"
        )

    print("=" * 55)
    print()

    return token_exists and chat_exists


# ============================================================
# TELEGRAM API
# ============================================================

def send_telegram_alert(message: str) -> bool:
    """
    Send message to Telegram.
    """

    if not BOT_TOKEN:

        print(
            "❌ Cannot send Telegram message:"
            " BOT_TOKEN is empty."
        )

        return False

    if not CHAT_ID:

        print(
            "❌ Cannot send Telegram message:"
            " CHAT_ID is empty."
        )

        return False


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )


    payload = {

        "chat_id": CHAT_ID,

        "text": message,

        "parse_mode": "HTML",

        "disable_web_page_preview": True
    }


    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )


        if response.status_code == 200:

            print(
                "✅ Telegram alert sent successfully."
            )

            return True


        print(
            f"❌ Telegram API error "
            f"{response.status_code}"
        )

        print(
            response.text
        )

        return False


    except requests.exceptions.Timeout:

        print(
            "❌ Telegram request timeout."
        )

        return False


    except requests.exceptions.ConnectionError:

        print(
            "❌ Telegram connection failed."
        )

        return False


    except Exception as e:

        print(
            f"❌ Telegram request failed: {e}"
        )

        return False


# ============================================================
# TELEGRAM CONNECTION TEST
# ============================================================

def test_telegram_connection():
    """
    Test Telegram bot using getMe API.
    """

    if not BOT_TOKEN:

        return False


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/getMe"
    )


    try:

        response = requests.get(
            url,
            timeout=10
        )


        if response.status_code != 200:

            print(
                "❌ Telegram bot authentication failed."
            )

            print(
                response.text
            )

            return False


        data = response.json()


        if not data.get("ok"):

            print(
                "❌ Telegram API returned an error."
            )

            print(data)

            return False


        bot_info = data.get(
            "result",
            {}
        )


        bot_username = bot_info.get(
            "username",
            "Unknown"
        )


        print(
            f"✅ Telegram bot connected: "
            f"@{bot_username}"
        )


        return True


    except Exception as e:

        print(
            f"❌ Telegram connection test failed: {e}"
        )

        return False


# ============================================================
# COOLDOWN
# ============================================================

def in_cooldown(direction: str) -> bool:
    """
    Check whether alert direction is in cooldown.
    """

    last_time = _last_alert.get(
        direction,
        0.0
    )


    elapsed = time.time() - last_time


    return elapsed < COOLDOWN_SECS


def mark_alert(direction: str):
    """
    Mark alert time.
    """

    _last_alert[direction] = time.time()


# ============================================================
# FETCH TRADINGVIEW OHLC
# ============================================================

async def fetch_ohlc():
    """
    Fetch recent OHLCV data from TradingView.
    """

    async with OHLCV() as client:

        bars = await client.get_historical_ohlcv(

            SYMBOL,

            interval=INTERVAL,

            bars_count=BARS_TO_FETCH
        )

        return bars


# ============================================================
# CANDLE INFORMATION
# ============================================================

def get_candle_color(
    candle
):
    """
    Determine candle color.

    GREEN:
        close > open

    RED:
        close < open

    DOJI:
        close == open
    """

    if candle.close > candle.open:

        return "GREEN"


    if candle.close < candle.open:

        return "RED"


    return "DOJI"


# ============================================================
# BREAKOUT CHECK
# ============================================================

async def check_breakout():

    global _previous_candle_key


    # --------------------------------------------------------
    # FETCH DATA
    # --------------------------------------------------------

    try:

        bars = await fetch_ohlc()

    except Exception as e:

        print(
            f"⚠️ TradingView data fetch failed: {e}"
        )

        return


    # --------------------------------------------------------
    # VALIDATE DATA
    # --------------------------------------------------------

    if not bars:

        print(
            "⚠️ TradingView returned no candles."
        )

        return


    if len(bars) < 2:

        print(
            f"⚠️ Not enough candles."
            f" Received: {len(bars)}"
        )

        return


    # --------------------------------------------------------
    # PREVIOUS COMPLETED CANDLE
    # --------------------------------------------------------

    previous_candle = bars[-2]


    # --------------------------------------------------------
    # CURRENT CANDLE
    # --------------------------------------------------------

    current_candle = bars[-1]


    # --------------------------------------------------------
    # PREVIOUS CANDLE VALUES
    # --------------------------------------------------------

    previous_open = previous_candle.open

    previous_high = previous_candle.high

    previous_low = previous_candle.low

    previous_close = previous_candle.close


    # --------------------------------------------------------
    # CURRENT PRICE
    # --------------------------------------------------------

    current_price = current_candle.close


    # --------------------------------------------------------
    # CANDLE COLOR
    # --------------------------------------------------------

    candle_color = get_candle_color(
        previous_candle
    )


    # --------------------------------------------------------
    # CANDLE KEY
    # --------------------------------------------------------

    # tvkit candle may contain timestamp.
    # Use timestamp if available.
    #
    # If timestamp isn't available, OHLC values
    # provide a stable fallback.

    candle_timestamp = getattr(
        previous_candle,
        "timestamp",
        None
    )


    if candle_timestamp is None:

        candle_key = (
            previous_open,
            previous_high,
            previous_low,
            previous_close
        )

    else:

        candle_key = candle_timestamp


    # --------------------------------------------------------
    # DETECT NEW PREVIOUS CANDLE
    # --------------------------------------------------------

    if _previous_candle_key != candle_key:

        print(
            "\n🔄 New previous 1H candle detected."
        )

        print(
            "Resetting candle-specific alert state."
        )


        _previous_candle_key = candle_key


        _breakout_alerted_for_candle[
            "UP"
        ] = None


        _breakout_alerted_for_candle[
            "DOWN"
        ] = None


    # --------------------------------------------------------
    # CURRENT TIME
    # --------------------------------------------------------

    now_str = get_utc_string()


    # ========================================================
    # DISPLAY CURRENT DATA
    # ========================================================

    print()
    print("-" * 65)

    print(
        f"[{now_str}] {SYMBOL}"
    )

    print(
        f"Previous 1H Candle:"
    )

    print(
        f"  Open  : {previous_open}"
    )

    print(
        f"  High  : {previous_high}"
    )

    print(
        f"  Low   : {previous_low}"
    )

    print(
        f"  Close : {previous_close}"
    )

    print(
        f"  Color : {candle_color}"
    )

    print(
        f"Current Price: {current_price}"
    )

    print("-" * 65)


    # ========================================================
    # GREEN CANDLE
    # ========================================================

    if candle_color == "GREEN":

        print(
            "🟢 Previous 1H candle is GREEN."
        )

        print(
            f"Checking:"
            f" current price ({current_price})"
            f" > previous HIGH ({previous_high})"
        )


        # ----------------------------------------------------
        # GREEN HIGH BREAKOUT
        # ----------------------------------------------------

        if current_price > previous_high:

            print(
                "🚀 GREEN candle HIGH has been crossed!"
            )


            # Same candle already alerted
            if (
                _breakout_alerted_for_candle["UP"]
                == candle_key
            ):

                print(
                    "↺ Already alerted for this "
                    "GREEN candle."
                )

                return


            # Cooldown
            if in_cooldown("UP"):

                remaining = (
                    COOLDOWN_SECS
                    - (
                        time.time()
                        - _last_alert["UP"]
                    )
                )


                print(
                    f"↺ UP alert cooldown active."
                    f" Remaining: "
                    f"{remaining:.0f}s"
                )

                return


            # ------------------------------------------------
            # ALERT MESSAGE
            # ------------------------------------------------

            message = (

                "🚀 <b>GREEN CANDLE "
                "BREAKOUT ALERT</b>\n\n"

                f"<b>Symbol:</b> "
                f"<code>{SYMBOL}</code>\n"

                f"<b>Interval:</b> "
                f"<code>{INTERVAL}</code>\n\n"

                "🟢 <b>Previous 1H Candle</b>\n"

                f"<b>Open:</b> "
                f"<code>{previous_open}</code>\n"

                f"<b>High:</b> "
                f"<code>{previous_high}</code>\n"

                f"<b>Low:</b> "
                f"<code>{previous_low}</code>\n"

                f"<b>Close:</b> "
                f"<code>{previous_close}</code>\n\n"

                f"💰 <b>Current Price:</b> "
                f"<code>{current_price}</code>\n"

                f"🚀 <b>Breakout Level:</b> "
                f"<code>{previous_high}</code>\n\n"

                f"🕐 <b>Time:</b> "
                f"<code>{now_str}</code>"
            )


            # ------------------------------------------------
            # SEND
            # ------------------------------------------------

            if send_telegram_alert(message):

                mark_alert("UP")


                _breakout_alerted_for_candle[
                    "UP"
                ] = candle_key


                print(
                    "✅ GREEN breakout alert sent."
                )


        else:

            print(
                "— No GREEN HIGH breakout."
            )


    # ========================================================
    # RED CANDLE
    # ========================================================

    elif candle_color == "RED":

        print(
            "🔴 Previous 1H candle is RED."
        )

        print(
            f"Checking:"
            f" current price ({current_price})"
            f" < previous LOW ({previous_low})"
        )


        # ----------------------------------------------------
        # RED LOW BREAKDOWN
        # ----------------------------------------------------

        if current_price < previous_low:

            print(
                "📉 RED candle LOW has been crossed!"
            )


            # Same candle already alerted
            if (
                _breakout_alerted_for_candle["DOWN"]
                == candle_key
            ):

                print(
                    "↺ Already alerted for this "
                    "RED candle."
                )

                return


            # Cooldown
            if in_cooldown("DOWN"):

                remaining = (
                    COOLDOWN_SECS
                    - (
                        time.time()
                        - _last_alert["DOWN"]
                    )
                )


                print(
                    f"↺ DOWN alert cooldown active."
                    f" Remaining: "
                    f"{remaining:.0f}s"
                )

                return


            # ------------------------------------------------
            # ALERT MESSAGE
            # ------------------------------------------------

            message = (

                "📉 <b>RED CANDLE "
                "BREAKDOWN ALERT</b>\n\n"

                f"<b>Symbol:</b> "
                f"<code>{SYMBOL}</code>\n"

                f"<b>Interval:</b> "
                f"<code>{INTERVAL}</code>\n\n"

                "🔴 <b>Previous 1H Candle</b>\n"

                f"<b>Open:</b> "
                f"<code>{previous_open}</code>\n"

                f"<b>High:</b> "
                f"<code>{previous_high}</code>\n"

                f"<b>Low:</b> "
                f"<code>{previous_low}</code>\n"

                f"<b>Close:</b> "
                f"<code>{previous_close}</code>\n\n"

                f"💰 <b>Current Price:</b> "
                f"<code>{current_price}</code>\n"

                f"📉 <b>Breakdown Level:</b> "
                f"<code>{previous_low}</code>\n\n"

                f"🕐 <b>Time:</b> "
                f"<code>{now_str}</code>"
            )


            # ------------------------------------------------
            # SEND
            # ------------------------------------------------

            if send_telegram_alert(message):

                mark_alert("DOWN")


                _breakout_alerted_for_candle[
                    "DOWN"
                ] = candle_key


                print(
                    "✅ RED breakdown alert sent."
                )


        else:

            print(
                "— No RED LOW breakdown."
            )


    # ========================================================
    # DOJI
    # ========================================================

    else:

        print(
            "⚪ Previous 1H candle is DOJI."
        )

        print(
            "— No breakout/breakdown alert."
        )


# ============================================================
# MAIN LOOP
# ============================================================

async def main_loop():

    # --------------------------------------------------------
    # VALIDATE ENVIRONMENT
    # --------------------------------------------------------

    if not validate_telegram_config():

        print()
        print(
            "❌ Telegram configuration failed."
        )

        print()
        print(
            "PowerShell commands:"
        )

        print(
            '$env:TELEGRAM_BOT_TOKEN="YOUR_NEW_BOT_TOKEN"'
        )

        print(
            '$env:TELEGRAM_CHAT_ID="1064846152"'
        )

        return


    # --------------------------------------------------------
    # TEST TELEGRAM BOT
    # --------------------------------------------------------

    print(
        "🔍 Testing Telegram connection..."
    )


    if not test_telegram_connection():

        print(
            "❌ Telegram bot connection failed."
        )

        print(
            "Please check your bot token."
        )

        return


    # --------------------------------------------------------
    # ENGINE START
    # --------------------------------------------------------

    print()
    print("=" * 65)

    print(
        "🤖 TRADINGVIEW BREAKOUT ALERT ENGINE"
    )

    print("=" * 65)

    print(
        f"Symbol          : {SYMBOL}"
    )

    print(
        f"Interval        : {INTERVAL}"
    )

    print(
        "Green Candle    : HIGH breakout"
    )

    print(
        "Red Candle      : LOW breakdown"
    )

    print(
        "Doji            : No alert"
    )

    print(
        f"Polling         : {POLL_SECONDS} seconds"
    )

    print(
        f"Cooldown        : "
        f"{COOLDOWN_SECS} seconds"
    )

    print("=" * 65)


    # --------------------------------------------------------
    # STARTUP TELEGRAM MESSAGE
    # --------------------------------------------------------

    startup_message = (

        "✅ <b>Alert Engine Started</b>\n\n"

        f"<b>Symbol:</b> "
        f"<code>{SYMBOL}</code>\n"

        f"<b>Interval:</b> "
        f"<code>{INTERVAL}</code>\n\n"

        "🟢 Green candle → HIGH breakout\n"

        "🔴 Red candle → LOW breakdown\n"

        "⚪ Doji → No alert"
    )


    send_telegram_alert(
        startup_message
    )


    # --------------------------------------------------------
    # CONTINUOUS LOOP
    # --------------------------------------------------------

    while True:

        try:

            await check_breakout()

        except Exception as e:

            print()
            print(
                f"⚠️ Unexpected loop error: {e}"
            )


        print()

        print(
            f"⏳ Next check in "
            f"{POLL_SECONDS} seconds..."
        )

        print()


        await asyncio.sleep(
            POLL_SECONDS
        )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main_loop()
        )

    except KeyboardInterrupt:

        print()
        print(
            "🛑 Alert engine stopped by user."
        )

    except Exception as e:

        print()
        print(
            f"❌ Fatal error: {e}"
        )
