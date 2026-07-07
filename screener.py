import requests
import os

# --- CONFIGURATION (Pulls from GitHub Secrets securely) ---
BIRDEYE_API_KEY = os.environ.get("BIRDEYE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TOKENS_TO_WATCH = [
    "So11111111111111111111111111111111111111112", # Example: SOL, add yours here
]

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def check_volume_spikes():
    for address in TOKENS_TO_WATCH:
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
                        f"<code>{address}</code>\n\n"
                        f"Cascading 15m Volume:\n"
                        f"V1: ${v1:,.0f}\n"
                        f"V2: ${v2:,.0f}\n"
                        f"V3: ${v3:,.0f}\n"
                        f"V4: ${v4:,.0f} 🟢\n\n"
                        f"<a href='https://birdeye.so/token/{address}?chain=solana'>Birdeye</a>"
                    )
                    send_telegram_alert(msg)
                    print(f"Alert fired for {address}!")
                else:
                    print(f"[{address}] Checked. Current V4: ${v4:,.0f}")
                    
        except Exception as e:
            print(f"Error checking {address}: {e}")

if __name__ == "__main__":
    check_volume_spikes()
