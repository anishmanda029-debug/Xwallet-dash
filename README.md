# ⚡ PremiumBot — Complete Setup Guide

A **premium-grade** Discord bot + web dashboard.

---

## 📁 Full Project Structure

```
premiumbot/
├── bot/
│   ├── cogs/
│   │   ├── economy.py        # /balance /daily /work /transfer /leaderboard /rates
│   │   ├── rain.py           # /rain — live countdown, claim buttons
│   │   ├── giveaway.py       # /gstart /gend /greroll — live updates
│   │   ├── tickets.py        # Dropdown panel, transcripts, logs
│   │   ├── tasks.py          # /task /taskstock — step-by-step flow
│   │   ├── withdraw.py       # /withdraw — LTC/INR owner approval
│   │   ├── deposit.py        # /deposit — QR codes, copy buttons
│   │   ├── admin.py          # Balance edit, messaging, ping, uptime
│   │   ├── settings.py       # Server role/channel configuration
│   │   ├── invites.py        # Live invite tracking + leaderboard
│   │   ├── moderation.py     # warn mute kick ban purge lock slowmode
│   │   ├── antinuke.py       # Mass-action real-time protection
│   │   ├── automod.py        # Spam/caps/link/invite filtering
│   │   ├── reaction_roles.py # Emoji reaction role assignment
│   │   ├── hold.py           # Hold entries + auto-release loop
│   │   ├── backup.py         # /backup JSON + TXT export
│   │   ├── help.py           # Interactive dropdown help menu
│   │   └── subscription.py   # Prefix-free shortcuts toggle
│   ├── utils/
│   │   ├── database.py       # All async SQLite operations
│   │   ├── embeds.py         # Full emoji pack + embed helpers
│   │   ├── logger.py         # Structured logging to file+Discord
│   │   └── checks.py         # Permission predicates
│   ├── data/                 # database.db (auto-created)
│   └── main.py               # Bot entry point + event handlers
├── dashboard/
│   ├── app.py                # Flask app + all routes + API
│   ├── templates/
│   │   ├── base.html         # Sidebar layout + particles
│   │   ├── index.html        # Landing page
│   │   ├── dashboard.html    # Stats home
│   │   ├── users.html        # User management + edit modal
│   │   ├── withdrawals.html  # Approve/reject + totals bar
│   │   ├── deposits.html     # Deposit approval
│   │   ├── tickets.html      # Ticket viewer + transcripts
│   │   ├── giveaways.html    # Giveaway history
│   │   ├── settings.html     # Guild config + task editor
│   │   ├── logs.html         # Activity logs with filters
│   │   └── error.html        # 403/404/500 pages
│   └── static/
│       ├── css/main.css      # Premium dark glassmorphism UI
│       ├── css/extra.css     # Component-specific styles
│       └── js/main.js        # Particles, animations, toast
├── run_bot.py                # Start bot only
├── run_dashboard.py          # Start dashboard only
├── run_all.py                # Start both simultaneously
├── requirements.txt
├── .env.example
├── render.yaml               # Render.com deployment
├── Procfile                  # Heroku/Railway deployment
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd premiumbot
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env    # Fill in all values
```

### 3. Create Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application** → name it → go to **Bot** tab
3. **Reset Token** → copy → paste as `DISCORD_TOKEN`
4. Enable all **Privileged Gateway Intents**:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. **OAuth2** tab → copy **Client ID** → `DISCORD_CLIENT_ID`
6. **OAuth2** tab → **Client Secret** → `DISCORD_CLIENT_SECRET`
7. Add redirect URL: `http://localhost:5000/callback`
8. Your Discord User ID → `OWNER_ID`

### 4. Run

```bash
# Both bot + dashboard
python run_all.py

# Bot only
python run_bot.py

# Dashboard only
python run_dashboard.py
```

### 5. Access Dashboard

Open `http://localhost:5000` and login with Discord.

---

## ⚙️ First-Time Server Setup (in order)

