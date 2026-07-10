import os
import requests

# Env variables from your GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
WATCHLIST = [a.strip().lower() for a in os.environ.get("WATCHLIST", "").split(",") if a.strip()]

# Sniper settings
MAX_MARKET_CAP_USD = float(os.environ.get("MAX_MARKET_CAP_USD", "100000")) # Sub 100k MC
MIN_M5_VOLUME = float(os.environ.get("MIN_M5_VOLUME", "2500"))            # $2.5k+ in last 5m
MIN_M5_BUYS = int(os.environ.get("MIN_M5_BUYS", "15"))                   # 15+ buys in last 5m

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"[warn] Telegram failed: {resp.status_code} {resp.text}")

def main():
    if not WATCHLIST:
        print("Watchlist is empty. Add tokens to your GitHub secrets or environment variables.")
        return

    # DexScreener lets you request up to 30 tokens at once separated by commas
    addresses = ",".join(WATCHLIST[:30]) 
    url = f"https://api.dexscreener.com/latest/dex/tokens/{addresses}"
    
    print(f"Scanning {len(WATCHLIST[:30])} tokens via DexScreener...")
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"[err] DexScreener returned status {resp.status_code}")
            return
        data = resp.json()
    except Exception as e:
        print(f"[err] API request failed: {e}")
        return

    pairs = data.get("pairs", [])
    if not pairs:
        print("No active trading pairs found for these tokens.")
        return

    for pair in pairs:
        base_token = pair.get("baseToken", {})
        addr = base_token.get("address", "").lower()
        symbol = base_token.get("symbol", "UNKNOWN")
        chain = pair.get("chainId", "unknown").upper()
        
        mcap = pair.get("fdv", 0)  # DexScreener uses FDV for market cap
        m5_stats = pair.get("txns", {}).get("m5", {})
        m5_buys = m5_stats.get("buys", 0)
        m5_vol = pair.get("volume", {}).get("m5", 0)
        
        # Check if it fits the sub-100k velocity criteria
        if 0 < mcap <= MAX_MARKET_CAP_USD:
            if m5_vol >= MIN_M5_VOLUME and m5_buys >= MIN_M5_BUYS:
                msg = (
                    f"🚨 *Micro-Cap Pump Detected* 🚨\n\n"
                    f"**Token:** `{symbol}` ({chain})\n"
                    f"**CA:** `{addr}`\n"
                    f"**Market Cap:** ${mcap:,.0f}\n"
                    f"**5m Buys:** {m5_buys}\n"
                    f"**5m Volume:** ${m5_vol:,.0f}\n\n"
                    f"[View on DexScreener]({pair.get('url')})"
                )
                print(f"🔥 Triggered: {symbol} at ${mcap:,.0f} MC")
                send_telegram(msg)

if __name__ == "__main__":
    main()
