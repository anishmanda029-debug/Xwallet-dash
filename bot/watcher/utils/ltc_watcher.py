"""
Litecoin watcher — polls BlockCypher's free public API.
Docs: https://www.blockcypher.com/dev/litecoin/
No API key required for light usage (3 req/sec, 200 req/hr token-free).
"""
import aiohttp
from dataclasses import dataclass


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None
    amount: float            # in whole LTC
    confirmations: int


async def get_new_incoming(address: str, confirmed_only: bool = True) -> list[IncomingTx]:
    """Returns transactions that paid INTO `address`."""
    url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/full"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    results = []
    for tx in data.get("txs", []):
        confirmations = tx.get("confirmations", 0)
        if confirmed_only and confirmations < 1:
            continue

        received = 0
        for out in tx.get("outputs", []):
            if address in (out.get("addresses") or []):
                received += out.get("value", 0)
        if received <= 0:
            continue

        from_address = None
        inputs = tx.get("inputs", [])
        if inputs and inputs[0].get("addresses"):
            from_address = inputs[0]["addresses"][0]

        results.append(IncomingTx(
            tx_hash=tx.get("hash", ""),
            from_address=from_address,
            amount=received / 1e8,  # litoshi -> LTC
            confirmations=confirmations,
        ))

    return results
