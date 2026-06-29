"""
Config for the standalone watcher process. Run separately from the main
bot (different machine, or just a second process) — see watcher/README.md.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _get_required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


@dataclass
class WalletConfig:
    symbol: str       # internal coin code used by XWALLET, e.g. 'ltc', 'usdterc20'
    address: str


def _derived_or_env(symbol: str, env_key: str) -> str:
    """Prefer mnemonic-derived address (same as the bot/dashboard use); fall back to explicit env var."""
    mn = os.getenv("WALLET_MNEMONIC", "").strip()
    if mn:
        try:
            from bot.wallets import mnemonic as _mn
            fn = {
                "btc": _mn.derive_btc_address,
                "ltc": _mn.derive_ltc_address,
                "eth": _mn.derive_eth_address,
                "sol": _mn.derive_sol_address,
            }.get(symbol)
            if fn:
                addr = fn()
                if addr:
                    return addr
        except Exception:
            pass
    return os.getenv(env_key, "")


@dataclass
class WatcherConfig:
    main_bot_url: str = field(default_factory=lambda: _get_required("MAIN_BOT_URL"))
    shared_secret: str = field(
        default_factory=lambda: os.getenv("WATCHER_SHARED_SECRET") or _get_required("SHARED_SECRET")
    )

    btc_address: str = field(default_factory=lambda: _derived_or_env("btc", "BTC_ADDRESS"))
    ltc_address: str = field(default_factory=lambda: _derived_or_env("ltc", "LTC_ADDRESS"))
    eth_address: str = field(default_factory=lambda: _derived_or_env("eth", "ETH_ADDRESS"))
    sol_address: str = field(default_factory=lambda: _derived_or_env("sol", "SOL_ADDRESS"))
    usdt_erc20_address: str = field(default_factory=lambda: os.getenv("USDT_ERC20_ADDRESS", ""))
    usdt_trc20_address: str = field(default_factory=lambda: os.getenv("USDT_TRC20_ADDRESS", ""))

    poll_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    )

    def active_wallets(self) -> list[WalletConfig]:
        wallets = []
        if self.btc_address:
            wallets.append(WalletConfig("btc", self.btc_address))
        if self.ltc_address:
            wallets.append(WalletConfig("ltc", self.ltc_address))
        if self.eth_address:
            wallets.append(WalletConfig("eth", self.eth_address))
        if self.sol_address:
            wallets.append(WalletConfig("sol", self.sol_address))
        if self.usdt_erc20_address:
            wallets.append(WalletConfig("usdterc20", self.usdt_erc20_address))
        if self.usdt_trc20_address:
            wallets.append(WalletConfig("usdttrc20", self.usdt_trc20_address))
        return wallets


config = WatcherConfig()
