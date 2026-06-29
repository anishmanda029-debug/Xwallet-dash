"""
XWALLET — LTC Signer
Derives signing key from WALLET_MNEMONIC (m/84'/2'/0'/0/0).
Pure-Python signer (see bot.wallets.segwit_tx) — no bitcoinlib, no native deps,
so it actually installs and runs on Railway/Render.
"""
from bot.wallets.mnemonic import get_ltc_privkey_bytes, derive_ltc_address
from bot.wallets import segwit_tx


async def send_transaction(to_address: str, amount_ltc: float) -> str:
    privkey = get_ltc_privkey_bytes()
    from_address = derive_ltc_address()
    return await segwit_tx.send("ltc", privkey, from_address, to_address, amount_ltc)
