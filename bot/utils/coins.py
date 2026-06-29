"""
XWALLET — Supported Currencies Registry
Single source of truth for every coin XWALLET accepts. Add/remove a coin
here and it propagates everywhere (balance display, deposit, withdraw,
admin commands, dashboard, watcher) without touching other files.

`code`           — internal key, also the watcher's payload `coin` field
`label`          — human-readable name
`symbol`         — short ticker shown in UI
`coingecko_id`   — for live USD pricing
`decimals`       — display precision
`address_hint`   — placeholder example shown in withdraw modal
`watcher_tracked`— True if the standalone watcher auto-detects this coin
"""

COINS = {
    "btc":       {"label": "Bitcoin",        "symbol": "BTC",  "coingecko_id": "bitcoin",  "decimals": 8, "address_hint": "bc1q… / 1… / 3…",          "watcher_tracked": True},
    "ltc":       {"label": "Litecoin",       "symbol": "LTC",  "coingecko_id": "litecoin", "decimals": 8, "address_hint": "ltc1q… / L… / M…",         "watcher_tracked": True},
    "sol":       {"label": "Solana",         "symbol": "SOL",  "coingecko_id": "solana",   "decimals": 6, "address_hint": "Base58 address",           "watcher_tracked": True},
    "eth":       {"label": "Ethereum",       "symbol": "ETH",  "coingecko_id": "ethereum", "decimals": 6, "address_hint": "0x…",                      "watcher_tracked": True},
    "usdterc20": {"label": "USDT (ERC20)",   "symbol": "USDT", "coingecko_id": "tether",   "decimals": 2, "address_hint": "0x… (Ethereum address)",   "watcher_tracked": True},
    "usdttrc20": {"label": "USDT (TRC20)",   "symbol": "USDT", "coingecko_id": "tether",   "decimals": 2, "address_hint": "T… (Tron address)",        "watcher_tracked": True},
}

ORDER = ["btc", "ltc", "sol", "eth", "usdterc20", "usdttrc20"]


def is_valid_coin(code: str) -> bool:
    return code in COINS


def label(code: str) -> str:
    return COINS.get(code, {}).get("label", code.upper())


def symbol(code: str) -> str:
    return COINS.get(code, {}).get("symbol", code.upper())


def decimals(code: str) -> int:
    return COINS.get(code, {}).get("decimals", 8)


def coingecko_id(code: str) -> str:
    return COINS.get(code, {}).get("coingecko_id", "")


def address_hint(code: str) -> str:
    return COINS.get(code, {}).get("address_hint", "Enter address")


def is_watcher_tracked(code: str) -> bool:
    return COINS.get(code, {}).get("watcher_tracked", False)


def balance_column(code: str) -> str:
    """Column name in the user_balances table — same as the coin code."""
    return code
