"""
XWALLET — Currency Rules (multi-coin)
Flat 2% fee and ~$0.03 minimum across all 8 supported coins.
Override via .env without touching code.
"""

import os

FEE_PCT     = float(os.getenv("FEE_PCT", "2"))        # % fee, deposit AND withdraw, every coin
MIN_USD     = float(os.getenv("MIN_USD", "0.03"))      # ~$0.03 minimum, every coin
LTC_ADDRESS = os.getenv("LTC_ADDRESS", "SET_YOUR_LTC_ADDRESS_HERE")  # static fallback address


def calc_fee(amount: float) -> float:
    return round((amount or 0) * (FEE_PCT / 100), 8)


def calc_net(amount: float) -> float:
    return round((amount or 0) - calc_fee(amount), 8)


async def min_coin_amount(coin: str) -> float:
    """Minimum amount of `coin` equivalent to MIN_USD, using the live CoinGecko price."""
    from bot.utils.embeds import get_usd_price
    price = await get_usd_price(coin)
    if price <= 0:
        return 0.0001  # safe fallback floor if the price feed is briefly down
    return round(MIN_USD / price, 8)


async def validate_amount(coin: str, amount: float):
    """Returns (ok: bool, message: str)."""
    from bot.utils.coins import is_valid_coin, symbol
    if not is_valid_coin(coin):
        return False, "Unsupported currency."
    if amount is None or amount <= 0:
        return False, "Amount must be greater than zero."
    floor = await min_coin_amount(coin)
    if amount < floor:
        return False, f"Minimum amount is {floor:.8f} {symbol(coin)} (~${MIN_USD:.2f})."
    return True, ""
