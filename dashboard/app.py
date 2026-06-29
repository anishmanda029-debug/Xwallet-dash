"""
XWALLET Dashboard — Flask Web Panel (PostgreSQL version for Railway)
"""

import os, json, hmac, hashlib, psycopg2, psycopg2.extras, requests
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, redirect, url_for,
    session, request, jsonify, flash, Response
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", "change-me-secret-key")

CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID",     "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("DISCORD_REDIRECT_URI",  "http://localhost:5000/callback")
OWNER_ID      = os.getenv("OWNER_ID",              "0")
DATABASE_URL  = os.getenv("DATABASE_URL",          "")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
WATCHER_SHARED_SECRET  = os.getenv("WATCHER_SHARED_SECRET",  "")

DISCORD_API = "https://discord.com/api/v10"
OAUTH_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={requests.utils.quote(REDIRECT_URI, safe='')}"
    f"&response_type=code"
    f"&scope=identify+guilds"
)

COINS = {
    "btc":       {"label": "Bitcoin",     "symbol": "BTC",  "decimals": 8},
    "ltc":       {"label": "Litecoin",    "symbol": "LTC",  "decimals": 8},
    "sol":       {"label": "Solana",      "symbol": "SOL",  "decimals": 6},
    "eth":       {"label": "Ethereum",    "symbol": "ETH",  "decimals": 6},
    "usdterc20": {"label": "USDT (ERC20)","symbol": "USDT", "decimals": 2},
    "usdttrc20": {"label": "USDT (TRC20)","symbol": "USDT", "decimals": 2},
}
COIN_ORDER = ["btc", "ltc", "sol", "eth", "usdterc20", "usdttrc20"]


def get_db():
    url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def fmt_coin(amount, coin):
    d   = COINS.get(coin, {}).get("decimals", 8)
    sym = COINS.get(coin, {}).get("symbol", (coin or "").upper())
    return f"{(amount or 0):.{d}f} {sym}"

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def require_owner(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if str(session["user"]["id"]) != str(OWNER_ID) and not is_authorised(session["user"]["id"]):
            return render_template("error.html", code=403, message="Access denied."), 403
        return f(*args, **kwargs)
    return decorated

def require_owner_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if str(session["user"]["id"]) != str(OWNER_ID):
            return render_template("error.html", code=403, message="Owner only."), 403
        return f(*args, **kwargs)
    return decorated

def is_authorised(user_id) -> bool:
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1 FROM authorised_users WHERE user_id=%s", (str(user_id),))
            return bool(cur.fetchone())
    finally:
        db.close()

def discord_get(endpoint, token):
    r = requests.get(f"{DISCORD_API}{endpoint}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    return r.json() if r.ok else None

def db_fetchone(query, params=()):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
    finally:
        db.close()

def db_fetchall(query, params=()):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        db.close()

def db_execute(query, params=()):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(query, params)
            db.commit()
    finally:
        db.close()

@app.context_processor
def inject_globals():
    user_authorised = False
    if "user" in session:
        user_authorised = is_authorised(session["user"]["id"])
    return {"owner_id": OWNER_ID, "coins": COINS, "coin_order": COIN_ORDER, "is_authorised": user_authorised}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/login")
def login():
    return redirect(OAUTH_URL)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))
    r = requests.post(
        f"{DISCORD_API}/oauth2/token",
        data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
              "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10,
    )
    if not r.ok:
        return redirect(url_for("index"))
    token_data   = r.json()
    access_token = token_data.get("access_token")
    user_data    = discord_get("/users/@me", access_token)
    if not user_data:
        return redirect(url_for("index"))
    session["user"]  = user_data
    session["token"] = access_token
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="Access denied."), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Internal server error."), 500

