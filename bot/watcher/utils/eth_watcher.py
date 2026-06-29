"""
Ethereum watcher — polls Etherscan's free API.
Needs a free API key from https://etherscan.io/apis (generous free tier,
5 req/sec). Set ETHERSCAN_API_KEY in .env.
"""
import os
import aiohttp
from dataclasses import dataclass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None
    amount: float          # in ETH
    confirmations: int


async def get_new_incoming(address: str, confirmed_only: bool = True) -> list[IncomingTx]:
    if not ETHERSCAN_API_KEY:
        return []  # silently skip if not configured

    url = (
        "https://api.etherscan.io/api"
        f"?module=account&action=txlist&address={address}"
        f"&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    if data.get("status") != "1":
        return []

    results = []
    for tx in data.get("result", [])[:50]:  # only check recent 50
        # Only incoming (to == our address), value > 0, and not an error tx
        if tx.get("to", "").lower() != address.lower():
            continue
        if tx.get("isError") == "1":
            continue
        value_wei = int(tx.get("value", "0"))
        if value_wei <= 0:
            continue

        confirmations = int(tx.get("confirmations", "0"))
        if confirmed_only and confirmations < 1:
            continue

        results.append(IncomingTx(
            tx_hash=tx["hash"],
            from_address=tx.get("from"),
            amount=value_wei / 1e18,  # wei -> ETH
            confirmations=confirmations,
        ))

    return results
