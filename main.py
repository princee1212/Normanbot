import requests
import time

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

ETHERSCAN_API_KEY = "YourApiKeyHere"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=data)

def get_large_transactions():
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address=0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
    
    response = requests.get(url)
    data = response.json()

    if data["status"] == "1":
        for tx in data["result"][:5]:
            value_eth = int(tx["value"]) / 10**18
            if value_eth > 50:  # Whale threshold
                msg = f"""
🚨 Whale Transaction Detected!

From: {tx['from']}
To: {tx['to']}
Amount: {value_eth:.2f} ETH
"""
                send_telegram(msg)

while True:
    get_large_transactions()
    time.sleep(60)