@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.route("/webhooks/watcher", methods=["POST"])
def watcher_webhook():
    auth = request.headers.get("Authorization", "")
    if not WATCHER_SHARED_SECRET or auth != f"Bearer {WATCHER_SHARED_SECRET}":
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    coin         = (data.get("coin") or "").lower()
    tx_hash      = data.get("tx_hash", "")
    from_address = (data.get("from_address") or "").lower()
    amount       = data.get("amount")
    if coin not in COINS or not tx_hash or amount is None:
        return jsonify({"error": "invalid fields"}), 400
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1 FROM deposits WHERE method=%s AND verified_txid=%s", (coin, tx_hash))
            if cur.fetchone():
                return jsonify({"status": "already_processed"})
            cur.execute("SELECT user_id FROM address_links WHERE coin=%s AND sender_address=%s AND status='linked'", (coin, from_address))
            link = cur.fetchone()
            fee_pct = float(os.getenv("FEE_PCT", "2"))
            fee = round(amount * (fee_pct / 100), 8)
            net = round(amount - fee, 8)
            if link:
                user_id = link["user_id"]
                cur.execute(
                    "INSERT INTO deposits (user_id,guild_id,method,method_amount,fee,net_amount,verified_txid,auto_verified,status,claimed_amount) "
                    "VALUES (%s,'WATCHER',%s,%s,%s,%s,%s,1,'approved',%s)",
                    (user_id, coin, amount, fee, net, tx_hash, amount)
                )
                cur.execute(
                    "INSERT INTO user_balances (user_id,coin,balance) VALUES (%s,%s,0) ON CONFLICT (user_id,coin) DO NOTHING",
                    (user_id, coin)
                )
                cur.execute(
                    "UPDATE user_balances SET balance=GREATEST(0,balance+%s) WHERE user_id=%s AND coin=%s",
                    (net, user_id, coin)
                )
                db.commit()
                return jsonify({"status": "credited", "user_id": user_id})
            else:
                cur.execute(
                    "INSERT INTO address_links (coin,sender_address,user_id,status) VALUES (%s,%s,NULL,'pending') ON CONFLICT DO NOTHING",
                    (coin, from_address)
                )
                cur.execute(
                    "INSERT INTO deposits (user_id,guild_id,method,method_amount,fee,net_amount,verified_txid,status,claimed_amount) "
                    "VALUES ('UNASSIGNED','WATCHER',%s,%s,%s,%s,%s,'pending',%s)",
                    (coin, amount, fee, net, tx_hash, amount)
                )
                db.commit()
                return jsonify({"status": "pending_review"})
    finally:
        db.close()

@app.route("/webhooks/nowpayments", methods=["POST"])
def nowpayments_webhook():
    raw_body  = request.get_data()
    signature = request.headers.get("x-nowpayments-sig", "")
    if NOWPAYMENTS_IPN_SECRET:
        try:
            parsed      = json.loads(raw_body)
            sorted_body = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
            expected    = hmac.new(NOWPAYMENTS_IPN_SECRET.encode(), sorted_body.encode(), hashlib.sha512).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return jsonify({"ok": False, "error": "invalid signature"}), 401
        except Exception:
            return jsonify({"ok": False, "error": "bad payload"}), 400
    data       = request.get_json(silent=True) or {}
    payment_id = str(data.get("payment_id", ""))
    status     = data.get("payment_status") or data.get("status", "")
    db = get_db()
    try:
        with db.cursor() as cur:
            if payment_id:
                cur.execute("SELECT * FROM deposits WHERE payment_id=%s", (payment_id,))
                dep = cur.fetchone()
                if dep and dep["status"] == "pending" and status in ("finished", "confirmed"):
                    cur.execute("UPDATE deposits SET status='approved', updated_at=%s WHERE id=%s",
                                (datetime.utcnow().isoformat(), dep["id"]))
                    cur.execute(
                        "INSERT INTO user_balances (user_id,coin,balance) VALUES (%s,%s,0) ON CONFLICT (user_id,coin) DO NOTHING",
                        (dep["user_id"], dep["method"])
                    )
                    cur.execute(
                        "UPDATE user_balances SET balance=GREATEST(0,balance+%s) WHERE user_id=%s AND coin=%s",
                        (dep["net_amount"], dep["user_id"], dep["method"])
                    )
            db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@require_login