```
1.  /setownerrole   @AdminRole
2.  /setstaffrole   @StaffRole
3.  /setearnrole    @EarnRole
4.  /setsubrole     @SubRole       (optional)
5.  /setlogchannel  #logs
6.  /setwithdrawlog #withdraw-logs
7.  /setticketlog   #ticket-logs
8.  /ticketpanel    (in #support channel)
9.  /antinuke       enable:true
10. /automod        (configure via buttons)
11. /setholddays    3
12. /settask        First Name:\nEmail:\nPassword:
```

---

## 💰 Economy Commands

| Command | Description |
|---------|-------------|
| `/balance [@user]` | View wallet (coins + INR + LTC) |
| `/daily` | Claim daily reward (24h cooldown) |
| `/work` | Work for coins (1h cooldown) |
| `/transfer @user amount` | Send coins to another user |
| `/leaderboard` | Top 10 richest users |
| `/rates` | View current conversion rates |
| `!pay @user amount` | Admin: pay a user |

---

## ☔ Rain System

```
/rain amount:1000
```
- Deducts coins from host immediately
- Users click **☔ Claim Rain** button
- Coins split randomly when timer ends
- Live countdown embed updates every 10s
- Nobody claims → refund to host

---

## 🎉 Giveaway System

```
/gstart time:1h winners:2 prize:Discord Nitro
/gend message_id
/greroll message_id
```
- Live countdown updates every 10s
- Enter/Leave toggle button
- **End Early** button (admin/host only)
- **Force Pick** button (choose specific winner)
- Auto-DMs winners on end

---

## 🎫 Ticket System

Run `/ticketpanel` in your support channel.

Types: **🎫 Support** · **💳 Payment** · **💰 Earning**

Each ticket has:
- Close (saves transcript to log channel)
- Add User / Remove User buttons
- Earning tickets auto-show task form

---

## 📋 Task System

```
/task          — Open a task ticket
/taskstock     — View total/completed/pending
/settask msg   — Edit task template (use \n for newlines)
```

Flow: Step 1 → 2 → 3 → Complete → reward added to hold

---

## 💸 Withdraw System

```
/withdraw
```
1. Choose **INR (UPI)** or **LTC**
2. Enter amount + address
3. 3-step animated loading
4. Owner gets DM with ✅ Approve / ❌ Reject buttons
5. Balance only deducted **on approval**
6. User gets DM on both outcomes

---

## 📥 Deposit System

```
/deposit
```
1. Choose **INR** or **LTC**
2. QR code shown + copy button
3. Click **I Paid** → enter amount + TxID
4. Owner gets DM notification
5. Approve via Dashboard → Deposits page

---

## 🔒 Hold System

```
/holdinfo       — Upcoming releases + explanation
/holdhistory    — Your active hold entries
/addhold @u amt days reason  — Admin: add hold
/releasepay @u [entry_id]    — Admin: early release
/setholddays N               — Set default days (1-30)
```

Auto-releases every **10 minutes** in background.
User gets DM when hold releases.

---

## 🌐 Dashboard Pages

| Page | Description |
|------|-------------|
| `/dashboard` | Stats, economy overview, recent logs, top users |
| `/users` | Search, sort, edit balance/hold/invites |
| `/withdrawals` | Approve/reject with reason, filter by status/method |
| `/deposits` | Approve deposits, add coins to user |
| `/tickets` | View all tickets, read transcripts |
| `/giveaways` | Giveaway history and winner records |
| `/settings` | Guild config, task template, toggles |
| `/logs` | Full activity logs with action/user filter |

---

## 🛡️ AntiNuke

```
/antinuke enable:true
```

Auto-bans + strips roles from anyone who:
- Bans 3+ members in 10 seconds
- Kicks 3+ members in 10 seconds
- Deletes 2+ channels in 10 seconds
- Deletes 2+ roles in 10 seconds
- Creates 2+ webhooks in 10 seconds

Owner gets DM alert on every trigger.

---

## 🤖 AutoMod

