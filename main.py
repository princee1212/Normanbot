#!/usr/bin/env python3
"""
Norman Signal v2 — improved, production-ready version.

Features:
- env validation
- requests.Session with retries
- timeouts + backoff handling for 429
- persistent deduplication (notified_tx.json)
- configurable thresholds via env vars
- logging
"""
import os
import time
import json
import logging
from typing import Optional, Set, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration (env vars)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
CHAIN = os.getenv("CHAIN", "bsc")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))        # seconds
MIN_USD_ALERT = float(os.getenv("MIN_USD_ALERT", "10000"))   # min USD to alert
STRONG_BUY_TH = float(os.getenv("STRONG_BUY_TH", "50000"))
WHALE_TH = float(os.getenv("WHALE_TH", "100000"))
NOTIFIED_FILE = os.getenv("NOTIFIED_FILE", "notified_tx.json")
MORALIS_LIMIT = int(os.getenv("MORALIS_LIMIT", "50"))        # number of transfers to fetch

# Basic validation
if not BOT_TOKEN or not CHAT_ID or not MORALIS_API_KEY:
    raise SystemExit("Missing required env vars: BOT_TOKEN, CHAT_ID, and MORALIS_API_KEY must be set.")

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("norman-signal")

# HTTP session with retries
session = requests.Session()
retry_strategy = Retry(
    total=5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

HEADERS = {
    "accept": "application/json",
    "X-API-Key": MORALIS_API_KEY,
    "User-Agent": "norman-signal/1.0"
}

def load_notified(path: str) -> Set[str]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return set(data if isinstance(data, list) else [])
    except FileNotFoundError:
        return set()
    except Exception as e:
        logger.exception("Failed to load notified file; starting fresh.")
        return set()

def save_notified(path: str, notified: Set[str]) -> None:
    try:
        with open(path, "w") as f:
            json.dump(list(notified), f)
    except Exception:
        logger.exception("Failed to persist notified txs.")

def send_telegram(msg: str, parse_mode: str = "HTML") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = session.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send telegram message")
        return False

def get_moralis_transfers(limit: int = MORALIS_LIMIT, chain: str = CHAIN) -> Optional[Dict]:
    url = "https://deep-index.moralis.io/api/v2/erc20/transfers"
    params = {"chain": chain, "limit": limit}
    try:
        resp = session.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 429:
            # Let Retry/backoff handle next attempts, but log and return None for this cycle
            logger.warning("Rate limited by Moralis (429); backing off this cycle.")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Error fetching Moralis transfers")
        return None

def extract_tx_id(tx: Dict) -> Optional[str]:
    # Try multiple possible fields to identify a transaction uniquely
    for key in ("transaction_hash", "transactionHash", "hash", "tx_hash"):
        v = tx.get(key)
        if v:
            return str(v)
    # Fallback: combine block_number + log_index if present
    block = tx.get("block_number") or tx.get("blockNumber")
    idx = tx.get("log_index") or tx.get("logIndex")
    if block and idx:
        return f"{block}:{idx}"
    return None

def parse_usd_value(tx: Dict) -> Optional[float]:
    # Primary: value_usd if present
    v = tx.get("value_usd")
    if v is not None:
        try:
            return float(v)
        except Exception:
            return None
    # Secondary: some Moralis responses include 'value' and token_price
    # Here we try a best-effort parse but skip if not possible.
    try:
        value = tx.get("value")
        token_price = tx.get("usd_price") or tx.get("token_price_usd") or tx.get("price_usd")
        decimals = tx.get("token_decimal") or tx.get("tokenDecimals") or 18
        if value is not None and token_price is not None:
            # value may be an integer string in smallest unit
            value_float = float(value) / (10 ** int(decimals))
            return value_float * float(token_price)
    except Exception:
        return None
    return None

def build_message(token_name: str, token_symbol: str, usd_value: float, contract: str, signal: str, tx_url: Optional[str] = None) -> str:
    token_name_safe = token_name or "Unknown"
    token_symbol_safe = token_symbol or ""
    usd_fmt = f"${usd_value:,.2f}"
    parts = [
        "🚨 <b>NORMAN SIGNAL V2</b>",
        "",
        f"Token: <b>{token_name_safe}</b> ({token_symbol_safe})",
        f"Buy Size: <b>{usd_fmt}</b>",
        f"Contract: <code>{contract}</code>",
        "",
        f"Signal: {signal}"
    ]
    if tx_url:
        parts.append("")
        parts.append(f"<a href=\"{tx_url}\">View TX</a>")
    return "\n".join(parts)

def get_bsc_tx_url(tx_id: str) -> str:
    # BSC explorer tx url
    return f"https://bscscan.com/tx/{tx_id}"

def get_swaps(notified: Set[str]) -> Set[str]:
    data = get_moralis_transfers()
    if not data:
        return notified

    results = data.get("result") or data.get("data") or []
    if not isinstance(results, list):
        logger.debug("Unexpected results shape from Moralis")
        return notified

    new_notified = set()
    for tx in results:
        try:
            tx_id = extract_tx_id(tx)
            if not tx_id:
                logger.debug("Could not determine tx id for tx: %s", tx)
                continue
            if tx_id in notified or tx_id in new_notified:
                continue

            usd_value = parse_usd_value(tx)
            if usd_value is None:
                logger.debug("Skipping tx %s: no USD value", tx_id)
                continue

            if usd_value < MIN_USD_ALERT:
                continue

            token_name = tx.get("token_name") or tx.get("name") or "Unknown"
            token_symbol = tx.get("token_symbol") or tx.get("symbol") or ""
            contract = tx.get("address") or tx.get("token_address") or tx.get("contract_address") or "Unknown"

            # Skip stablecoins
            if token_symbol.upper() in {"USDT", "USDC", "BUSD"}:
                continue

            signal = "⚠️ WATCH"
            if usd_value > STRONG_BUY_TH:
                signal = "🔥 STRONG BUY"
            if usd_value > WHALE_TH:
                signal = "🚀 WHALE ACCUMULATION"

            tx_url = None
            # If chain is BSC and tx id looks like a hash
            if CHAIN.lower() in ("bsc", "bsc-testnet") and len(tx_id) >= 60:
                tx_url = get_bsc_tx_url(tx_id)

            message = build_message(token_name, token_symbol, usd_value, contract, signal, tx_url)
            sent = send_telegram(message)
            if sent:
                logger.info("Alert sent for tx %s (%s %s) USD %s", tx_id, token_name, token_symbol, usd_value)
                new_notified.add(tx_id)
            else:
                logger.warning("Alert NOT sent for tx %s", tx_id)

        except Exception:
            logger.exception("Error processing tx entry")

    # Persist union of existing + new
    notified |= new_notified
    return notified

def main_loop():
    notified = load_notified(NOTIFIED_FILE)
    logger.info("Starting Norman Signal v2 — loaded %d previously-notified txs", len(notified))
    try:
        while True:
            notified = get_swaps(notified)
            save_notified(NOTIFIED_FILE, notified)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting.")
    except Exception:
        logger.exception("Unhandled error in main loop")
    finally:
        save_notified(NOTIFIED_FILE, notified)

if __name__ == "__main__":
    main_loop()
