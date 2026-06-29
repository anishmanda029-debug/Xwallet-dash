"""
XWALLET — BTC Signer
Derives signing key from WALLET_MNEMONIC (m/84'/0'/0'/0/0).
Pure-Python signer (see bot.wallets.segwit_tx) — no bitcoinlib, no native deps,
so it actually installs and runs on Railway/Render.
"""
from bot.wallets.mnemonic import get_btc_privkey_bytes, derive_btc_address
from bot.wallets import segwit_tx


async def send_transaction(to_address: str, amount_btc: float) -> str:
    privkey = get_btc_privkey_bytes()
    from_address = derive_btc_address()
    return await segwit_tx.send("btc", privkey, from_address, to_address, amount_btc)
