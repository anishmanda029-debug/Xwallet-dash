"""
XWALLET — ETH Signer
Derives signing key from WALLET_MNEMONIC (m/44'/60'/0'/0/0).
"""
import os, asyncio

def _rpc_url() -> str:
    key = os.getenv('ALCHEMY_API_KEY', '').strip()
    if key:
        net = 'eth-mainnet' if os.getenv('NETWORK', 'mainnet') == 'mainnet' else 'eth-sepolia'
        return f'https://{net}.g.alchemy.com/v2/{key}'
    return 'https://rpc.ankr.com/eth'

async def send_transaction(to_address: str, amount_eth: float) -> str:
    def _send():
        from bot.wallets.mnemonic import get_eth_privkey
        from web3 import Web3
        from eth_account import Account
        privkey = get_eth_privkey()
        acct = Account.from_key(privkey)
        w3 = Web3(Web3.HTTPProvider(_rpc_url(), request_kwargs={'timeout': 30}))
        if not w3.is_connected():
            raise RuntimeError('ETH RPC unreachable')
        nonce = w3.eth.get_transaction_count(acct.address, 'pending')
        value = w3.to_wei(amount_eth, 'ether')
        to = Web3.to_checksum_address(to_address)
        gas = w3.eth.estimate_gas({'from': acct.address, 'to': to, 'value': value})
        tx = {
            'from': acct.address, 'to': to, 'value': value,
            'nonce': nonce, 'gas': gas,
            'gasPrice': w3.eth.gas_price,
            'chainId': w3.eth.chain_id,
        }
        signed = acct.sign_transaction(tx)
        return w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    return await asyncio.get_event_loop().run_in_executor(None, _send)
