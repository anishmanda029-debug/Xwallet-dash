"""
XWALLET — Full Emoji Pack & Embed Helpers
Multi-coin crypto wallet (BTC, LTC, SOL, ETH, USDT, DOGE, TRX).
Live prices via CoinGecko (no API key). Clean minimal embed style —
emojis are used only where they add real meaning, never decoratively.
"""

import discord
from datetime import datetime
import os
import time

# ── XWALLET EMOJI PACK (real IDs) ────────────────────────────────────────────
E = {
    "loading":      "<a:loading:1518238768094511245>",

    "xwallet":      "<:xwallet:1518235073990889533>",
    "invoice":      "<:invoice:1518232907020238929>",
    "ticket":       "<:ticket:1518232973210550323>",
    "broadcast":    "<:broadcast:1518232426655256687>",
    "server":       "<:server:1518232336997679104>",
    "arrow2":       "<:arrow2:1518232259583279235>",
    "payment":      "<:payment:1518232185000165467>",
    "history":      "<:history:1518232105706852602>",
    "dm":           "<:dm:1518232029064331385>",

    "authorized":   "<:authorized:1518231834817855680>",
    "gift":         "<:gift:1518231617460502528>",
    "secure":       "<:secure:1518231483469267064>",
    "deposit":      "<:deposit:1518223323094454423>",
    "withdraw":     "<:withdraw:1518223568981463171>",
    "tick":         "<:success:1518222850538864671>",

    "arrow1":       "<:arrow1:1518233614792392926>",
    "debug":        "<:debug:1518233547515887636>",
    "task":         "<:task:1518233477114368131>",
    "admin":        "<:admin:1518233374165041232>",
    "address":      "<:address:1518233237972062208>",
    "time":         "<:time:1518233147370770452>",
    "rain":         "<:rain:1518233063182569542>",
    "id":           "<:id:1518232510595727402>",
    "notify":       "<:notify:1518232563741884496>",
    "owner":        "<:owner:1518232628128518154>",
    "balance":      "<:balance:1518232688970961027>",
    "qr":           "<:qr:1518232762539184139>",
    "error":        "<:error:1518232832793776148>",
}

# ── Legacy key aliases — map old internal names onto the new real set ───────
_ALIASES = {
    "announcement": "notify",
    "green_tick":   "tick",
    "unlock":       "secure",
    "lock":         "secure",
    "members":      "id",
    "action":       "admin",
    "shop":         "balance",
    "dollars":      "payment",
    "inr":          "payment",
    "staff":        "admin",
    "mute":         "time",
    "cart":         "balance",
    "declined":     "error",
    "next":         "arrow2",
    "call":         "dm",
    "dollar":       "payment",
    "spotify":      "balance",
    "code":         "qr",
    "pause":        "time",
    "boost":        "gift",
    "premium":      "xwallet",
    "mail":         "dm",
    "form":         "history",
    "private":      "secure",
    "hide":         "secure",
    "like":         "tick",
    "good":         "tick",
    "dislike":      "error",
    "bad":          "error",
    "link":         "qr",
    "card":         "balance",
    "blue_tick":    "tick",
    "edit":         "admin",
    "website":      "qr",
    "unhide":       "qr",
    "idle":         "time",
    "dnd":          "time",
    "tag":          "history",
    "accept":       "tick",
    "mod":          "admin",
    "nitro":        "gift",
    "security":     "secure",
    "warning":      "error",
    "pending":      "time",
    "giveaway":     "gift",
    "wallet":       "balance",
    "profile":      "id",
    "price":        "balance",
    "help":         "history",
    "invite":       "dm",
    "settings":     "admin",
    "export":       "history",
    "import":       "history",
    "diamond":      "xwallet",
    "gold":         "xwallet",
    "ltc":          "balance",  # coin emojis handled via coin_emoji()
}
for alias, target in _ALIASES.items():
    E[alias] = E[target]

# Explicitly ensure these always exist (some are used in withdraw.py confirm embeds)
E.setdefault("declined", E["error"])
E.setdefault("pause",    E["time"])
E.setdefault("profile",  E["id"])

# Per-coin emoji — your custom emojis
COIN_EMOJI = {
    "btc":       "<:btc:1518245013052461097>",
    "ltc":       "<:ltc:1518244865870139552>",
    "sol":       "<:sol:1518244931590815866>",
    "eth":       "<:eth:1518244898833432737>",
    "usdterc20": "<:usdt:1518244976981573704>",
    "usdttrc20": "<:usdt:1518244976981573704>",
}

def coin_emoji(code: str) -> str:
    return COIN_EMOJI.get(code, E["payment"])

# ── DECORATIVE SYMBOLS (used very sparingly — accents, not spam) ───────────
S = {
    "dot":     "𑣲",
    "star":    "⋆",
    "bullet":  "▸",
    "double":  "»",
    "premium": "ᯓ★",
    "plus":    "➕",
    "money":   "$",
    "swap":    "💱",
    "card":    "💳",
    "rupee":   "₨",
}

DIV = "━━━━━━━━━━━━━━━━━━━━"

COLOR = {
    "primary":    0x5865F2,
    "success":    0x2ECC71,
    "error":      0xE74C3C,
    "warning":    0xF39C12,
    "info":       0x3498DB,
    "processing": 0x9B59B6,
    "gold":       0xF1C40F,
    "dark":       0x2C2F33,
}


# ── LIVE PRICES — all 8 coins, one batched CoinGecko call, cached 60s ───────
_price_cache = {"prices": {}, "ts": 0.0}

