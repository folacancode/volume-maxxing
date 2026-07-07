import requests
import os
import time

# --- CONFIGURATION ---
BIRDEYE_API_KEY = os.environ.get("BIRDEYE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def get_trending_tokens():
    """Fetches the top 20 trending Solana tokens from Birdeye."""
    # Birdeye allows a maximum limit of 20 tokens per request for this endpoint
    url = "https://public-api.birdeye.so/defi/token_trending?sort_by=rank&sort_type=asc&offset=0&limit=20"
    headers = {
        "x-chain": "solana",
        "X-API-KEY": BIRDEYE_API_KEY,
        "accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers).json()
        if response.get("success"):
            return response["data"]["tokens"]
        return []
    except Exception as e:
        print(f"Error fetching trending tokens: {e}")
        return []

def check_volume_spikes():
    # 1. Grab the dynamic list of hot tokens
    trending_tokens = get_trending_tokens()
    if not trending_tokens:
        print("No trending tokens found.")
        return

    print(f"Hunting for volume spikes across {len(trending_tokens)} trending tokens...")

    # 2. Loop through them and check the volume logic
    for token in trending_tokens:
        address = token["address"]
        symbol = token["symbol"]
        
        # Pause for 1.2 seconds between checks to respect Birdeye's free tier rate limit (1 request/sec)
        time.sleep(1.2)

        url = f"https://public-api.birdeye.so/defi/ohlcv?type=15m&currency=usd&ui_amount_mode=raw&address={address}"
        headers = {
            "x-chain": "solana", 
            "X-API-KEY": BIRDEYE_API_KEY, 
            "accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers).json()
            if response.get("success"):
                candles = response["data"]["items"][-4:]
                if len(candles) < 4:
                    continue
                
                v1, v2, v3, v4 = [c["v"] for c in candles]
                is_v4_green = candles[3]["c"] > candles[3]["o"]
                
                if v1 < v2 < v3 < v4 and v4 > (v1 * 5) and is_v4_green:
                    msg = (
                        f"🚨 <b>VOLUME SPIKE DETECTED</b> 🚨\n\n"
                        f"<b>${symbol}</b>\n"
                        f"<code>{address}</code>\n\n"
                        f"Cascading 15m Volume:\n"
                        f"V1: ${v1:,.0f}\n"
                        f"V2: ${v2:,.0f}\n"
                        f"V3: ${v3:,.0f}\n"
                        f"V4: ${v4:,.0f} 🟢\n\n"
                        f"<a href='https://birdeye.so/token/{address}?chain=solana'>View on Birdeye</a>"
                    )
                    send_telegram_alert(msg)
                    print(f"Alert fired for {symbol} ({address})!")
                else:
                    print(f"[{symbol}] Checked. Current V4: ${v4:,.0f}")
                    
        except Exception as e:
            print(f"Error checking {symbol} ({address}): {e}")

if __name__ == "__main__":
    check_volume_spikes()
