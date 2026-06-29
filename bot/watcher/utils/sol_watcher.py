"""
Solana watcher — polls the public Solana RPC endpoint directly.
Free, no API key needed, but rate-limited (~100 req/10s on the public
endpoint) — fine for a single wallet polled every 30s.
"""
import aiohttp
from dataclasses import dataclass

RPC_URL = "https://api.mainnet-beta.solana.com"


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str | None
    amount: float          # in SOL
    confirmations: int     # we just use 1 if finalized, 0 otherwise


async def _rpc(session: aiohttp.ClientSession, method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        data = await resp.json()
        return data.get("result")


async def get_new_incoming(address: str, confirmed_only: bool = True, limit: int = 20) -> list[IncomingTx]:
    async with aiohttp.ClientSession() as session:
        signatures = await _rpc(
            session, "getSignaturesForAddress", [address, {"limit": limit}]
        )
        if not signatures:
            return []

        results = []
        for sig_info in signatures:
            if confirmed_only and sig_info.get("confirmationStatus") != "finalized":
                continue
            if sig_info.get("err") is not None:
                continue  # failed tx

            tx_data = await _rpc(
                session,
                "getTransaction",
                [sig_info["signature"], {"maxSupportedTransactionVersion": 0}],
            )
            if not tx_data:
                continue

            meta = tx_data.get("meta", {})
            account_keys = tx_data["transaction"]["message"]["accountKeys"]
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])

            try:
                idx = [str(k) if isinstance(k, str) else k.get("pubkey")
                       for k in account_keys].index(address)
            except ValueError:
                continue

            delta_lamports = post_balances[idx] - pre_balances[idx]
            if delta_lamports <= 0:
                continue  # not a receive for us

            # best-effort sender = first account that lost balance
            from_address = None
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                if i == idx:
                    continue
                if pre - post > 0:
                    key = account_keys[i]
                    from_address = key if isinstance(key, str) else key.get("pubkey")
                    break

            results.append(IncomingTx(
                tx_hash=sig_info["signature"],
                from_address=from_address,
                amount=delta_lamports / 1e9,  # lamports -> SOL
                confirmations=1,
            ))

        return results
