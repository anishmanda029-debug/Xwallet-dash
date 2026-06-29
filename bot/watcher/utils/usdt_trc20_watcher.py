"""
USDT (TRC20, Tron) watcher — polls TronGrid's free public API.
No API key strictly required for light use, but a free one from
https://www.trongrid.io raises rate limits a lot — set TRONGRID_API_KEY.
USDT contract: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t (6 decimals).
"""
import os
import aiohttp
from dataclasses import dataclass

TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "")
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_DECIMALS = 6


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None
    amount: float
    confirmations: int


async def get_new_incoming(address: str, confirmed_only: bool = True) -> list[IncomingTx]:
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
    params = {"limit": 50, "contract_address": USDT_CONTRACT, "only_to": "true"}
    headers = {"TRON-PRO-API-KEY": TRONGRID_API_KEY} if TRONGRID_API_KEY else {}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    results = []
    for tx in data.get("data", []):
        if tx.get("to", "").lower() != address.lower():
            continue
        value_raw = int(tx.get("value", "0"))
        if value_raw <= 0:
            continue

        # TronGrid's trc20 endpoint only returns confirmed transfers,
        # so treat anything returned here as confirmed (confirmations=1).
        results.append(IncomingTx(
            tx_hash=tx.get("transaction_id", ""),
            from_address=tx.get("from"),
            amount=value_raw / (10 ** USDT_DECIMALS),
            confirmations=1,
        ))

    return results
