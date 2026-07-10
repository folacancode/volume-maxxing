import os
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Sniper settings
MAX_MARKET_CAP_USD = float(os.environ.get("MAX_MARKET_CAP_USD", "100000")) 
MIN_M5_VOLUME = float(os.environ.get("MIN_M5_VOLUME", "2500"))            
MIN_M5_BUYS = int(os.environ.get("MIN_M5_BUYS", "15"))                    

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[warn] Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"[err] Telegram failed: {e}")

def get_trending_tokens(limit=30):
    url = "https://api.dexscreener.com/token-boosts/top/v1"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            seen = set()
            return [item.get("tokenAddress") for item in resp.json() if item.get("tokenAddress") and not (item.get("tokenAddress") in seen or seen.add(item.get("tokenAddress")))]][:limit]
    except Exception as e:
        print(f"[err] Failed fetching trending: {e}")
    return []

def main():
    print("Step 1: Fetching top trending tokens from DexScreener...")
    trending_tokens = get_trending_tokens(limit=30)
    
    if not trending_tokens:
        print("❌ No trending tokens found.")
        return

    print(f"Step 2: Found {len(trending_tokens)} tokens. Requesting live pair data...")
    addresses = ",".join(trending_tokens) 
    url = f"https://api.dexscreener.com/latest/dex/tokens/{addresses}"
    
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"❌ DexScreener API error: {resp.status_code}")
            return
        pairs = resp.json().get("pairs", [])
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return

    print("\nStep 3: Evaluating Token Metrics against filters:")
    print(f"Filters -> Max MC: ${MAX_MARKET_CAP_USD:,.0f} | Min 5m Vol: ${MIN_M5_VOLUME:,.0f} | Min 5m Buys: {MIN_M5_BUYS}")
    print("-" * 80)

    processed_addresses = set()
    alert_triggered = False

    for pair in pairs:
        base_token = pair.get("baseToken", {})
        addr = base_token.get("address", "").lower()
        if addr in processed_addresses:
            continue
            
        symbol = base_token.get("symbol", "UNKNOWN")
        chain = pair.get("chainId", "unknown").upper()
        mcap = pair.get("fdv", 0)  
        m5_stats = pair.get("txns", {}).get("m5", {})
        m5_buys = m5_stats.get("buys", 0)
        m5_vol = pair.get("volume", {}).get("m5", 0)
        
        processed_addresses.add(addr)

        # Print the status of every single coin checked so you see it working
        print(f"🔍 Checking {symbol} ({chain}) | MC: ${mcap:,.0f} | 5m Vol: ${m5_vol:,.0f} | 5m Buys: {m5_buys}")

        if 0 < mcap <= MAX_MARKET_CAP_USD:
            if m5_vol >= MIN_M5_VOLUME and m5_buys >= MIN_M5_BUYS:
                alert_triggered = True
                msg = (
                    f"🚨 *Trending Micro-Cap Pump* 🚨\n\n"
                    f"**Token:** `{symbol}` ({chain})\n"
                    f"**CA:** `{addr}`\n"
                    f"**Market Cap:** ${mcap:,.0f}\n"
                    f"**5m Buys:** {m5_buys}\n"
                    f"**5m Volume:** ${m5_vol:,.0f}\n\n"
                    f"[View on DexScreener]({pair.get('url')})"
                )
                print(f"   🔥 MATCH FOUND! Sending Telegram alert for {symbol}...")
                send_telegram(msg)

    print("-" * 80)
    if not alert_triggered:
        print("Scan finished successfully. No tokens matched the filters on this run.")
    else:
        print("Scan finished successfully. Alerts dispatched.")

if __name__ == "__main__":
    main()
