"""
XWALLET — Deposit Addresses
Derives addresses from WALLET_MNEMONIC if set, otherwise reads *_ADDRESS env vars.
"""
import os


def get_address(coin: str) -> str:
    """Get deposit address for a coin. Mnemonic derivation takes priority."""
    mn = os.getenv('WALLET_MNEMONIC', '').strip()
    if mn:
        try:
            from bot.wallets.mnemonic import (
                derive_btc_address, derive_ltc_address,
                derive_eth_address, derive_sol_address,
            )
            mapping = {
                'btc':       derive_btc_address,
                'ltc':       derive_ltc_address,
                'eth':       derive_eth_address,
                'sol':       derive_sol_address,
                'usdterc20': derive_eth_address,  # same ETH address
            }
            if coin in mapping:
                return mapping[coin]()
        except Exception:
            pass

    # Fallback to manual env vars
    env_map = {
        'btc':       os.getenv('BTC_ADDRESS', ''),
        'ltc':       os.getenv('LTC_ADDRESS', ''),
        'eth':       os.getenv('ETH_ADDRESS', ''),
        'sol':       os.getenv('SOL_ADDRESS', ''),
        'usdterc20': os.getenv('USDT_ERC20_ADDRESS', ''),
        'usdttrc20': os.getenv('USDT_TRC20_ADDRESS', ''),
    }
    return env_map.get(coin, 'Not configured — contact an admin')


class _Addresses:
    """Dict-style access to deposit addresses."""
    def __getitem__(self, key):
        return get_address(key)

    def get(self, key, default=''):
        val = get_address(key)
        return val if val else default


DEPOSIT_ADDRESSES = _Addresses()