def dashboard():
    user     = session["user"]
    is_owner = str(user["id"]) == str(OWNER_ID)
    db = get_db()
    try:
        with db.cursor() as cur:
            def count(q): cur.execute(q); return cur.fetchone()[list(cur.fetchone().keys())[0]] if False else cur.fetchone()
            stats = {}
            for key, q in [
                ("users",        "SELECT COUNT(*) as c FROM users"),
                ("withdrawals",  "SELECT COUNT(*) as c FROM withdrawals"),
                ("pending_wd",   "SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'"),
                ("approved_wd",  "SELECT COUNT(*) as c FROM withdrawals WHERE status IN ('approved','paid')"),
                ("deposits",     "SELECT COUNT(*) as c FROM deposits"),
                ("pending_dep",  "SELECT COUNT(*) as c FROM deposits WHERE status='pending'"),
                ("authorised",   "SELECT COUNT(*) as c FROM authorised_users"),
                ("servers",      "SELECT COUNT(*) as c FROM bot_guilds WHERE active=1"),
                ("logs",         "SELECT COUNT(*) as c FROM logs"),
            ]:
                cur.execute(q); stats[key] = cur.fetchone()["c"]

            cur.execute("SELECT coin, SUM(balance) as total_bal, SUM(hold) as total_hold FROM user_balances GROUP BY coin")
            holdings = {r["coin"]: {"balance": r["total_bal"] or 0, "hold": r["total_hold"] or 0} for r in cur.fetchall()}

            cur.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 10")
            recent_logs = cur.fetchall()

            cur.execute(
                "SELECT ub.user_id, ub.coin, ub.balance, u.username FROM user_balances ub "
                "LEFT JOIN users u ON u.user_id = ub.user_id WHERE ub.balance > 0 ORDER BY ub.balance DESC LIMIT 5"
            )
            top_users_raw = cur.fetchall()
    finally:
        db.close()
    return render_template(
        "dashboard.html", user=user, is_owner=is_owner,
        stats=stats, recent_logs=recent_logs, top_users=top_users_raw,
        holdings=holdings, fmt_coin=fmt_coin,
    )


# ── Users ─────────────────────────────────────────────────────────────────────

@app.route("/users")
@require_owner
def users_page():
    search = request.args.get("q", "").strip()
    db = get_db()
    try:
        with db.cursor() as cur:
            if search:
                cur.execute("SELECT * FROM users WHERE username ILIKE %s OR user_id ILIKE %s ORDER BY created_at DESC",
                            (f"%{search}%", f"%{search}%"))
            else:
                cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 200")
            users = cur.fetchall()
            balances_by_user = {}
            for u in users:
                cur.execute("SELECT coin, balance, hold FROM user_balances WHERE user_id=%s", (u["user_id"],))
                balances_by_user[u["user_id"]] = {r["coin"]: {"balance": r["balance"], "hold": r["hold"]} for r in cur.fetchall()}
    finally:
        db.close()
    return render_template("users.html", users=users, search=search, balances=balances_by_user, fmt_coin=fmt_coin)

@app.route("/users/<user_id>/edit", methods=["POST"])
@require_owner
def edit_user(user_id):
    action = request.form.get("action", "")
    coin   = request.form.get("coin", "ltc")
    if coin not in COINS:
        return jsonify({"ok": False, "error": "Invalid coin"})
    try:
        value = float(request.form.get("value", 0))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid value"})
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO user_balances (user_id,coin,balance,hold) VALUES (%s,%s,0,0) ON CONFLICT (user_id,coin) DO NOTHING", (user_id, coin))
            if action == "set_balance":
                cur.execute("UPDATE user_balances SET balance=GREATEST(0,%s) WHERE user_id=%s AND coin=%s", (value, user_id, coin))
            elif action == "add_balance":
                cur.execute("UPDATE user_balances SET balance=GREATEST(0,balance+%s) WHERE user_id=%s AND coin=%s", (value, user_id, coin))
            elif action == "set_hold":
                cur.execute("UPDATE user_balances SET hold=GREATEST(0,%s) WHERE user_id=%s AND coin=%s", (value, user_id, coin))
            elif action == "add_hold":
                cur.execute("UPDATE user_balances SET hold=GREATEST(0,hold+%s) WHERE user_id=%s AND coin=%s", (value, user_id, coin))
            db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


# ── Withdrawals ───────────────────────────────────────────────────────────────

@app.route("/withdrawals")
@require_owner
def withdrawals_page():
    status = request.args.get("status", "all")
    coin   = request.args.get("coin",   "all")
    db = get_db()
    try:
        with db.cursor() as cur:
            q = "SELECT * FROM withdrawals WHERE 1=1"
            p = []
            if status != "all": q += " AND status=%s"; p.append(status)
            if coin   != "all": q += " AND method=%s"; p.append(coin)
            q += " ORDER BY created_at DESC LIMIT 300"
            cur.execute(q, p); wds = cur.fetchall()
            totals = {c: {"pending": 0, "paid": 0} for c in COIN_ORDER}
            for w in wds:
                m = w["method"]
                if m in totals:
                    if w["status"] == "pending": totals[m]["pending"] += w["amount"] or 0
                    elif w["status"] in ("approved","paid"): totals[m]["paid"] += w["amount"] or 0
    finally:
        db.close()
    return render_template("withdrawals.html", withdrawals=wds, status=status, coin=coin, totals=totals, fmt_coin=fmt_coin)

