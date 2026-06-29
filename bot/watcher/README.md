# XWALLET Watcher

A standalone process — **no Discord token, no private keys** — that polls
6 shared deposit addresses (BTC, LTC, ETH, SOL, USDT-ERC20, USDT-TRC20)
every 30s using free public block explorer APIs, and reports new incoming
payments to the main XWALLET bot over HTTP.

## Why it's separate

- It never touches a Discord token, so it can run anywhere cheap/disposable.
- The main bot is the only thing that can credit a balance — one place to
  control what actually gets credited.
- Connected by a shared secret, not trust: the main bot rejects any
  webhook call that doesn't present `WATCHER_SHARED_SECRET`.

## Run it

```bash
cd bot/watcher
pip install -r requirements.txt
cp .env.example .env
# fill in MAIN_BOT_URL, SHARED_SECRET (must match the main bot's
# WATCHER_SHARED_SECRET exactly), and whichever addresses you're using
python watcher.py
```

It can run on the same machine as the main bot (just a second terminal /
process) or on a totally separate machine — as long as it can reach
`MAIN_BOT_URL`.

## How crediting works

1. Watcher sees a new tx paying into one of your shared addresses.
2. POSTs `{coin, tx_hash, from_address, amount, confirmations}` to the
   main bot's `/webhooks/watcher` endpoint.
3. Main bot checks if `from_address` is already linked to a Discord user
   (via the `/deposit` DM flow). If yes → auto-credited instantly. If
   it's a brand-new sending address → queued for manual review
   (`/pendinglinks` in Discord), and every future payment from that same
   address auto-credits once it's linked once.
