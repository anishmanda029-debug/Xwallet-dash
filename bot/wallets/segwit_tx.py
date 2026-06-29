"""
XWALLET — Pure-Python Native-Segwit (P2WPKH) Signer
====================================================
Builds, signs (BIP143), and broadcasts BTC/LTC transactions WITHOUT bitcoinlib.

Why: bitcoinlib pulls in heavy/native build deps that consistently fail to
install on Railway/Render's Nixpacks build (confirmed in this project's own
deploy logs). This module only needs stdlib + requests (already a hard
dependency), and reuses the secp256k1 point-math already implemented in
bot.wallets.mnemonic — so it works anywhere the bot itself works.

UTXO source + broadcast: BlockCypher (same provider already used by the
deposit watcher — no API key required for BTC/LTC on the free tier).
"""

import hashlib
import os
import struct
import requests

from bot.wallets.mnemonic import (
    _P, _N, _Gx, _Gy, _point_mul, _pub_compressed, _hash160, _bech32_encode,
)

BLOCKCYPHER_COIN = {"btc": "btc", "ltc": "ltc"}
DUST_THRESHOLD_SATS = 1000  # below this, change is added to the fee instead of a new output


# ── helpers ────────────────────────────────────────────────────────────────

def _dsha256(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def _varint(n: int) -> bytes:
    if n < 0xfd:
        return n.to_bytes(1, 'little')
    if n <= 0xffff:
        return b'\xfd' + n.to_bytes(2, 'little')
    if n <= 0xffffffff:
        return b'\xfe' + n.to_bytes(4, 'little')
    return b'\xff' + n.to_bytes(8, 'little')


def _push(data: bytes) -> bytes:
    """Script push: length-prefixed data (used for witness items)."""
    return _varint(len(data)) + data


def _der_encode_sig(r: int, s: int) -> bytes:
    def _enc_int(x: int) -> bytes:
        b = x.to_bytes((x.bit_length() + 7) // 8 or 1, 'big')
        if b[0] & 0x80:
            b = b'\x00' + b
        return b
    rb, sb = _enc_int(r), _enc_int(s)
    body = b'\x02' + len(rb).to_bytes(1, 'big') + rb + b'\x02' + len(sb).to_bytes(1, 'big') + sb
    return b'\x30' + len(body).to_bytes(1, 'big') + body


def _ecdsa_sign(msg_hash: bytes, privkey: bytes) -> bytes:
    """Sign a 32-byte hash with secp256k1, low-S, DER-encoded. Returns DER sig (no sighash byte)."""
    z = int.from_bytes(msg_hash, 'big')
    d = int.from_bytes(privkey, 'big')
    while True:
        k = int.from_bytes(os.urandom(32), 'big') % _N
        if k == 0:
            continue
        R = _point_mul(k, (_Gx, _Gy))
        r = R[0] % _N
        if r == 0:
            continue
        k_inv = pow(k, _N - 2, _N)
        s = (k_inv * (z + r * d)) % _N
        if s == 0:
            continue
        if s > _N // 2:
            s = _N - s
        return _der_encode_sig(r, s)


# ── BlockCypher I/O ──────────────────────────────────────────────────────────

def _bc_fetch_utxos(coin: str, address: str) -> list:
    coinpath = BLOCKCYPHER_COIN[coin]
    url = f"https://api.blockcypher.com/v1/{coinpath}/main/addrs/{address}?unspentOnly=true&includeScript=false&limit=2000"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    utxos = []
    for tx in data.get("txrefs", []) + data.get("unconfirmed_txrefs", []):
        utxos.append({
            "txid": tx["tx_hash"],
            "vout": tx["tx_output_n"],
            "value": tx["value"],
            "confirmations": tx.get("confirmations", 0),
        })
    return utxos


def _bc_fee_rate_sat_vb(coin: str) -> int:
    """Recommended fee rate in sat/vbyte. Falls back to a safe default on error."""
    defaults = {"btc": 15, "ltc": 30}
    try:
        coinpath = BLOCKCYPHER_COIN[coin]
        r = requests.get(f"https://api.blockcypher.com/v1/{coinpath}/main", timeout=15)
        r.raise_for_status()
        kb = r.json().get("medium_fee_per_kb")
        if kb:
            return max(1, round(kb / 1000))
    except Exception:
        pass
    return defaults.get(coin, 20)


def _bc_broadcast(coin: str, raw_hex: str) -> str:
    coinpath = BLOCKCYPHER_COIN[coin]
    url = f"https://api.blockcypher.com/v1/{coinpath}/main/txs/push"
    r = requests.post(url, json={"tx": raw_hex}, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"BlockCypher broadcast failed ({r.status_code}): {r.text[:300]}")
    return r.json()["tx"]["hash"]


# ── address decode (bech32 P2WPKH -> 20 byte hash) ───────────────────────────

_B32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'


def _bech32_decode_witprog(address: str) -> bytes:
    addr = address.lower()
    pos = addr.rfind('1')
    if pos < 1:
        raise ValueError(f"Not a valid bech32 address: {address}")
    data_part = addr[pos + 1:]
    values = [_B32_CHARSET.index(c) for c in data_part]
    data5 = values[:-6]  # strip checksum
    witver = data5[0]
    prog5 = data5[1:]
    acc, bits, out = 0, 0, []
    for v in prog5:
        acc = (acc << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xff)
    return bytes(out)


def _p2wpkh_script(hash160_bytes: bytes) -> bytes:
    """scriptPubKey for native segwit P2WPKH: OP_0 <20-byte-hash>."""
    return b'\x00\x14' + hash160_bytes


# ── core tx build/sign ───────────────────────────────────────────────────────

def _estimate_vsize(n_in: int, n_out: int) -> int:
    base = 4 + 1 + 1 + 4 + n_in * (32 + 4 + 1 + 4) + n_out * (8 + 1 + 22)
    witness = 2 + n_in * (1 + 1 + 72 + 1 + 33)
    weight = base * 4 + witness
    return -(-weight // 4)  # ceil


def build_and_sign(coin: str, privkey: bytes, from_address: str, to_address: str, amount_sats: int) -> str:
    """
    Build + sign a single-key P2WPKH transaction spending from_address's UTXOs.
    Change (if any, above dust) returns to from_address. Returns raw tx hex.
    """
    pub = _pub_compressed(privkey)
    from_hash160 = _hash160(pub)
    # BIP143 scriptCode for P2WPKH = the classic P2PKH script (NOT the witness
    # program). Using the witness-program scriptPubKey here would silently
    # produce an invalid signature that nodes reject.
    p2pkh_equiv = b'\x76\xa9\x14' + from_hash160 + b'\x88\xac'
    script_code = _varint(len(p2pkh_equiv)) + p2pkh_equiv

    utxos = _bc_fetch_utxos(coin, from_address)
    utxos = [u for u in utxos if u["confirmations"] >= 1]
    utxos.sort(key=lambda u: u["value"], reverse=True)
    if not utxos:
        raise RuntimeError(f"No spendable {coin.upper()} UTXOs found for {from_address}")

    fee_rate = _bc_fee_rate_sat_vb(coin)
    to_witprog = _bech32_decode_witprog(to_address)

    chosen, total_in = [], 0
    fee = 0
    for u in utxos:
        chosen.append(u)
        total_in += u["value"]
        n_out_guess = 2
        fee = _estimate_vsize(len(chosen), n_out_guess) * fee_rate
        if total_in >= amount_sats + fee:
            break
    if total_in < amount_sats + fee:
        raise RuntimeError(
            f"Insufficient {coin.upper()} balance: have {total_in} sats, need {amount_sats + fee} sats (incl. fee)"
        )

    change = total_in - amount_sats - fee
    outputs = [(amount_sats, _p2wpkh_script(to_witprog))]
    if change > DUST_THRESHOLD_SATS:
        outputs.append((change, _p2wpkh_script(from_hash160)))
    else:
        fee += change  # donate dust to the fee
        change = 0

    version = (2).to_bytes(4, 'little')
    locktime = (0).to_bytes(4, 'little')
    sequence = b'\xff\xff\xff\xff'

    prevouts = b''.join(bytes.fromhex(u["txid"])[::-1] + u["vout"].to_bytes(4, 'little') for u in chosen)
    sequences = sequence * len(chosen)
    hash_prevouts = _dsha256(prevouts)
    hash_sequence = _dsha256(sequences)

    outputs_ser = b''.join(
        v.to_bytes(8, 'little') + _varint(len(spk)) + spk for v, spk in outputs
    )
    hash_outputs = _dsha256(outputs_ser)

    witnesses = []
    for u in chosen:
        outpoint = bytes.fromhex(u["txid"])[::-1] + u["vout"].to_bytes(4, 'little')
        preimage = (
            version + hash_prevouts + hash_sequence + outpoint + script_code +
            u["value"].to_bytes(8, 'little') + sequence + hash_outputs + locktime +
            (1).to_bytes(4, 'little')  # SIGHASH_ALL
        )
        sighash = _dsha256(preimage)
        der_sig = _ecdsa_sign(sighash, privkey) + b'\x01'  # append SIGHASH_ALL byte
        witnesses.append(_varint(2) + _push(der_sig) + _push(pub))

    tx = bytearray()
    tx += version
    tx += b'\x00\x01'  # segwit marker + flag
    tx += _varint(len(chosen))
    for u in chosen:
        tx += bytes.fromhex(u["txid"])[::-1] + u["vout"].to_bytes(4, 'little') + b'\x00' + sequence
    tx += _varint(len(outputs))
    for v, spk in outputs:
        tx += v.to_bytes(8, 'little') + _varint(len(spk)) + spk
    for w in witnesses:
        tx += w
    tx += locktime

    return bytes(tx).hex()


async def send(coin: str, privkey: bytes, from_address: str, to_address: str, amount_coin: float) -> str:
    """Async wrapper: build, sign, broadcast. Returns TXID."""
    import asyncio
    amount_sats = int(round(amount_coin * 1e8))

    def _run():
        raw_hex = build_and_sign(coin, privkey, from_address, to_address, amount_sats)
        return _bc_broadcast(coin, raw_hex)

    return await asyncio.get_event_loop().run_in_executor(None, _run)