@app.route("/withdrawals/<int:wid>/action", methods=["POST"])
@require_owner
def wd_action(wid):
    action = request.form.get("action", "")
    note   = request.form.get("note", "").strip()
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM withdrawals WHERE id=%s", (wid,))
            wd = cur.fetchone()
            if not wd or wd["status"] != "pending":
                return jsonify({"ok": False, "error": "Not pending or not found"})
            if action == "approve":
                cur.execute("SELECT balance FROM user_balances WHERE user_id=%s AND coin=%s", (wd["user_id"], wd["method"]))
                bal = cur.fetchone()
                if not bal or (bal["balance"] or 0) < (wd["amount"] or 0):
                    return jsonify({"ok": False, "error": "Insufficient balance"})
                cur.execute("UPDATE user_balances SET balance=GREATEST(0,balance-%s) WHERE user_id=%s AND coin=%s",
                            (wd["amount"], wd["user_id"], wd["method"]))
                cur.execute("UPDATE withdrawals SET status='approved', note=%s, updated_at=%s WHERE id=%s",
                            (note, datetime.utcnow().isoformat(), wid))
            elif action == "reject":
                cur.execute("UPDATE withdrawals SET status='rejected', note=%s, updated_at=%s WHERE id=%s",
                            (note, datetime.utcnow().isoformat(), wid))
            db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


# ── Deposits ──────────────────────────────────────────────────────────────────

@app.route("/deposits")
@require_owner
def deposits_page():
    status = request.args.get("status", "all")
    db = get_db()
    try:
        with db.cursor() as cur:
            q = "SELECT * FROM deposits WHERE 1=1"
            p = []
            if status != "all": q += " AND status=%s"; p.append(status)
            q += " ORDER BY created_at DESC LIMIT 200"
            cur.execute(q, p); deposits = cur.fetchall()
    finally:
        db.close()
    return render_template("deposits.html", deposits=deposits, status=status, fmt_coin=fmt_coin)

@app.route("/deposits/<int:dep_id>/approve", methods=["POST"])
@require_owner
def approve_deposit(dep_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM deposits WHERE id=%s", (dep_id,))
            dep = cur.fetchone()
            if not dep or dep["status"] != "pending":
                return jsonify({"ok": False, "error": "Not found or already handled"})
            cur.execute("UPDATE deposits SET status='approved', updated_at=%s WHERE id=%s",
                        (datetime.utcnow().isoformat(), dep_id))
            cur.execute("INSERT INTO user_balances (user_id,coin,balance) VALUES (%s,%s,0) ON CONFLICT (user_id,coin) DO NOTHING",
                        (dep["user_id"], dep["method"]))
            cur.execute("UPDATE user_balances SET balance=GREATEST(0,balance+%s) WHERE user_id=%s AND coin=%s",
                        (dep["net_amount"] or dep["method_amount"], dep["user_id"], dep["method"]))
            db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})

@app.route("/deposits/<int:dep_id>/reject", methods=["POST"])
@require_owner
def reject_deposit(dep_id):
    db_execute("UPDATE deposits SET status='rejected', updated_at=%s WHERE id=%s",
               (datetime.utcnow().isoformat(), dep_id))
    return jsonify({"ok": True})


# ── Authorised ────────────────────────────────────────────────────────────────

@app.route("/authorised")
@require_owner_only
def authorised_page():
    authorised = db_fetchall("SELECT * FROM authorised_users ORDER BY added_at DESC")
    return render_template("authorised.html", authorised=authorised)

@app.route("/authorised/add", methods=["POST"])
@require_owner_only
def authorised_add():
    user_id  = request.form.get("user_id",  "").strip()
    username = request.form.get("username", "").strip()
    if not user_id.isdigit():
        return jsonify({"ok": False, "error": "Invalid Discord user ID"})
    db_execute(
        "INSERT INTO authorised_users (user_id,username,added_by) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username",
        (user_id, username, str(session["user"]["id"]))
    )
    return jsonify({"ok": True})

@app.route("/authorised/<user_id>/remove", methods=["POST"])
@require_owner_only
def authorised_remove(user_id):
    db_execute("DELETE FROM authorised_users WHERE user_id=%s", (user_id,))
    return jsonify({"ok": True})


# ── Servers ───────────────────────────────────────────────────────────────────

