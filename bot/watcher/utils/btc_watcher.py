"""
Bitcoin watcher — polls Blockstream's free public esplora API.
Docs: https://github.com/Blockstream/esplora/blob/master/API.md

No API key needed. Rate limits are generous for personal use.
"""
import aiohttp
from dataclasses import dataclass


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None   # may be None if we can't determine sender cleanly
    amount: float              # in whole coin units (BTC, not sats)
    confirmations: int


async def get_new_incoming(address: str, confirmed_only: bool = True) -> list[IncomingTx]:
    """
    Returns transactions that paid INTO `address`.
    For BTC, "sender" is ambiguous (multiple inputs possible) — we take the
    first input's previous-output address as a best-effort sender.
    """
    url = f"https://blockstream.info/api/address/{address}/txs"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            txs = await resp.json()

    # Get current block height for confirmation counting
    tip_height = None
    if confirmed_only:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://blockstream.info/api/blocks/tip/height") as resp:
                if resp.status == 200:
                    tip_height = int(await resp.text())

    results = []
    for tx in txs:
        # Sum outputs that pay to our address
        received = sum(
            vout["value"] for vout in tx.get("vout", [])
            if vout.get("scriptpubkey_address") == address
        )
        if received <= 0:
            continue

        status = tx.get("status", {})
        confirmed = status.get("confirmed", False)
        if confirmed_only and not confirmed:
            continue

        confirmations = 0
        if confirmed and tip_height and status.get("block_height"):
            confirmations = tip_height - status["block_height"] + 1

        # Best-effort sender: first input's prevout address
        from_address = None
        vins = tx.get("vin", [])
        if vins and vins[0].get("prevout"):
            from_address = vins[0]["prevout"].get("scriptpubkey_address")

        results.append(IncomingTx(
            tx_hash=tx["txid"],
            from_address=from_address,
            amount=received / 1e8,  # sats -> BTC
            confirmations=confirmations,
        ))

    return results
