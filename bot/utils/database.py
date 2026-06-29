"""
XWALLET — Database Manager (PostgreSQL)
Uses asyncpg for async PostgreSQL — works on Railway, Supabase, Neon, etc.
Set DATABASE_URL in environment (Railway provides this automatically).
"""

import asyncpg
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # Railway provides postgres:// but asyncpg needs postgresql://
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=10)
    return _pool


# ── INIT ──────────────────────────────────────────────────────────────────────

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
CREATE TABLE IF NOT EXISTS guilds (
    guild_id        TEXT PRIMARY KEY,
    prefix          TEXT DEFAULT '$',
    log_channel     TEXT,
    withdraw_log    TEXT,
    deposit_log     TEXT,
    ticket_log      TEXT,
    owner_role      TEXT,
    staff_role      TEXT,
    earn_role       TEXT,
    sub_role        TEXT,
    antinuke        INTEGER DEFAULT 0,
    automod         INTEGER DEFAULT 0,
    hold_days       INTEGER DEFAULT 3,
    task_message    TEXT DEFAULT 'First Name:\nEmail:\nPassword:',
    task_reward_ltc REAL DEFAULT 0.001,
    settings        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT DEFAULT '',
    balance      REAL DEFAULT 0,
    hold         REAL DEFAULT 0,
    daily_last   TEXT,
    work_last    TEXT,
    invites      INTEGER DEFAULT 0,
    invite_code  TEXT,
    sub_active   INTEGER DEFAULT 0,
    onboarded    INTEGER DEFAULT 0,
    created_at   TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS user_balances (
    user_id  TEXT,
    coin     TEXT,
    balance  REAL DEFAULT 0,
    hold     REAL DEFAULT 0,
    PRIMARY KEY (user_id, coin)
);

CREATE TABLE IF NOT EXISTS detection_settings (
    coin   TEXT PRIMARY KEY,
    method TEXT DEFAULT 'watcher'
);

CREATE TABLE IF NOT EXISTS withdraw_settings (
    coin   TEXT PRIMARY KEY,
    method TEXT DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS address_links (
    coin           TEXT NOT NULL,
    sender_address TEXT NOT NULL,
    user_id        TEXT,
    status         TEXT DEFAULT 'pending',
    linked_by      TEXT,
    created_at     TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    PRIMARY KEY (coin, sender_address)
);

CREATE TABLE IF NOT EXISTS invoices (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT,
    coin            TEXT,
    usd_amount      REAL,
    coin_amount     REAL,
    sender_address  TEXT,
    deposit_address TEXT,
    status          TEXT DEFAULT 'awaiting_payment',
    tx_hash         TEXT DEFAULT '',
    created_at      TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    paid_at         TEXT,
    payment_detected_at TEXT,
    credited_at     TEXT
);

CREATE TABLE IF NOT EXISTS authorised_users (
    user_id     TEXT PRIMARY KEY,
    username    TEXT DEFAULT '',
    added_by    TEXT,
    added_at    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id            SERIAL PRIMARY KEY,
    user_id       TEXT,
    guild_id      TEXT,
    method        TEXT,
    address       TEXT,
    amount_coins  REAL DEFAULT 0,
    amount        REAL DEFAULT 0,
    fee           REAL DEFAULT 0,
    net_amount    REAL DEFAULT 0,
    usd_value     REAL DEFAULT 0,
    handled_by    TEXT DEFAULT '',
    payout_id     TEXT DEFAULT '',
    payout_status TEXT DEFAULT '',
    status        TEXT DEFAULT 'pending',
    note          TEXT DEFAULT '',
    created_at    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    updated_at    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS deposits (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT,
    guild_id        TEXT,
    method          TEXT,
    amount_coins    REAL DEFAULT 0,
    method_amount   REAL DEFAULT 0,
    fee             REAL DEFAULT 0,
    net_amount      REAL DEFAULT 0,
    usd_value       REAL DEFAULT 0,
    handled_by      TEXT DEFAULT '',
    payment_id      TEXT DEFAULT '',
    pay_address     TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    txid            TEXT DEFAULT '',
    claimed_amount  REAL DEFAULT 0,
    verified_txid   TEXT DEFAULT '',
    auto_verified   INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    updated_at      TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id          SERIAL PRIMARY KEY,
    channel_id  TEXT UNIQUE,
    guild_id    TEXT,
    user_id     TEXT,
    type        TEXT,
    status      TEXT DEFAULT 'open',
    task_step   INTEGER DEFAULT 0,
    transcript  TEXT DEFAULT '',
    created_at  TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    closed_at   TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id           SERIAL PRIMARY KEY,
    user_id      TEXT,
    guild_id     TEXT,
    ticket_id    INTEGER,
    channel_id   TEXT,
    step         INTEGER DEFAULT 1,
    total_steps  INTEGER DEFAULT 3,
    status       TEXT DEFAULT 'active',
    assigned_at  TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS task_stock (
    id        SERIAL PRIMARY KEY,
    guild_id  TEXT UNIQUE,
    total     INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS giveaways (
    id           SERIAL PRIMARY KEY,
    message_id   TEXT UNIQUE,
    channel_id   TEXT,
    guild_id     TEXT,
    host_id      TEXT,
    prize        TEXT,
    winners      INTEGER DEFAULT 1,
    participants TEXT DEFAULT '[]',
    end_time     TEXT,
    status       TEXT DEFAULT 'active',
    winner_ids   TEXT DEFAULT '[]',
    mode         TEXT DEFAULT 'random',
    created_at   TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS hold_entries (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT,
    guild_id   TEXT,
    currency   TEXT DEFAULT 'ltc',
    amount     REAL,
    reason     TEXT DEFAULT '',
    release_at TEXT,
    status     TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS rains (
    message_id TEXT PRIMARY KEY,
    channel_id TEXT,
    guild_id   TEXT,
    host_id    TEXT,
    coin       TEXT DEFAULT 'ltc',
    amount     REAL,
    claimers   TEXT DEFAULT '[]',
    end_time   TEXT,
    status     TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS logs (
    id         SERIAL PRIMARY KEY,
    guild_id   TEXT,
    user_id    TEXT,
    action     TEXT,
    detail     TEXT DEFAULT '',
    created_at TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id  TEXT,
    guild_id TEXT,
    active   INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS bot_guilds (
    guild_id     TEXT PRIMARY KEY,
    name         TEXT DEFAULT '',
    icon_url     TEXT DEFAULT '',
    member_count INTEGER DEFAULT 0,
    joined_at    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
    active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
""")
    print("[DB] All tables ready.")


# ── HELPERS ───────────────────────────────────────────────────────────────────

class _Row(dict):
    """Dict that supports both row['key'] and row.key access."""
    def __getitem__(self, key):
        return super().__getitem__(key)
    def __getattr__(self, key):
        try: return super().__getitem__(key)
        except KeyError: raise AttributeError(key)
    def get(self, key, default=None):
        return super().get(key, default)

def _wrap(row):
    if row is None: return None
    return _Row(dict(row))

def _wrapall(rows):
    return [_Row(dict(r)) for r in rows]


async def _fetchone(query: str, params=()):
    pool = await get_pool()
    # Convert ? to $1,$2,... for asyncpg
    q, p = _convert(query, params)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(q, *p)
        return _wrap(row)

async def _fetchall(query: str, params=()):
    pool = await get_pool()
    q, p = _convert(query, params)
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *p)
        return _wrapall(rows)

async def _execute(query: str, params=()):
    pool = await get_pool()
    q, p = _convert(query, params)
    async with pool.acquire() as conn:
        result = await conn.fetchval(q + " RETURNING id" if _needs_returning(q) else q, *p)
        return result

def _needs_returning(q: str) -> bool:
    ql = q.strip().upper()
    return ql.startswith("INSERT") and "RETURNING" not in ql

def _convert(query: str, params):
    """Convert SQLite ? placeholders to PostgreSQL $1, $2, ..."""
    result = []
    idx = 1
    i = 0
    while i < len(query):
        if query[i] == '?':
            result.append(f'${idx}')
            idx += 1
        else:
            result.append(query[i])
        i += 1
    # Convert SQLite-specific SQL to PostgreSQL
    q = ''.join(result)
    q = q.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    q = q.replace("INSERT OR REPLACE INTO", "INSERT INTO")
    q = q.replace(" ON CONFLICT", " ON CONFLICT")
    q = q.replace("DO NOTHING", "DO NOTHING")
    # Fix INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    if "INSERT INTO" in q and "ON CONFLICT" not in q and _needs_returning(q):
        # Will be handled per-function for complex cases
        pass
    return q, list(params)


async def _upsert(table: str, conflict_col: str, data: dict):
    """Generic upsert helper."""
    cols = list(data.keys())
    vals = list(data.values())
    placeholders = [f"${i+1}" for i in range(len(vals))]
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != conflict_col)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(placeholders)}) "
            f"ON CONFLICT ({conflict_col}) DO UPDATE SET {updates}",
            *vals
        )


# ── USER ──────────────────────────────────────────────────────────────────────

async def get_user(user_id: str):
    return await _fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))

async def ensure_user(user_id: str, username: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, username) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username WHERE EXCLUDED.username != ''",
            user_id, username
        )

async def get_balance(user_id: str, coin: str) -> float:
    row = await _fetchone("SELECT balance FROM user_balances WHERE user_id=? AND coin=?", (user_id, coin))
    return row["balance"] if row else 0.0

async def get_hold(user_id: str, coin: str) -> float:
    row = await _fetchone("SELECT hold FROM user_balances WHERE user_id=? AND coin=?", (user_id, coin))
    return row["hold"] if row else 0.0

async def get_all_balances(user_id: str) -> dict:
    rows = await _fetchall("SELECT coin,balance,hold FROM user_balances WHERE user_id=?", (user_id,))
    return {r["coin"]: {"balance": r["balance"], "hold": r["hold"]} for r in rows}

async def update_balance(user_id: str, coin: str, delta: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_balances (user_id,coin,balance) VALUES ($1,$2,0) "
            "ON CONFLICT (user_id,coin) DO NOTHING", user_id, coin
        )
        await conn.execute(
            "UPDATE user_balances SET balance=GREATEST(0,balance+$1) WHERE user_id=$2 AND coin=$3",
            delta, user_id, coin
        )

async def set_balance(user_id: str, coin: str, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_balances (user_id,coin,balance) VALUES ($1,$2,$3) "
            "ON CONFLICT (user_id,coin) DO UPDATE SET balance=GREATEST(0,EXCLUDED.balance)",
            user_id, coin, max(0, amount)
        )

async def update_hold(user_id: str, coin: str, delta: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_balances (user_id,coin,hold) VALUES ($1,$2,0) "
            "ON CONFLICT (user_id,coin) DO NOTHING", user_id, coin
        )
        await conn.execute(
            "UPDATE user_balances SET hold=GREATEST(0,hold+$1) WHERE user_id=$2 AND coin=$3",
            delta, user_id, coin
        )

async def set_hold(user_id: str, coin: str, amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_balances (user_id,coin,hold) VALUES ($1,$2,$3) "
            "ON CONFLICT (user_id,coin) DO UPDATE SET hold=GREATEST(0,EXCLUDED.hold)",
            user_id, coin, max(0, amount)
        )

async def get_top_holders(coin: str, limit: int = 10):
    return await _fetchall(
        "SELECT ub.user_id, ub.balance, u.username FROM user_balances ub "
        "LEFT JOIN users u ON u.user_id = ub.user_id "
        "WHERE ub.coin=? AND ub.balance>0 ORDER BY ub.balance DESC LIMIT ?",
        (coin, limit)
    )

async def get_total_holdings_by_coin() -> dict:
    rows = await _fetchall("SELECT coin, SUM(balance) as total_bal, SUM(hold) as total_hold FROM user_balances GROUP BY coin")
    return {r["coin"]: {"balance": r["total_bal"] or 0, "hold": r["total_hold"] or 0} for r in rows}

async def get_all_users():
    return await _fetchall("SELECT * FROM users")


# ── AUTHORISED USERS ──────────────────────────────────────────────────────────

async def add_authorised_user(user_id: str, username: str, added_by: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO authorised_users (user_id,username,added_by) VALUES ($1,$2,$3) "
            "ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, added_by=EXCLUDED.added_by",
            user_id, username, added_by
        )

async def remove_authorised_user(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM authorised_users WHERE user_id=$1", user_id)

async def is_authorised(user_id: str) -> bool:
    row = await _fetchone("SELECT 1 FROM authorised_users WHERE user_id=?", (user_id,))
    return bool(row)

async def get_authorised_users():
    return await _fetchall("SELECT * FROM authorised_users ORDER BY added_at DESC")


# ── GUILD ─────────────────────────────────────────────────────────────────────

async def get_guild(guild_id: str):
    row = await _fetchone("SELECT * FROM guilds WHERE guild_id=?", (guild_id,))
    if not row:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
        row = await _fetchone("SELECT * FROM guilds WHERE guild_id=?", (guild_id,))
    return row

async def update_guild(guild_id: str, **kwargs):
    if not kwargs: return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
        sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(kwargs))
        vals = [guild_id] + list(kwargs.values())
        await conn.execute(f"UPDATE guilds SET {sets} WHERE guild_id=$1", *vals)

async def get_prefix(guild_id: str) -> str:
    default = os.getenv("BOT_PREFIX", "$")
    row = await _fetchone("SELECT prefix FROM guilds WHERE guild_id=?", (guild_id,))
    return row["prefix"] if row and row["prefix"] else default

async def set_prefix(guild_id: str, prefix: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
        await conn.execute("UPDATE guilds SET prefix=$1 WHERE guild_id=$2", prefix, guild_id)

async def get_all_guilds():
    return await _fetchall("SELECT * FROM guilds")


# ── BOT GUILD TRACKING ────────────────────────────────────────────────────────

async def upsert_bot_guild(guild_id: str, name: str, icon_url: str, member_count: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_guilds (guild_id,name,icon_url,member_count,active) VALUES ($1,$2,$3,$4,1) "
            "ON CONFLICT (guild_id) DO UPDATE SET name=EXCLUDED.name, icon_url=EXCLUDED.icon_url, "
            "member_count=EXCLUDED.member_count, active=1",
            guild_id, name, icon_url, member_count
        )

async def mark_bot_guild_inactive(guild_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE bot_guilds SET active=0 WHERE guild_id=$1", guild_id)

async def get_all_bot_guilds():
    return await _fetchall("SELECT * FROM bot_guilds ORDER BY joined_at DESC")


# ── WITHDRAWALS ───────────────────────────────────────────────────────────────

async def create_withdrawal(user_id, guild_id, coin, address, amount, fee=0, net_amount=0, usd_value=0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO withdrawals (user_id,guild_id,method,address,amount,fee,net_amount,usd_value) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            user_id, guild_id, coin, address, amount, fee, net_amount, usd_value
        )
        return row["id"]

async def set_withdrawal_payout(wid: int, payout_id: str, payout_status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE withdrawals SET payout_id=$1,payout_status=$2,updated_at=$3 WHERE id=$4",
            payout_id, payout_status, datetime.utcnow().isoformat(), wid
        )

async def get_withdrawal(wid: int):
    return await _fetchone("SELECT * FROM withdrawals WHERE id=?", (wid,))

async def update_withdrawal_status(wid: int, status: str, note: str = "", handled_by: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE withdrawals SET status=$1,note=$2,handled_by=$3,updated_at=$4 WHERE id=$5",
            status, note, handled_by, datetime.utcnow().isoformat(), wid
        )

async def get_user_withdrawals(user_id: str):
    return await _fetchall("SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC", (user_id,))

async def get_all_withdrawals():
    return await _fetchall("SELECT * FROM withdrawals ORDER BY created_at DESC")

async def get_pending_withdrawals():
    return await _fetchall("SELECT * FROM withdrawals WHERE status='pending' ORDER BY created_at ASC")

async def get_withdrawal_by_payout_id(payout_id: str):
    return await _fetchone("SELECT * FROM withdrawals WHERE payout_id=?", (payout_id,))

def withdrawal_amount(row) -> float:
    return row["amount"]


# ── DETECTION / WITHDRAW METHOD ───────────────────────────────────────────────

async def get_detection_method(coin: str) -> str:
    row = await _fetchone("SELECT method FROM detection_settings WHERE coin=?", (coin,))
    return row["method"] if row else "watcher"

async def set_detection_method(coin: str, method: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO detection_settings (coin,method) VALUES ($1,$2) "
            "ON CONFLICT (coin) DO UPDATE SET method=EXCLUDED.method",
            coin, method
        )

async def get_withdraw_method(coin: str) -> str:
    row = await _fetchone("SELECT method FROM withdraw_settings WHERE coin=?", (coin,))
    return row["method"] if row else "manual"

async def set_withdraw_method(coin: str, method: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO withdraw_settings (coin,method) VALUES ($1,$2) "
            "ON CONFLICT (coin) DO UPDATE SET method=EXCLUDED.method",
            coin, method
        )


# ── ADDRESS LINKS ─────────────────────────────────────────────────────────────

async def declare_sender_address(coin: str, sender_address: str, user_id: str):
    existing = await get_address_link(coin, sender_address)
    if existing: return existing
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO address_links (coin,sender_address,user_id,status) VALUES ($1,$2,$3,'pending') "
            "ON CONFLICT DO NOTHING",
            coin, sender_address.lower(), user_id
        )
    return await get_address_link(coin, sender_address)

async def get_address_link(coin: str, sender_address: str):
    return await _fetchone(
        "SELECT * FROM address_links WHERE coin=? AND sender_address=?",
        (coin, sender_address.lower())
    )

async def confirm_address_link(coin: str, sender_address: str, user_id: str, linked_by: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO address_links (coin,sender_address,user_id,status,linked_by) VALUES ($1,$2,$3,'linked',$4) "
            "ON CONFLICT (coin,sender_address) DO UPDATE SET user_id=EXCLUDED.user_id, status='linked', linked_by=EXCLUDED.linked_by",
            coin, sender_address.lower(), user_id, linked_by
        )

async def is_address_linked(coin: str, sender_address: str):
    row = await _fetchone(
        "SELECT user_id FROM address_links WHERE coin=? AND sender_address=? AND status='linked'",
        (coin, sender_address.lower())
    )
    return row["user_id"] if row else None

async def get_pending_links():
    return await _fetchall("SELECT * FROM address_links WHERE status='pending' ORDER BY created_at DESC")


# ── INVOICES ──────────────────────────────────────────────────────────────────

async def create_invoice(user_id, coin, usd_amount, coin_amount, sender_address, deposit_address):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO invoices (user_id,coin,usd_amount,coin_amount,sender_address,deposit_address) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, coin, usd_amount, coin_amount, sender_address, deposit_address
        )
        return row["id"]

async def get_invoice(invoice_id: int):
    return await _fetchone("SELECT * FROM invoices WHERE id=?", (invoice_id,))

async def get_user_invoices(user_id: str):
    return await _fetchall("SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC", (user_id,))

async def mark_invoice_paid(invoice_id: int, tx_hash: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE invoices SET status='paid', tx_hash=$1, paid_at=$2 WHERE id=$3",
            tx_hash, datetime.utcnow().isoformat(), invoice_id
        )

async def get_open_invoices_for_address(coin: str, sender_address: str):
    return await _fetchall(
        "SELECT * FROM invoices WHERE coin=? AND sender_address=? AND status='awaiting_payment' ORDER BY created_at ASC",
        (coin, sender_address.lower())
    )


# ── ONBOARDING ────────────────────────────────────────────────────────────────

async def is_onboarded(user_id: str) -> bool:
    row = await _fetchone("SELECT onboarded FROM users WHERE user_id=?", (user_id,))
    return bool(row["onboarded"]) if row else False

async def mark_onboarded(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET onboarded=1 WHERE user_id=$1", user_id)


# ── DEPOSITS ──────────────────────────────────────────────────────────────────

async def create_deposit(user_id, guild_id, method, amount, fee=0, net_amount=0, usd_value=0, txid="", payment_id="", pay_address=""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO deposits (user_id,guild_id,method,method_amount,fee,net_amount,usd_value,txid,claimed_amount,payment_id,pay_address) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id",
            user_id, guild_id, method, amount, fee, net_amount, usd_value, txid, amount, payment_id, pay_address
        )
        return row["id"]

async def get_deposit(dep_id: int):
    return await _fetchone("SELECT * FROM deposits WHERE id=?", (dep_id,))

async def get_deposit_by_payment_id(payment_id: str):
    return await _fetchone("SELECT * FROM deposits WHERE payment_id=?", (payment_id,))

async def update_deposit_status(dep_id: int, status: str, handled_by: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE deposits SET status=$1,handled_by=$2,updated_at=$3 WHERE id=$4",
            status, handled_by, datetime.utcnow().isoformat(), dep_id
        )

async def get_user_deposits(user_id: str):
    return await _fetchall("SELECT * FROM deposits WHERE user_id=? ORDER BY created_at DESC", (user_id,))

async def get_all_deposits():
    return await _fetchall("SELECT * FROM deposits ORDER BY created_at DESC")

async def get_pending_deposits():
    return await _fetchall("SELECT * FROM deposits WHERE status='pending' ORDER BY created_at ASC")

async def get_pending_coin_deposits(coin: str):
    return await _fetchall(
        "SELECT * FROM deposits WHERE method=? AND status IN ('pending','pending_chain') ORDER BY created_at ASC",
        (coin,)
    )

async def get_claimed_txids():
    rows = await _fetchall("SELECT verified_txid FROM deposits WHERE verified_txid != ''")
    return [r["verified_txid"] for r in rows]

async def complete_deposit_onchain(dep_id: int, user_id: str, coin: str, amount: float, fee: float, net_amount: float, txid: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE deposits SET status='approved', method_amount=$1, fee=$2, net_amount=$3, "
            "verified_txid=$4, auto_verified=1, updated_at=$5 WHERE id=$6",
            amount, fee, net_amount, txid, datetime.utcnow().isoformat(), dep_id
        )
    await update_balance(user_id, coin, net_amount)

def deposit_amount(row) -> float:
    return row["method_amount"] if row["method_amount"] else row["claimed_amount"]


# ── TICKETS ───────────────────────────────────────────────────────────────────

async def create_ticket(channel_id, guild_id, user_id, ticket_type):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tickets (channel_id,guild_id,user_id,type) VALUES ($1,$2,$3,$4) RETURNING id",
            channel_id, guild_id, user_id, ticket_type
        )
        return row["id"]

async def get_ticket(channel_id: str):
    return await _fetchone("SELECT * FROM tickets WHERE channel_id=?", (channel_id,))

async def close_ticket(channel_id: str, transcript: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET status='closed',transcript=$1,closed_at=$2 WHERE channel_id=$3",
            transcript, datetime.utcnow().isoformat(), channel_id
        )

async def get_all_tickets():
    return await _fetchall("SELECT * FROM tickets ORDER BY created_at DESC")


# ── TASKS ─────────────────────────────────────────────────────────────────────

async def create_task(user_id, guild_id, ticket_id, channel_id, total_steps=3):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tasks (user_id,guild_id,ticket_id,channel_id,total_steps) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            user_id, guild_id, ticket_id, channel_id, total_steps
        )
        return row["id"]

async def get_task_by_channel(channel_id: str):
    return await _fetchone("SELECT * FROM tasks WHERE channel_id=? AND status='active'", (channel_id,))

async def advance_task_step(task_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tasks SET step=step+1 WHERE id=$1", task_id)

async def complete_task(task_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tasks SET status='completed',completed_at=$1 WHERE id=$2",
            datetime.utcnow().isoformat(), task_id
        )

async def get_task_stock(guild_id: str):
    row = await _fetchone("SELECT * FROM task_stock WHERE guild_id=?", (guild_id,))
    if not row:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO task_stock (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
        row = await _fetchone("SELECT * FROM task_stock WHERE guild_id=?", (guild_id,))
    return row

async def update_task_stock(guild_id: str, delta_total=0, delta_completed=0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO task_stock (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
        await conn.execute(
            "UPDATE task_stock SET total=total+$1,completed=completed+$2 WHERE guild_id=$3",
            delta_total, delta_completed, guild_id
        )


# ── GIVEAWAYS ─────────────────────────────────────────────────────────────────

async def create_giveaway(message_id, channel_id, guild_id, host_id, prize, winners, end_time, mode="random"):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO giveaways (message_id,channel_id,guild_id,host_id,prize,winners,end_time,mode) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            message_id, channel_id, guild_id, host_id, prize, winners, end_time.isoformat(), mode
        )
        return row["id"]

async def get_giveaway(message_id: str):
    return await _fetchone("SELECT * FROM giveaways WHERE message_id=?", (message_id,))

async def update_giveaway_participants(message_id: str, participants: list):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE giveaways SET participants=$1 WHERE message_id=$2", json.dumps(participants), message_id)

async def end_giveaway(message_id: str, winner_ids: list):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE giveaways SET status='ended',winner_ids=$1 WHERE message_id=$2", json.dumps(winner_ids), message_id)

async def get_active_giveaways():
    return await _fetchall("SELECT * FROM giveaways WHERE status='active'")


# ── HOLD ENTRIES ──────────────────────────────────────────────────────────────

async def add_hold_entry(user_id, guild_id, coin, amount, reason, days):
    release_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO hold_entries (user_id,guild_id,currency,amount,reason,release_at) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, guild_id, coin, amount, reason, release_at
        )
        return row["id"]

async def get_active_hold_entries(user_id: str):
    return await _fetchall("SELECT * FROM hold_entries WHERE user_id=? AND status='active' ORDER BY release_at", (user_id,))

async def get_expired_hold_entries():
    return await _fetchall(
        "SELECT * FROM hold_entries WHERE status='active' AND release_at <= ?",
        (datetime.utcnow().isoformat(),)
    )

async def release_hold_entry(entry_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE hold_entries SET status='released' WHERE id=$1", entry_id)


# ── RAIN ──────────────────────────────────────────────────────────────────────

async def create_rain(message_id, channel_id, guild_id, host_id, coin, amount, end_time):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO rains (message_id,channel_id,guild_id,host_id,coin,amount,end_time) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            message_id, channel_id, guild_id, host_id, coin, amount, end_time.isoformat()
        )

async def get_rain(message_id: str):
    return await _fetchone("SELECT * FROM rains WHERE message_id=?", (message_id,))

async def update_rain_claimers(message_id: str, claimers: list):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE rains SET claimers=$1 WHERE message_id=$2", json.dumps(claimers), message_id)

async def end_rain(message_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE rains SET status='ended' WHERE message_id=$1", message_id)

async def get_active_rains():
    return await _fetchall("SELECT * FROM rains WHERE status='active'")


# ── LOGS ──────────────────────────────────────────────────────────────────────

async def add_log(guild_id, user_id, action, detail):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logs (guild_id,user_id,action,detail) VALUES ($1,$2,$3,$4)",
            guild_id, user_id, action, detail
        )

async def get_logs(guild_id: str, limit: int = 50):
    return await _fetchall(
        "SELECT * FROM logs WHERE guild_id=? ORDER BY created_at DESC LIMIT ?",
        (guild_id, limit)
    )

async def get_all_logs():
    return await _fetchall("SELECT * FROM logs ORDER BY created_at DESC LIMIT 1000")


# ── SUBSCRIPTIONS ─────────────────────────────────────────────────────────────

async def set_subscription(user_id: str, guild_id: str, active: bool):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id,guild_id,active) VALUES ($1,$2,$3) "
            "ON CONFLICT (user_id,guild_id) DO UPDATE SET active=EXCLUDED.active",
            user_id, guild_id, 1 if active else 0
        )

async def get_subscription(user_id: str, guild_id: str) -> bool:
    row = await _fetchone("SELECT active FROM subscriptions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    return bool(row["active"]) if row else False


# ── FULL BACKUP ───────────────────────────────────────────────────────────────

async def get_full_backup() -> dict:
    tables = [
        "guilds", "users", "user_balances", "authorised_users", "withdrawals", "deposits",
        "tickets", "tasks", "task_stock", "giveaways", "hold_entries", "rains",
        "address_links", "invoices", "detection_settings", "withdraw_settings",
        "logs", "subscriptions", "bot_guilds",
    ]
    result = {}
    for table in tables:
        try:
            result[table] = [dict(r) for r in await _fetchall(f"SELECT * FROM {table}")]
        except Exception:
            result[table] = []
    return result