```
/automod              — View config + toggle buttons
/setspam N            — Set spam limit (3-10 msg/5s)
/setwarnlimit N       — Set warn count before auto-mute
```

Filters: Spam · Excessive Caps · Discord Invites · External Links

---

## 💬 Subscription (Prefix-free Shortcuts)

```
/subscription   — Toggle on/off
```

When active (no prefix needed):
- `-help` → help menu
- `-si` → task stock
- `-bal` → balance
- `-daily` → daily
- `-work` → work
- `-rates` → rates
- `-inv` → invites

---

## 🎭 Reaction Roles

```
/reactionrole #channel "Title" "Description" 🎮 @Role
/listreactionroles
/removereactionrole message_id emoji
```

---

## 📦 Backup

```
/backup           — JSON + TXT report
/backup json      — JSON only
/backup txt       — Human-readable TXT only
```

TXT report includes wallet summary, withdrawal totals,
all users sorted by balance, withdrawal history, recent logs.

---

## 🚀 Deployment

### Render.com (Recommended)

1. Push to GitHub
2. New Blueprint on Render → connect repo (reads `render.yaml`)
3. Set env vars in Render dashboard
4. Deploy!

> ⚠️ For persistent DB on Render, add a **Render Disk** mounted at `/opt/render/project/src/bot/data`

### Railway / Heroku

```bash
git push heroku main  # Uses Procfile automatically
```

### VPS

```bash
pip install -r requirements.txt
cp .env.example .env && nano .env
python run_all.py
# Use screen/tmux/systemd to keep alive
```

---

## 🔑 Full Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token from dev portal | **required** |
| `OWNER_ID` | Your Discord user ID | **required** |
| `OWNER_PASSWORD` | Secret for /ownerbal | **required** |
| `BOT_PREFIX` | Default command prefix | `!` |
| `DAILY_AMOUNT` | Daily reward coins | `500` |
| `WORK_MIN` | Min work earnings | `100` |
| `WORK_MAX` | Max work earnings | `400` |
| `TASK_REWARD` | Coins per task complete | `200` |
| `INR_RATE` | Coins→INR multiplier | `0.1` |
| `LTC_RATE` | Coins→LTC multiplier | `0.000001` |
| `HOLD_DAYS` | Default hold release days | `3` |
| `UPI_ID` | Your UPI ID for deposits | — |
| `LTC_ADDRESS` | Your LTC address | — |
| `INR_QR_URL` | INR QR code image URL | — |
| `LTC_QR_URL` | LTC QR code image URL | — |
| `DASHBOARD_SECRET` | Flask session secret | **required** |
| `DISCORD_CLIENT_ID` | OAuth2 app client ID | **required** |
| `DISCORD_CLIENT_SECRET` | OAuth2 app secret | **required** |
| `DISCORD_REDIRECT_URI` | OAuth2 callback URL | `http://localhost:5000/callback` |
| `DATABASE_PATH` | SQLite DB file path | `bot/data/database.db` |
| `PORT` | Dashboard port | `5000` |

---

## 🛠️ Troubleshooting

| Issue | Fix |
|-------|-----|
| Slash commands not appearing | Wait up to 1 hour, or kick+reinvite bot |
| `DISCORD_TOKEN not set` | Check `.env` is in root directory |
| Dashboard 403 | Make sure your Discord ID matches `OWNER_ID` |
| `Database locked` | Only run one bot instance at a time |
| Emojis showing as text | Replace emoji IDs in `bot/utils/embeds.py` |
| Hold not releasing | Check bot is running (background task every 10 min) |
| Tickets not creating channels | Bot needs Manage Channels permission |

---

## 🎨 Custom Emoji Setup

All emoji IDs are in `bot/utils/embeds.py` in the `E = {}` dict.

To use your own server's emojis:
1. Type `\:your_emoji:` in Discord → copy the ID
2. Replace the corresponding ID in `embeds.py`
3. Restart the bot

---

**Built with ❤️ — PremiumBot v2.0**