@app.route("/servers")
@require_owner
def servers_page():
    servers = db_fetchall("SELECT * FROM bot_guilds ORDER BY joined_at DESC")
    return render_template("servers.html", servers=servers)


# ── Tickets ───────────────────────────────────────────────────────────────────

@app.route("/tickets")
@require_owner
def tickets_page():
    status = request.args.get("status", "all")
    ttype  = request.args.get("type",   "all")
    db = get_db()
    try:
        with db.cursor() as cur:
            q = "SELECT * FROM tickets WHERE 1=1"; p = []
            if status != "all": q += " AND status=%s"; p.append(status)
            if ttype  != "all": q += " AND type=%s";   p.append(ttype)
            q += " ORDER BY created_at DESC LIMIT 200"
            cur.execute(q, p); tickets = cur.fetchall()
    finally:
        db.close()
    return render_template("tickets.html", tickets=tickets, status=status, ttype=ttype)


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings")
@require_owner
def settings_page():
    guilds          = db_fetchall("SELECT * FROM guilds")
    det_rows        = db_fetchall("SELECT coin, method FROM detection_settings")
    wd_rows         = db_fetchall("SELECT coin, method FROM withdraw_settings")
    detection       = {r["coin"]: r["method"] for r in det_rows}
    withdraw_methods = {r["coin"]: r["method"] for r in wd_rows}
    return render_template("settings.html", guilds=guilds, detection=detection, withdraw_methods=withdraw_methods)

@app.route("/settings/method", methods=["POST"])
@require_owner_only
def update_method():
    coin   = request.form.get("coin",   "")
    kind   = request.form.get("kind",   "")
    method = request.form.get("method", "")
    if coin not in COINS:
        return jsonify({"ok": False, "error": "Invalid coin"})
    table = "detection_settings" if kind == "detection" else "withdraw_settings"
    db_execute(
        f"INSERT INTO {table} (coin,method) VALUES (%s,%s) ON CONFLICT (coin) DO UPDATE SET method=EXCLUDED.method",
        (coin, method)
    )
    return jsonify({"ok": True})


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.route("/logs")
@require_owner
def logs_page():
    action_filter = request.args.get("action", "").strip()
    user_filter   = request.args.get("user",   "").strip()
    db = get_db()
    try:
        with db.cursor() as cur:
            q = "SELECT * FROM logs WHERE 1=1"; p = []
            if action_filter: q += " AND action=%s";          p.append(action_filter)
            if user_filter:   q += " AND user_id ILIKE %s";  p.append(f"%{user_filter}%")
            q += " ORDER BY created_at DESC LIMIT 500"
            cur.execute(q, p); logs = cur.fetchall()
            cur.execute("SELECT DISTINCT action FROM logs ORDER BY action")
            actions = cur.fetchall()
    finally:
        db.close()
    return render_template("logs.html", logs=logs, actions=actions, action_filter=action_filter, user_filter=user_filter)


# ── Giveaways ─────────────────────────────────────────────────────────────────

@app.route("/giveaways")
@require_owner
def giveaways_page():
    giveaways = db_fetchall("SELECT * FROM giveaways ORDER BY created_at DESC LIMIT 100")
    return render_template("giveaways.html", giveaways=giveaways)


# ── Backup ────────────────────────────────────────────────────────────────────

@app.route("/backup/export")
@require_owner_only
def backup_export():
    tables = ["guilds","users","user_balances","authorised_users","withdrawals","deposits",
              "tickets","tasks","giveaways","hold_entries","rains","logs","subscriptions","bot_guilds"]
    backup = {"generated_at": datetime.utcnow().isoformat(), "tables": {}}
    for t in tables:
        try:
            backup["tables"][t] = [dict(r) for r in db_fetchall(f"SELECT * FROM {t}")]
        except Exception:
            backup["tables"][t] = []
    payload = json.dumps(backup, indent=2, default=str)
    return Response(
        payload, mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=xwallet_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"}
    )


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
@require_owner
def api_stats():
    db = get_db()
    try:
        with db.cursor() as cur:
            data = {}
            for k, q in [
                ("users",        "SELECT COUNT(*) as c FROM users"),
                ("pending_wd",   "SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'"),
                ("pending_dep",  "SELECT COUNT(*) as c FROM deposits WHERE status='pending'"),
                ("open_tickets", "SELECT COUNT(*) as c FROM tickets WHERE status='open'"),
            ]:
                cur.execute(q); data[k] = cur.fetchone()["c"]
    finally:
        db.close()
    return jsonify(data)


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
