"""
USDT (ERC20, Ethereum) watcher — polls Etherscan's token-transfer API.
Needs the same free ETHERSCAN_API_KEY as eth_watcher.py.
USDT contract: 0xdAC17F958D2ee523a2206206994597C13D831ec (6 decimals).
"""
import os
import aiohttp
from dataclasses import dataclass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
USDT_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec"
USDT_DECIMALS = 6


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None
    amount: float
    confirmations: int


async def get_new_incoming(address: str, confirmed_only: bool = True) -> list[IncomingTx]:
    if not ETHERSCAN_API_KEY:
        return []

    url = (
        "https://api.etherscan.io/api"
        f"?module=account&action=tokentx&contractaddress={USDT_CONTRACT}"
        f"&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    if data.get("status") != "1":
        return []

    results = []
    for tx in data.get("result", [])[:50]:
        if tx.get("to", "").lower() != address.lower():
            continue
        value_raw = int(tx.get("value", "0"))
        if value_raw <= 0:
            continue

        confirmations = int(tx.get("confirmations", "0"))
        if confirmed_only and confirmations < 1:
            continue

        results.append(IncomingTx(
            tx_hash=tx["hash"],
            from_address=tx.get("from"),
            amount=value_raw / (10 ** USDT_DECIMALS),
            confirmations=confirmations,
        ))

    return results
