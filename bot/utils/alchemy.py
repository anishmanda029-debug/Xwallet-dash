"""
Alchemy integration — two SEPARATE, deliberately limited responsibilities:

1. Deposit detection (read-only): verifying the x-alchemy-signature header
   on incoming Address Activity webhooks. See dashboard/app.py's
   /webhooks/alchemy route for the actual receiver.

2. Withdrawal broadcasting (NOT signing): build an UNSIGNED transaction
   request for a pending withdrawal, so an authorised member can sign it
   on their own machine (with a key that never touches this bot or
   server) and then have Alchemy broadcast the already-signed raw tx.

This module never holds, generates, or touches a private key. If you're
looking for "auto-send crypto on approval," that's intentionally not here.
"""

import os
import aiohttp

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")

NETWORK_URLS = {
    "eth":       f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
    "usdterc20": f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}",
}


def is_configured() -> bool:
    return bool(ALCHEMY_API_KEY)


async def build_unsigned_tx(coin: str, from_address: str, to_address: str, amount: float) -> dict | None:
    """
    Returns the pieces needed to construct + sign a transaction OFF this
    server: current nonce, gas price estimate, and chain id. The actual
    signing must happen wherever you keep your key (hardware wallet,
    local signer script, etc) — this never sees or needs the private key.
    """
    url = NETWORK_URLS.get(coin)
    if not url or not ALCHEMY_API_KEY:
        return None

    async with aiohttp.ClientSession() as session:
        nonce_resp = await session.post(url, json={
            "jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionCount",
            "params": [from_address, "pending"]
        })
        gas_resp = await session.post(url, json={
            "jsonrpc": "2.0", "id": 2, "method": "eth_gasPrice", "params": []
        })
        chain_resp = await session.post(url, json={
            "jsonrpc": "2.0", "id": 3, "method": "eth_chainId", "params": []
        })
        nonce_data = await nonce_resp.json()
        gas_data = await gas_resp.json()
        chain_data = await chain_resp.json()

    if "result" not in nonce_data or "result" not in gas_data:
        return None

    return {
        "from": from_address,
        "to": to_address,
        "value_eth": amount,
        "nonce": int(nonce_data["result"], 16),
        "gas_price_wei": int(gas_data["result"], 16),
        "chain_id": int(chain_data.get("result", "0x1"), 16),
        "note": "Sign this OFF this server with your own key, then submit the raw signed tx via /broadcast or eth_sendRawTransaction.",
    }


async def broadcast_signed_tx(coin: str, signed_raw_tx_hex: str) -> dict | None:
    """Takes an ALREADY-SIGNED raw transaction (hex, 0x...) and broadcasts
    it via Alchemy. The bot never produces this — you (or your local signer
    script) do, then paste/POST the result here."""
    url = NETWORK_URLS.get(coin)
    if not url or not ALCHEMY_API_KEY:
        return None

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={
            "jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
            "params": [signed_raw_tx_hex]
        }) as resp:
            data = await resp.json()
            return data
