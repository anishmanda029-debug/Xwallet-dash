"""
XWALLET — SOL Signer
Derives signing key from WALLET_MNEMONIC (m/44'/501'/0'/0').
"""
import os, asyncio

def _rpc() -> str:
    return ('https://api.mainnet-beta.solana.com'
            if os.getenv('NETWORK', 'mainnet') == 'mainnet'
            else 'https://api.devnet.solana.com')

async def send_transaction(to_address: str, amount_sol: float) -> str:
    def _send():
        from bot.wallets.mnemonic import get_sol_privkey_bytes
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.system_program import transfer, TransferParams
        from solders.transaction import Transaction
        from solders.message import Message
        from solana.rpc.api import Client
        seed_bytes = get_sol_privkey_bytes()
        kp = Keypair.from_seed(seed_bytes)
        client = Client(_rpc())
        lamports = int(round(amount_sol * 1_000_000_000))
        to_pub = Pubkey.from_string(to_address)
        ix = transfer(TransferParams(from_pubkey=kp.pubkey(), to_pubkey=to_pub, lamports=lamports))
        blockhash = client.get_latest_blockhash().value.blockhash
        msg = Message.new_with_blockhash([ix], kp.pubkey(), blockhash)
        tx = Transaction([kp], msg, blockhash)
        resp = client.send_transaction(tx)
        if resp.value is None:
            raise RuntimeError(f'SOL send failed: {resp}')
        return str(resp.value)
    return await asyncio.get_event_loop().run_in_executor(None, _send)