async def get_all_usd_prices() -> dict:
    """Returns {coin_code: usd_price} for every supported coin, e.g. {'btc': 67000.0, ...}."""
    from bot.utils.coins import COINS
    now = time.time()
    if _price_cache["prices"] and (now - _price_cache["ts"]) < 60:
        return _price_cache["prices"]
    gecko_ids = sorted(set(c["coingecko_id"] for c in COINS.values()))
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(gecko_ids), "vs_currencies": "usd"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {}
                    for code, info in COINS.items():
                        gid = info["coingecko_id"]
                        price = float(data.get(gid, {}).get("usd", 0) or 0)
                        if price > 0:
                            result[code] = price
                    if result:
                        _price_cache["prices"] = result
                        _price_cache["ts"] = now
                        return result
    except Exception:
        pass
    return _price_cache["prices"] or {}


async def get_usd_price(coin: str) -> float:
    prices = await get_all_usd_prices()
    return prices.get(coin, 0.0)

# Backward-compatible alias used by a couple of older call sites
async def get_ltc_usd_price() -> float:
    return await get_usd_price("ltc")


def fmt_coin(amount: float, coin: str) -> str:
    from bot.utils.coins import symbol, decimals
    d = decimals(coin)
    return f"`{(amount or 0):.{d}f} {symbol(coin)}`"

def fmt_usd(amount: float) -> str:
    return f"`${(amount or 0):,.2f}`"

# Backward-compatible alias
def fmt_ltc(amount: float) -> str:
    return fmt_coin(amount, "ltc")


async def coin_to_usd_str(amount: float, coin: str) -> str:
    price = await get_usd_price(coin)
    if price <= 0:
        return "`$-.-- (price unavailable)`"
    return fmt_usd((amount or 0) * price)

# Backward-compatible alias
async def ltc_to_usd_str(ltc_amount: float) -> str:
    return await coin_to_usd_str(ltc_amount, "ltc")


async def wallet_block(balance: float, coin: str, label: str = "Available") -> str:
    from bot.utils.coins import label as coin_label
    usd_line = await coin_to_usd_str(balance, coin)
    return f"{E['ltc']} **{label} ({coin_label(coin)})** {S['bullet']} {fmt_coin(balance, coin)} {S['swap']} {usd_line}"


async def full_wallet_block(balances: dict, label: str = "Available", hide_zero: bool = False) -> str:
    """Smart wallet block: only shows coins with a balance.
    Coins at zero are hidden. If nothing is held, prompts to deposit."""
    from bot.utils.coins import ORDER, symbol
    prices = await get_all_usd_prices()
    lines = []
    for coin in ORDER:
        amt = balances.get(coin, 0.0) or 0.0
        if amt <= 0.0:
            continue  # always hide zero-balance coins
        price = prices.get(coin, 0.0)
        usd = f"{S['swap']} {fmt_usd(amt * price)}" if price > 0 else ""
        lines.append(f"{coin_emoji(coin)} **{symbol(coin)}** {S['bullet']} {fmt_coin(amt, coin)} {usd}")
    if not lines:
        return (
            f"{E['deposit']} **No coins in wallet yet.**\n"
            f"{E['arrow1']} Use `/deposit` or `$depo` to add funds."
        )
    return "\n".join(lines)


async def smart_wallet_embed(target: discord.Member, balances: dict) -> discord.Embed:
    """Returns a wallet embed that only shows coins with balance + a ❌ close button hint."""
    from bot.utils.coins import ORDER
    prices = await get_all_usd_prices()
    avail = {c: (balances.get(c, {}).get("balance", 0) or 0) for c in ORDER}
    hold  = {c: (balances.get(c, {}).get("hold",    0) or 0) for c in ORDER}

    wallet_text = await full_wallet_block(avail, "Available")
    total_usd   = sum(avail.get(c, 0) * prices.get(c, 0) for c in ORDER)
    hold_usd    = sum(hold.get(c, 0)  * prices.get(c, 0) for c in ORDER)

    desc = f"{DIV}\n{wallet_text}\n{DIV}\n"
    desc += f"{E['diamond']} **Total Available** {S['bullet']} {fmt_usd(total_usd)}\n"
    if hold_usd > 0:
        desc += f"{E['secure']} **On Hold** {S['bullet']} {fmt_usd(hold_usd)}\n"
    desc += DIV

    em = discord.Embed(
        title=f"{E['wallet']} Wallet — {target.display_name}",
        description=desc,
        color=COLOR["primary"],
    )
    em.set_thumbnail(url=target.display_avatar.url)
    em.set_footer(text="XWALLET • Press ✕ to close this message")
    return em


def embed_success(title: str, description: str = "", footer: str = "") -> discord.Embed:
    e = discord.Embed(
        title=f"{E['tick']} {title}",
        description=description or None,
        color=COLOR["success"],
        timestamp=datetime.utcnow(),
    )
    if footer:
        e.set_footer(text=footer)
    return e

def embed_error(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(
        title=f"{E['error']} {title}",
        description=description or None,
        color=COLOR["error"],
        timestamp=datetime.utcnow(),
    )

def embed_info(title: str, description: str = "", footer: str = "") -> discord.Embed:
    e = discord.Embed(
        title=f"{E['announcement']} {title}",
        description=description or None,
        color=COLOR["primary"],
        timestamp=datetime.utcnow(),
    )
    if footer:
        e.set_footer(text=footer)
    return e

def embed_processing(title: str = "Processing…") -> discord.Embed:
    return discord.Embed(
        title=f"{E['loading']} {title}",
        description=f"{DIV}\nPlease wait a moment…\n{DIV}",
        color=COLOR["processing"],
    )

def embed_warning(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(
        title=f"{E['mute']} {title}",
        description=description or None,
        color=COLOR["warning"],
        timestamp=datetime.utcnow(),
    )
