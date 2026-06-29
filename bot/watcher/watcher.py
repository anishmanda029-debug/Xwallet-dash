"""
XWALLET Standalone Watcher
Polls your manually configured deposit addresses (from .env) every N seconds.
When a new confirmed incoming tx is found, it securely notifies the main bot
via webhook with HMAC signature verification.

Security:
- HMAC-SHA256 signature on every webhook (SHARED_SECRET)
- Minimum confirmations required before crediting (MIN_CONFIRMATIONS)
- Seen tx stored in SQLite to prevent double-credit
- No private keys ever touched here

Run separately:
    cd bot/watcher
    python watcher.py
"""
import asyncio
import aiohttp
import hashlib
import hmac
import json
import time

from config import config
import seen_store
from utils import btc_watcher, ltc_watcher, eth_watcher, sol_watcher, usdt_erc20_watcher, usdt_trc20_watcher

WATCHERS = {
    "btc":       btc_watcher,
    "ltc":       ltc_watcher,
    "eth":       eth_watcher,
    "sol":       sol_watcher,
    "usdterc20": usdt_erc20_watcher,
    "usdttrc20": usdt_trc20_watcher,
}

MIN_CONFIRMATIONS = {
    "btc":       2,
    "ltc":       3,
    "eth":       12,
    "sol":       1,
    "usdterc20": 12,
    "usdttrc20": 20,
}


def _sign_payload(payload: dict, secret: str) -> str:
    """HMAC-SHA256 signature for webhook security."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def notify_main_bot(session: aiohttp.ClientSession, payload: dict):
    """POST to main bot webhook with HMAC signature."""
    signature = _sign_payload(payload, config.shared_secret)
    headers = {
        "Authorization": f"Bearer {config.shared_secret}",
        "X-Signature":   signature,
        "Content-Type":  "application/json",
    }
    try:
        async with session.post(
            f"{config.main_bot_url}/webhooks/watcher",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.text()
            if resp.status == 200:
                print(f"[notify] ✅ Bot credited: {payload['coin']} {payload['amount']} tx:{payload['tx_hash'][:16]}…")
            else:
                print(f"[notify] ⚠️  Bot returned {resp.status}: {body}")
    except Exception as e:
        print(f"[notify] ❌ Failed to reach main bot: {e}")


async def poll_once(session: aiohttp.ClientSession):
    for wallet in config.active_wallets():
        watcher = WATCHERS.get(wallet.symbol)
        if not watcher:
            continue

        try:
            incoming = await watcher.get_new_incoming(wallet.address)
        except Exception as e:
            print(f"[poll] ❌ Error checking {wallet.symbol} ({wallet.address[:12]}…): {e}")
            continue

        min_conf = MIN_CONFIRMATIONS.get(wallet.symbol, 1)

        for tx in incoming:
            if not tx.tx_hash:
                continue

            # Skip if not enough confirmations
            if tx.confirmations < min_conf:
                print(f"[poll] ⏳ {wallet.symbol} tx {tx.tx_hash[:16]}… only {tx.confirmations}/{min_conf} confirmations — waiting")
                continue

            # Skip if already processed
            if seen_store.is_seen(wallet.symbol, tx.tx_hash):
                continue

            seen_store.mark_seen(wallet.symbol, tx.tx_hash)

            print(f"[poll] 💰 NEW {wallet.symbol.upper()} deposit: {tx.amount} | tx:{tx.tx_hash[:20]}… | confs:{tx.confirmations}")

            await notify_main_bot(session, {
                "coin":          wallet.symbol,
                "tx_hash":       tx.tx_hash,
                "to_address":    wallet.address,
                "from_address":  tx.from_address or "",
                "amount":        tx.amount,
                "confirmations": tx.confirmations,
                "timestamp":     int(time.time()),
            })


async def main():
    seen_store.init_db()
    wallets = config.active_wallets()

    if not wallets:
        print("❌ No wallet addresses configured.")
        print("   Set BTC_ADDRESS / LTC_ADDRESS / ETH_ADDRESS / SOL_ADDRESS in .env")
        return

    print("=" * 50)
    print("  💎 XWALLET Deposit Watcher")
    print("=" * 50)
    for w in wallets:
        print(f"  👁  Watching {w.symbol.upper()}: {w.address}")
    print(f"  ⏱  Poll interval: {config.poll_interval_seconds}s")
    print(f"  🔗 Reporting to: {config.main_bot_url}")
    print("=" * 50)
    print("  Min confirmations required:")
    for w in wallets:
        print(f"     {w.symbol.upper()}: {MIN_CONFIRMATIONS.get(w.symbol, 1)} confirms")
    print("=" * 50)

    async with aiohttp.ClientSession() as session:
        while True:
            await poll_once(session)
            await asyncio.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
