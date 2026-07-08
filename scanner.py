"""
Meme-coin buy-volume spike scanner.

Pulls candidate Solana tokens (your watchlist + Birdeye's meme/trending feed),
fetches recent swaps, buckets them into 15-minute windows, and alerts on Telegram
when buy volume in the latest bucket spikes vs the prior one.

Requires env vars:
  BIRDEYE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Optional env vars (all have defaults, see README):
  CHAIN, WATCHLIST, MAX_DISCOVERY_TOKENS, SPIKE_MULTIPLIER,
  MIN_BUY_VOLUME_USD, RE_ALERT_COOLDOWN_SEC

Schema confirmed against a live DEBUG=1 run on 2026-07-08:
- blockUnixTime and side ("buy"/"sell") are top-level fields on each trade,
  as expected.
- There is NO direct USD-volume field on a trade. Each trade has `base` and
  `quote` legs, each with `uiAmount` (token quantity) and `price` (USD per
  token). USD size of the trade = uiAmount * price on either leg; see
  trade_usd_volume() below, which averages both legs for robustness.
"""

import os
import time
import json
import requests
from datetime import datetime, timezone

BIRDEYE_API_KEY = os.environ["BIRDEYE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHAIN = os.environ.get("CHAIN", "solana")
WATCHLIST = [a.strip() for a in os.environ.get("WATCHLIST", "").split(",") if a.strip()]
MAX_DISCOVERY_TOKENS = int(os.environ.get("MAX_DISCOVERY_TOKENS", "6"))
SPIKE_MULTIPLIER = float(os.environ.get("SPIKE_MULTIPLIER", "3"))
MIN_BUY_VOLUME_USD = float(os.environ.get("MIN_BUY_VOLUME_USD", "5000"))
MAX_MARKET_CAP_USD = float(os.environ.get("MAX_MARKET_CAP_USD", "3000000"))
RE_ALERT_COOLDOWN_SEC = int(os.environ.get("RE_ALERT_COOLDOWN_SEC", "3600"))
DEBUG = os.environ.get("DEBUG", "") == "1"

STATE_FILE = "state.json"
BASE_URL = "https://public-api.birdeye.so"
HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": CHAIN,
    "accept": "application/json",
}


def birdeye_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
    time.sleep(1.1)  # free tier = 1 req/sec, stay under it
    if r.status_code != 200:
        print(f"[warn] GET {path} -> {r.status_code}: {r.text[:300]}")
        return None
    data = r.json()
    if DEBUG:
        print(f"[debug] {path} params={params} ->\n{json.dumps(data, indent=2)[:1500]}")
    return data


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"alerted": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def discover_candidates():
    """Watchlist + Birdeye's meme-token feed sorted by 24h volume, capped for CU budget."""
    candidates = list(dict.fromkeys(WATCHLIST))  # preserve order, dedupe
    if MAX_DISCOVERY_TOKENS > 0:
        data = birdeye_get(
            "/defi/v3/token/meme/list",
            params={"sort_by": "volume_24h_usd", "sort_type": "desc", "offset": 0, "limit": MAX_DISCOVERY_TOKENS},
        )
        if data and data.get("success"):
            for item in data.get("data", {}).get("items", []):
                addr = item.get("address")
                mcap = item.get("market_cap")
                if not addr or addr in candidates:
                    continue
                if mcap is not None and mcap > MAX_MARKET_CAP_USD:
                    continue  # skip already-pumped tokens above the ceiling
                candidates.append(addr)
    return candidates


def get_recent_trades(address, limit=50):
    data = birdeye_get(
        "/defi/txs/token",
        params={"address": address, "tx_type": "swap", "sort_type": "desc", "limit": limit},
    )
    if not data or not data.get("success"):
        return []
    return data.get("data", {}).get("items", [])


def trade_usd_volume(t):
    """Birdeye /defi/txs/token trades have no direct USD field. Each trade has
    base/quote legs, each with uiAmount (token qty) and price (USD/token).
    uiAmount * price on either leg gives the trade's USD size; average both
    legs for robustness against float/rounding quirks on either side."""
    vals = []
    for leg in (t.get("base") or {}, t.get("quote") or {}):
        try:
            amt = leg.get("uiAmount")
            price = leg.get("price")
            if amt is not None and price is not None:
                vals.append(float(amt) * float(price))
        except (TypeError, ValueError):
            continue
    return sum(vals) / len(vals) if vals else 0.0


def bucket_buy_volume(trades, bucket_minutes=15, buckets=4):
    """Return buy-volume-USD per 15-min bucket, oldest first, newest last."""
    now = datetime.now(timezone.utc).timestamp()
    bucket_seconds = bucket_minutes * 60
    vols = [0.0] * buckets
    for t in trades:
        ts = t.get("blockUnixTime") or t.get("block_unix_time")
        if ts is None:
            continue
        age = now - ts
        idx_from_now = int(age // bucket_seconds)  # 0 = current (newest) bucket
        if idx_from_now < 0 or idx_from_now >= buckets:
            continue
        side = (t.get("side") or "").lower()
        usd = trade_usd_volume(t)
        if side == "buy":
            vols[buckets - 1 - idx_from_now] += float(usd)
    return vols


def check_spike(vols):
    """vols: oldest->newest. Flag when the newest bucket jumps hard vs the prior one."""
    if len(vols) < 2:
        return False, ""
    latest, prior = vols[-1], vols[-2]
    if latest < MIN_BUY_VOLUME_USD:
        return False, ""
    ratio = (latest / prior) if prior > 0 else float("inf")
    if ratio >= SPIKE_MULTIPLIER:
        ratio_str = "∞" if ratio == float("inf") else f"{ratio:.1f}x"
        return True, f"buy volume {prior:,.0f} -> {latest:,.0f} USD ({ratio_str})"
    return False, ""


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[warn] Telegram send failed: {resp.status_code} {resp.text[:300]}")


def main():
    state = load_state()
    candidates = discover_candidates()
    print(f"Scanning {len(candidates)} tokens: {candidates}")

    for addr in candidates:
        trades = get_recent_trades(addr)
        if not trades:
            continue
        vols = bucket_buy_volume(trades)
        flagged, reason = check_spike(vols)
        last_alert = state["alerted"].get(addr, 0)
        now = time.time()

        if flagged and (now - last_alert > RE_ALERT_COOLDOWN_SEC):
            msg = (
                f"🚨 *Buy volume spike*\n"
                f"Token: `{addr}`\n"
                f"{reason}\n"
                f"Last 4x15m buy vol (USD): {[round(v) for v in vols]}\n"
                f"https://dexscreener.com/{CHAIN}/{addr}"
            )
            send_telegram(msg)
            state["alerted"][addr] = now
            print(f"ALERT sent for {addr}: {reason}")

    save_state(state)


if __name__ == "__main__":
    main()
