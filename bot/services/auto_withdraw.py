"""
XWALLET — Auto-Withdraw Service
Handles automatic coin signing + broadcasting.
Per-coin asyncio lock prevents double-spend/nonce races.
"""

import asyncio
import os
import logging
from typing import Tuple

log = logging.getLogger("XWALLET.auto_withdraw")

# ── Per-coin serialisation locks ──────────────────────────────────────────────
_LOCKS: dict[str, asyncio.Lock] = {
    "btc": asyncio.Lock(),
    "ltc": asyncio.Lock(),
    "eth": asyncio.Lock(),
    "sol": asyncio.Lock(),
}

# ── Daily withdraw limits (USD) — override via env ────────────────────────────
DAILY_LIMIT_USD = float(os.getenv("AUTO_WITHDRAW_DAILY_LIMIT_USD", "500"))
MAX_TX_USD      = float(os.getenv("AUTO_WITHDRAW_MAX_TX_USD", "200"))


async def get_daily_withdrawn_usd(user_id: str) -> float:
    """Sum of automatic withdrawal USD values today for this user."""
    from bot.utils.database import _fetchall  # private helper is fine here
    rows = await _fetchall(
        """SELECT usd_value FROM withdrawals
           WHERE user_id = ?
             AND status IN ('paid', 'approved')
             AND note LIKE '%auto%'
             AND created_at >= to_char(CURRENT_DATE, 'YYYY-MM-DD')""",
        (user_id,),
    )
    return sum(float(r["usd_value"] or 0) for r in rows)


async def check_limits(user_id: str, usd_amount: float) -> Tuple[bool, str]:
    """Returns (ok, error_message). Call BEFORE reserving balance."""
    if usd_amount > MAX_TX_USD:
        return False, f"Single auto-withdrawal limit is ${MAX_TX_USD:,.2f}."
    daily = await get_daily_withdrawn_usd(user_id)
    if daily + usd_amount > DAILY_LIMIT_USD:
        remaining = max(0.0, DAILY_LIMIT_USD - daily)
        return False, f"Daily auto-withdrawal limit is ${DAILY_LIMIT_USD:,.2f}. You have ${remaining:,.2f} remaining today."
    return True, ""


async def _dispatch(coin: str, to_address: str, amount: float) -> str:
    """Route to the correct signer module. Returns TXID."""
    if coin == "btc":
        from bot.wallets.btc_wallet import send_transaction
    elif coin == "ltc":
        from bot.wallets.ltc_wallet import send_transaction
    elif coin == "eth":
        from bot.wallets.eth_wallet import send_transaction
    elif coin == "sol":
        from bot.wallets.sol_wallet import send_transaction
    else:
        raise ValueError(f"No automatic signer for coin: {coin}")
    return await send_transaction(to_address, amount)


async def execute_auto_withdraw(
    coin: str,
    to_address: str,
    amount: float,
    user_id: str,
    wid: int,
) -> str:
    """
    Full automatic withdrawal pipeline, serialised per coin.

    1. Acquire per-coin lock (prevents double-spend)
    2. Reserve balance in DB
    3. Sign + broadcast
    4. On success  → deduct balance, mark withdrawal paid
    5. On failure  → release reserved balance, re-raise

    Returns TXID string.
    """
    from bot.utils.database import update_balance, update_withdrawal_status

    lock = _LOCKS.get(coin)
    if lock is None:
        raise ValueError(f"No lock for coin {coin}. Only BTC/LTC/ETH/SOL support auto-withdraw.")

    async with lock:
        # Reserve funds before signing (prevents race where two requests
        # read the same balance before either deducts)
        await update_balance(user_id, coin, -amount)
        log.info(f"[AUTO_WITHDRAW] Reserved {amount} {coin.upper()} for user {user_id} wid #{wid}")

        try:
            txid = await _dispatch(coin, to_address, amount)
        except Exception as exc:
            # Roll back reservation — balance not deducted
            await update_balance(user_id, coin, +amount)
            log.error(f"[AUTO_WITHDRAW] Broadcast failed for wid #{wid}: {exc}")
            raise

        await update_withdrawal_status(
            wid, "paid",
            f"auto broadcast txid:{txid}",
            handled_by="BOT_AUTO",
        )
        log.info(f"[AUTO_WITHDRAW] SUCCESS wid #{wid} txid:{txid}")
        return txid
