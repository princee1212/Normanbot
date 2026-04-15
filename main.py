import requests
import time
import os

# ── Environment Variables ──────────────────────────────────────────────────────

BOT_TOKEN = os.getenv(“BOT_TOKEN”)
CHAT_ID = os.getenv(“CHAT_ID”)
MORALIS_API_KEY = os.getenv(“MORALIS_API_KEY”)

# ── Config ─────────────────────────────────────────────────────────────────────

MIN_USD = 10000       # Ignore trades below this
SLEEP_SECONDS = 20    # How often to poll (seconds)
CHAIN = “bsc”

# Stablecoins to ignore

STABLECOINS = {“USDT”, “USDC”, “BUSD”, “DAI”, “TUSD”, “USDD”}

# Track already-sent transactions to avoid duplicates

seen_hashes = set()

# ── Telegram ───────────────────────────────────────────────────────────────────

def send_telegram(msg):
url = f”https://api.telegram.org/bot{BOT-TOKEN}/sendMessage”
try:
response = requests.post(url, data={
“chat_id”: CHAT_ID,
“text”: msg,
“parse_mode”: “HTML”
}, timeout=10)
if not response.ok:
print(f”[Telegram Error] {response.status_code}: {response.text}”)
except Exception as e:
print(f”[Telegram Exception] {e}”)

# ── Signal Logic ───────────────────────────────────────────────────────────────

def get_signal(usd_value):
if usd_value >= 100000:
return “🚀 WHALE ACCUMULATION”
elif usd_value >= 50000:
return “🔥 STRONG BUY”
else:
return “⚠️ WATCH”

# ── Moralis Fetch ──────────────────────────────────────────────────────────────

def get_swaps():
url = “https://deep-index.moralis.io/api/v2/erc20/transfers”
headers = {
“accept”: “application/json”,
“X-API-Key”: MORALIS_API_KEY
}
params = {
“chain”: CHAIN,
“limit”: 20
}

```
try:
    response = requests.get(url, headers=headers, params=params, timeout=15)
    data = response.json()
except Exception as e:
    print(f"[Moralis Exception] {e}")
    return

if "result" not in data:
    print(f"[Moralis] Unexpected response: {data}")
    return

for tx in data["result"]:
    try:
        # ── Deduplicate ────────────────────────────────────────────────────
        tx_hash = tx.get("transaction_hash", "")
        if tx_hash in seen_hashes:
            continue
        seen_hashes.add(tx_hash)

        # ── USD Value ──────────────────────────────────────────────────────
        usd_raw = tx.get("value_usd")
        if usd_raw is None:
            continue

        try:
            usd_value = float(usd_raw)
        except (ValueError, TypeError):
            continue

        if usd_value < MIN_USD:
            continue

        # ── Token Info ─────────────────────────────────────────────────────
        token_name = tx.get("token_name", "").strip()
        token_symbol = tx.get("token_symbol", "").strip().upper()
        contract = tx.get("token_address", "N/A")
        from_wallet = tx.get("from_address", "N/A")
        to_wallet = tx.get("to_address", "N/A")

        if not token_name or len(token_name) < 2:
            continue

        if token_symbol in STABLECOINS:
            continue

        # ── Build Message ──────────────────────────────────────────────────
        signal = get_signal(usd_value)

        message = (
            f"🚨 <b>NORMAN SIGNAL V2</b>\n\n"
            f"🪙 Token: <b>{token_name} ({token_symbol})</b>\n"
            f"💵 Value: <b>${usd_value:,.2f}</b>\n"
            f"📋 Contract: <code>{contract}</code>\n"
            f"📤 From: <code>{from_wallet}</code>\n"
            f"📥 To:   <code>{to_wallet}</code>\n\n"
            f"Signal: {signal}"
        )

        print(f"[Alert] {token_name} | ${usd_value:,.2f} | {signal}")
        send_telegram(message)

    except Exception as e:
        print(f"[TX Error] {e}")
        continue
```

# ── Main Loop ──────────────────────────────────────────────────────────────────

def main():
print(“✅ NORMAN BOT STARTED”)
print(f”   Chain     : {CHAIN}”)
print(f”   Min USD   : ${MIN_USD:,}”)
print(f”   Interval  : {SLEEP_SECONDS}s”)
print(“─” * 40)

```
while True:
    print(f"[{time.strftime('%H:%M:%S')}] Checking swaps...")
    get_swaps()
    time.sleep(SLEEP_SECONDS)
```

if **name** == “**main**”:
main()
