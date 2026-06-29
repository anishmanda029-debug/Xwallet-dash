# XWALLET — Multi-Coin Crypto Tip Bot

Crypto-only Discord wallet bot: deposit, tip, withdraw.
BTC, LTC, SOL, ETH, USDT (ERC20 + TRC20). 

## Quick Setup

1. cp .env.example .env — fill in all values
2. pip install -r requirements.txt  
3. Run watcher: cd bot/watcher && pip install -r requirements.txt && python watcher.py
4. Run bot+dashboard: python run_all.py

## Deposit Detection (toggle per coin via /setdetection or dashboard Settings)

- watcher (default) — bot/watcher/ standalone process, free public APIs
- alchemy — Alchemy Notify webhooks, ETH + USDT-ERC20 only

## Withdraw Payout (toggle per coin via /setwithdrawmethod)

- manual (default) — approve, pay from your wallet, mark paid
- alchemy — approve, bot builds unsigned tx, you sign locally, /broadcast sends it

## Key Commands

/deposit — DM-only, USD amount, picks coin, binds sender address
/withdraw — DM-only, USD amount, picks coin, binds payout address  
/tip @user coin $amount — slash tip
@XWALLET tip 26$ ltc @user — mention tip
/pendinglinks — confirm new sender addresses (authorised members)
/rules — rules + quick guide (also auto-DM on first use)
/setdetection coin method — toggle detection: watcher/alchemy
/setwithdrawmethod coin method — toggle payout: manual/alchemy
/broadcast id hex — send already-signed tx via Alchemy
/debug — owner diagnostics panel
