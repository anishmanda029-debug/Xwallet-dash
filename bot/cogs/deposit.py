"""
XWALLET Deposit Cog
- No sender address required
- Delayed credit (DEPOSIT_CREDIT_DELAY_MINUTES)
- Rich invoice with QR code, gas fee, address emoji
- /history command (combined deposit + withdraw history)
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio, os, io
from datetime import datetime, timedelta

from bot.utils.database import (
    ensure_user, create_invoice, get_invoice, get_user_invoices,
    get_user_deposits, get_user_withdrawals,
    add_log, update_balance,
)
from bot.utils.embeds import (
    E, S, DIV, COLOR, embed_error, embed_processing, embed_success,
    fmt_coin, get_usd_price, get_all_usd_prices, coin_emoji
)
from bot.utils.checks import is_authorised_or_owner
from bot.utils.currency import validate_amount
from bot.utils.coins import COINS, ORDER, label as coin_label, symbol
from bot.utils.addresses import DEPOSIT_ADDRESSES

import logging
log = logging.getLogger("XWALLET.deposit")

CREDIT_DELAY   = int(os.getenv("DEPOSIT_CREDIT_DELAY_MINUTES", "15"))
PLATFORM_FEE   = float(os.getenv("DEPOSIT_PLATFORM_FEE_USD", "0.00"))  # extra USD fee added to invoice
NETWORK_FEES   = {
    "btc":       float(os.getenv("BTC_NETWORK_FEE",       "0.0001")),
    "ltc":       float(os.getenv("LTC_NETWORK_FEE",       "0.001")),
    "eth":       float(os.getenv("ETH_NETWORK_FEE",       "0.002")),
    "sol":       float(os.getenv("SOL_NETWORK_FEE",       "0.000005")),
    "usdterc20": float(os.getenv("USDTERC20_NETWORK_FEE", "0.003")),
    "usdttrc20": float(os.getenv("USDTTRC20_NETWORK_FEE", "1.0")),
}

EXPLORER = {
    "btc":       lambda a: f"https://mempool.space/address/{a}",
    "ltc":       lambda a: f"https://blockchair.com/litecoin/address/{a}",
    "eth":       lambda a: f"https://etherscan.io/address/{a}",
    "sol":       lambda a: f"https://solscan.io/account/{a}",
    "usdterc20": lambda a: f"https://etherscan.io/address/{a}",
    "usdttrc20": lambda a: f"https://tronscan.org/#/address/{a}",
}


def _qr_bytes(data: str) -> bytes | None:
    """Generate QR PNG bytes. Returns None if qrcode not installed."""
    try:
        import qrcode, io as _io
        qr = qrcode.QRCode(box_size=6, border=3)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def _invoice_embed(
    invoice_id: int, coin: str, coin_amount: float,
    usd_amount: float, deposit_addr: str, price: float,
    network_fee: float, network: str = "mainnet",
) -> discord.Embed:
    ts         = datetime.utcnow().strftime("%-d %b %Y, %H:%M UTC")
    net_label  = network.upper()
    explorer   = EXPLORER.get(coin, lambda a: "#")(deposit_addr)
    total_coin = round(coin_amount + network_fee, 8)
    total_usd  = round(usd_amount + (network_fee * price), 4)

    desc = (
        f"{DIV}\n"
        f"{E['history']} **Invoice ID** {S['bullet']} `#{invoice_id}`\n"
        f"{coin_emoji(coin)} **Coin** {S['bullet']} `{symbol(coin)} — {COINS[coin]['label']}`\n"
        f"{E['server']} **Network** {S['bullet']} `{net_label}`\n"
        f"{DIV}\n"
        f"{E['payment']} **Amount (USD)** {S['bullet']} `${usd_amount:,.2f}`\n"
        f"📊 **Live Price** {S['bullet']} `1 {symbol(coin)} = ${price:,.4f}`\n"
        f"{E['payment']} **Network Fee** {S['bullet']} `{network_fee:.8f} {symbol(coin)}`\n"
        f"{E['balance']} **Total to Send** {S['bullet']} `{total_coin:.8f} {symbol(coin)}` (~`${total_usd:,.4f}`)\n"
        f"{DIV}\n"
        f"{E['address']} **Deposit Address**\n"
        f"```\n{deposit_addr}\n```\n"
        f"[🔍 View on Explorer]({explorer})\n"
        f"{DIV}\n"
        f"{E['time']} Credits after **{CREDIT_DELAY} min** of confirmation\n"
        f"{E['tick']} Send the **exact amount** shown above\n"
        f"⚠️ Do **not** send from an exchange — use a personal wallet\n"
        f"{E['time']} **Issued** {S['bullet']} {ts}\n"
        f"{DIV}"
    )
    em = discord.Embed(
        title=f"{E['history']} Deposit Invoice #{invoice_id}",
        description=desc,
        color=COLOR["info"],
    )
    em.set_footer(text=f"XWALLET • Invoice #{invoice_id} • Keep this for your records")
    return em


# ── Copy Address Button (only address, no extra text) ────────────────────────

class CopyAddressButton(discord.ui.Button):
    def __init__(self, address: str):
        super().__init__(label="{E['history']} Copy Address", style=discord.ButtonStyle.secondary, row=0)
        self.address = address

    async def callback(self, interaction: discord.Interaction):
        # Only the raw address — no embed, no extra text
        await interaction.response.send_message(f"`{self.address}`", ephemeral=True)


class CoinSelect(discord.ui.Select):
    def __init__(self, uid: str):
        self.uid = uid
        options = [
            discord.SelectOption(
                label=f"{COINS[c]['label']} ({symbol(c)})",
                value=c,
                emoji=None
            )
            for c in ORDER
        ]
        super().__init__(placeholder="Choose a coin to deposit…", options=options)

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.uid:
            return await interaction.response.send_message(embed=embed_error("Not Yours", ""), ephemeral=True)
        await interaction.response.send_modal(DepositUSDModal(self.values[0]))


class CoinSelectView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=180)
        self.add_item(CoinSelect(uid))


class DepositUSDModal(discord.ui.Modal):
    def __init__(self, coin: str):
        super().__init__(title=f"Deposit — {symbol(coin)}")
        self.coin = coin
        self.usd_input = discord.ui.TextInput(
            label="Amount in USD ($)",
            placeholder="e.g. 25",
            min_length=1, max_length=12,
        )
        self.add_item(self.usd_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid  = str(interaction.user.id)
        coin = self.coin

        try:
            usd_amount = float(self.usd_input.value.strip().replace("$", "").replace(",", ""))
        except ValueError:
            return await interaction.followup.send(
                embed=embed_error("Invalid Amount", "Enter a number like `25` or `25.50`."), ephemeral=True
            )
        if usd_amount <= 0:
            return await interaction.followup.send(
                embed=embed_error("Invalid Amount", "Must be greater than zero."), ephemeral=True
            )

        price = await get_usd_price(coin)
        if price <= 0:
            return await interaction.followup.send(
                embed=embed_error("Price Unavailable", "Couldn't fetch live price — try again shortly."), ephemeral=True
            )

        coin_amount  = round(usd_amount / price, 8)
        network_fee  = NETWORK_FEES.get(coin, 0.0)
        deposit_addr = DEPOSIT_ADDRESSES.get(coin, "Not configured")
        network      = os.getenv("NETWORK", "mainnet")
        invoice_id   = await create_invoice(uid, coin, usd_amount, coin_amount, "", deposit_addr)

        invoice_em   = _invoice_embed(invoice_id, coin, coin_amount, usd_amount, deposit_addr, price, network_fee, network)

        view = discord.ui.View(timeout=None)
        if deposit_addr and "Not configured" not in deposit_addr:
            view.add_item(CopyAddressButton(deposit_addr))

        # Try QR code
        qr_bytes = _qr_bytes(deposit_addr)
        if qr_bytes:
            file = discord.File(io.BytesIO(qr_bytes), filename="deposit_qr.png")
            invoice_em.set_image(url="attachment://deposit_qr.png")
            await interaction.followup.send(embed=invoice_em, view=view, file=file, ephemeral=True)
        else:
            await interaction.followup.send(embed=invoice_em, view=view, ephemeral=True)

        await add_log("DEPOSIT", uid, "INVOICE_CREATED", f"#{invoice_id} {coin} ${usd_amount}")


# ── Delayed Credit Task ───────────────────────────────────────────────────────

async def _process_pending_credits(bot):
    try:
        from bot.utils.database import _fetchall, _execute
        cutoff = (datetime.utcnow() - timedelta(minutes=CREDIT_DELAY)).strftime("%Y-%m-%d %H:%M:%S")
        rows = await _fetchall(
            "SELECT id, user_id, coin, coin_amount FROM invoices "
            "WHERE status='awaiting_credit' AND payment_detected_at <= ?",
            (cutoff,),
        )
        for row in rows:
            try:
                await update_balance(row["user_id"], row["coin"], row["coin_amount"])
                await _execute(
                    "UPDATE invoices SET status='paid', credited_at=? WHERE id=?",
                    (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), row["id"]),
                )
                user = bot.get_user(int(row["user_id"]))
                if user:
                    try:
                        await user.send(embed=discord.Embed(
                            title="{E['tick']} Deposit Credited!",
                            description=(
                                f"{DIV}\n"
                                f"{E['history']} **Invoice** {S['bullet']} `#{row['id']}`\n"
                                f"{coin_emoji(row['coin'])} **Credited** {S['bullet']} {fmt_coin(row['coin_amount'], row['coin'])}\n"
                                f"{E['tick']} Your balance has been updated.\n"
                                f"{DIV}"
                            ),
                            color=COLOR["success"],
                        ))
                    except Exception:
                        pass
            except Exception as exc:
                log.error(f"[CREDIT] Invoice #{row['id']} failed: {exc}")
    except Exception as exc:
        log.warning(f"[CREDIT TASK] {exc}")


# ── /history — Combined deposit + withdraw history ────────────────────────────

async def _history_embed(user: discord.User) -> discord.Embed:
    uid  = str(user.id)
    deps = await get_user_deposits(uid)
    wds  = await get_user_withdrawals(uid)

    entries = []
    for d in (deps or []):
        status = d.get("status", "?")
        icon   = "✅" if status == "approved" else "⏳" if status in ("pending", "pending_chain") else "❌"
        method = d.get("method", "?").upper()
        amt    = d.get("net_amount") or d.get("method_amount") or 0
        entries.append({
            "type": "dep",
            "icon": f"{E['deposit']} {icon}",
            "line": f"{E['deposit']} {icon} **Deposit** {S['bullet']} `{method}` {S['bullet']} `{amt:.6f}` {S['bullet']} `{status}`",
            "ts":   d.get("created_at", ""),
        })
    for w in (wds or []):
        status = w.get("status", "?")
        icon   = "✅" if status in ("approved", "paid", "sent") else "⏳" if status == "pending" else "❌"
        method = w.get("method", "?").upper()
        amt    = w.get("net_amount") or w.get("amount") or 0
        entries.append({
            "type": "wd",
            "icon": f"{E['withdraw']} {icon}",
            "line": f"{E['withdraw']} {icon} **Withdraw** {S['bullet']} `{method}` {S['bullet']} `{amt:.6f}` {S['bullet']} `{status}`",
            "ts":   w.get("created_at", ""),
        })

    entries.sort(key=lambda x: x["ts"], reverse=True)

    if not entries:
        desc = f"{DIV}\n💸 No transaction history yet.\n{DIV}"
    else:
        lines = [e["line"] for e in entries[:15]]
        desc  = f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}"

    em = discord.Embed(title=f"{E['history']} Transaction History — {user.display_name}", description=desc, color=COLOR["info"])
    em.set_footer(text=f"{E['deposit']} = Deposit  |  📤 = Withdraw  |  Showing last {min(15, len(entries))} entries")
    return em


# ── Cog ───────────────────────────────────────────────────────────────────────

class Deposit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._credit_task.start()

    def cog_unload(self):
        self._credit_task.cancel()

    @tasks.loop(minutes=2)
    async def _credit_task(self):
        await _process_pending_credits(self.bot)

    @_credit_task.before_loop
    async def _before_credit(self):
        await self.bot.wait_until_ready()

    # ── /deposit ──────────────────────────────────────────────────────────────
    @app_commands.command(name="deposit", description="{E['payment']} Deposit crypto into your wallet")
    async def deposit(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        await interaction.response.defer(ephemeral=True)
        try:
            dm = await interaction.user.send(embed=embed_processing("Loading deposit panel…"))
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=embed_error("DMs Closed", "Enable DMs from server members and try again."), ephemeral=True
            )
        await asyncio.sleep(0.4)
        await dm.edit(embed=_coin_select_embed(), view=CoinSelectView(uid))
        try: await interaction.delete_original_response()
        except Exception: pass

    @commands.command(name="dep")
    async def depo_prefix(self, ctx):
        """Open deposit panel in DMs."""
        uid = str(ctx.author.id)
        await ensure_user(uid, ctx.author.name)
        if ctx.guild:
            try: await ctx.message.delete()
            except Exception: pass
        try:
            dm = await ctx.author.send(embed=embed_processing("Loading deposit panel…"))
        except discord.Forbidden:
            return
        await asyncio.sleep(0.4)
        await dm.edit(embed=_coin_select_embed(), view=CoinSelectView(uid))

    # ── /history (replaces /invoices) ─────────────────────────────────────────
    @app_commands.command(name="history", description="{E['history']} View your deposit and withdrawal history")
    async def history(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        em = await _history_embed(interaction.user)
        await interaction.followup.send(embed=em, ephemeral=True)

    @commands.command(name="history", aliases=["txs", "transactions", "hist"])
    async def history_prefix(self, ctx, user: discord.Member = None):
        """View transaction history."""
        target = user or ctx.author
        if user and not _is_staff_ctx(ctx):
            target = ctx.author
        em = await _history_embed(target)
        await ctx.send(embed=em)


def _coin_select_embed():
    lines = [f"{coin_emoji(c)} **{COINS[c]['label']}** {S['bullet']} `{symbol(c)}`" for c in ORDER]
    desc  = f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}\nChoose which coin you'd like to deposit."
    return discord.Embed(title="{E['deposit']} XWALLET Deposit", description=desc, color=COLOR["primary"])

def _is_staff_ctx(ctx) -> bool:
    from bot.utils.checks import STAFF_IDS
    return ctx.author.id in STAFF_IDS or (ctx.guild and ctx.author.guild_permissions.administrator)


async def setup(bot):
    await bot.add_cog(Deposit(bot))
