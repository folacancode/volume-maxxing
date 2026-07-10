import os
import requests

# Env variables from your GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Sniper settings
MAX_MARKET_CAP_USD = float(os.environ.get("MAX_MARKET_CAP_USD", "100000")) # Sub 100k MC
MIN_M5_VOLUME = float(os.environ.get("MIN_M5_VOLUME", "2500"))            # $2.5k+ in last 5m
MIN_M5_BUYS = int(os.environ.get("MIN_M5_BUYS", "15"))                    # 15+ buys in last 5m

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[warn] Telegram credentials missing. Cannot send alert.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[warn] Telegram failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[err] Failed to reach Telegram API: {e}")

def get_trending_tokens(limit=50):
    """Fetches the top trending/boosted tokens directly from DexScreener."""
    url = "https://api.dexscreener.com/token-boosts/top/v1"
    
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            
            unique_addresses = []
            seen = set()
            
            # The API returns an array of objects. We extract the tokenAddress.
            for item in data:
                addr = item.get("tokenAddress")
                if addr and addr not in seen:
                    seen.add(addr)
                    unique_addresses.append(addr)
                    if len(unique_addresses) >= limit:
                        break
            
            return unique_addresses
        else:
            print(f"[err] Failed to fetch trending tokens. Status: {resp.status_code}")
    except Exception as e:
        print(f"[err] Request to DexScreener top boosts failed: {e}")
        
    return []

def main():
    print("Fetching top trending tokens from DexScreener...")
    trending_tokens = get_trending_tokens(limit=50)
    
    if not trending_tokens:
        print("No trending tokens found. Exiting.")
        return

    print(f"Found {len(trending_tokens)} trending tokens. Fetching live market data...")
    
    # DexScreener allows max 30 token addresses per request
    # We chunk our 50 addresses into two batches (e.g., 30 and 20)
    chunked_tokens = [trending_tokens[i:i + 30] for i in range(0, len(trending_tokens), 30)]
    
    all_pairs = []
    for chunk in chunked_tokens:
        addresses = ",".join(chunk) 
        url = f"https://api.dexscreener.com/latest/dex/tokens/{addresses}"
        
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                all_pairs.extend(data.get("pairs", []))
            else:
                print(f"[warn] DexScreener pairs API returned {resp.status_code}")
        except Exception as e:
            print(f"[err] Failed to fetch pair data: {e}")

    if not all_pairs:
        print("No active trading pairs found for the trending tokens.")
        return

    # Track processed addresses to prevent duplicate alerts if a token has multiple liquidity pools
    processed_addresses = set()

    for pair in all_pairs:
        base_token = pair.get("baseToken", {})
        addr = base_token.get("address", "").lower()
        
        if addr in processed_addresses:
            continue
            
        symbol = base_token.get("symbol", "UNKNOWN")
        chain = pair.get("chainId", "unknown").upper()
        
        mcap = pair.get("fdv", 0)  # DexScreener uses FDV for market cap
        m5_stats = pair.get("txns", {}).get("m5", {})
        m5_buys = m5_stats.get("buys", 0)
        m5_vol = pair.get("volume", {}).get("m5", 0)
        
        # 1. Filter: Must be sub-100k MC
        if 0 < mcap <= MAX_MARKET_CAP_USD:
            # 2. Trigger: High velocity in a short window
            if m5_vol >= MIN_M5_VOLUME and m5_buys >= MIN_M5_BUYS:
                
                # Mark as processed so we don't alert twice for the same token
                processed_addresses.add(addr)
                
                msg = (
                    f"🚨 *Trending Micro-Cap Pump* 🚨\n\n"
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
