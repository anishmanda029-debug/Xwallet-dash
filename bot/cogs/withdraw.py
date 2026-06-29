"""
XWALLET Withdraw Cog — /withdraw (DM-only).
User declares a USD amount and payout address.

Three payout methods, toggleable per-coin via /setwithdrawmethod:
  - manual     (default): approve → authorised member pays from own wallet → mark paid.
  - automatic  : bot signs + broadcasts instantly on approval. Requires *_PRIVATE_KEY env vars.
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from bot.utils.database import (
    ensure_user, get_user, get_all_balances, update_balance,
    create_withdrawal, get_withdrawal, update_withdrawal_status,
    get_user_withdrawals, withdrawal_amount, get_pending_withdrawals,
    get_authorised_users, add_log, declare_sender_address,
)
from bot.utils.embeds import (
    E, S, DIV, COLOR,
    embed_error, embed_processing, embed_success,
    fmt_coin, coin_to_usd_str, get_usd_price, coin_emoji,
)
from bot.utils.checks import is_authorised_or_owner, OWNER_ID
from bot.utils.currency import calc_fee, calc_net, validate_amount
from bot.utils.coins import COINS, ORDER, symbol, address_hint
import logging

log = logging.getLogger("XWALLET.withdraw")


# ── Auto-withdraw-capable coins ───────────────────────────────────────────────
AUTO_COINS = {"btc", "ltc", "eth", "sol"}


def validate_address(coin: str, addr: str) -> bool:
    if not addr or len(addr) < 8:
        return False
    if coin == "btc":
        return addr.startswith(("1", "3", "bc1"))
    if coin == "ltc":
        return addr.startswith(("L", "M", "3", "ltc1"))
    if coin in ("eth", "usdterc20"):
        return addr.startswith("0x") and len(addr) == 42
    if coin == "sol":
        return 32 <= len(addr) <= 44 and addr.isalnum()
    if coin == "usdttrc20":
        return addr.startswith("T") and len(addr) == 34
    return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def coin_select_embed():
    lines = [
        f"{coin_emoji(c)} **{COINS[c]['label']}** {S['bullet']} `{symbol(c)}`"
        for c in ORDER
    ]
    desc = f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}\nChoose which coin you'd like to withdraw."
    return discord.Embed(
        title=f"{E['withdraw']} XWALLET Withdraw",
        description=desc,
        color=COLOR["primary"],
    )


def _confirm_embed(coin: str, from_addr: str, to_addr: str, net: float, txid: str) -> discord.Embed:
    """Rich withdrawal confirmation invoice sent to user on payout."""
    from datetime import datetime
    import os
    ts = datetime.utcnow().strftime("%-d %b %Y, %H:%M UTC")
    explorer = _explorer_url(coin, txid)
    fee_coin = net * 0.02  # cosmetic display — real fee already deducted
    desc = (
        f"{DIV}\n"
        f"{E['history']} **Withdrawal Receipt**\n"
        f"{DIV}\n"
        f"{coin_emoji(coin)} **Coin** {S['bullet']} `{symbol(coin)} — {COINS[coin]['label']}`\n"
        f"{E['payment']} **Net Received** {S['bullet']} `{fmt_coin(net, coin)}`\n"
        f"{E['payment']} **Network Fee** {S['bullet']} `{fmt_coin(fee_coin, coin)}` (deducted)\n"
        f"{DIV}\n"
        f"{E['withdraw']} **From** {S['bullet']} `{from_addr[:20]}…`\n"
        f"{E['address']} **To Address**\n"
        f"```\n{to_addr}\n```\n"
        f"🔗 **Transaction**\n"
        f"```\n{txid}\n```\n"
        f"[🔍 View on Explorer]({explorer})\n"
        f"{DIV}\n"
        f"{E['time']} May take **1–4 hours** to appear in your wallet\n"
        f"{E['time']} **Completed** {S['bullet']} {ts}\n"
        f"{DIV}"
    )
    return discord.Embed(
        title="{E['tick']} Withdrawal Complete",
        description=desc,
        color=COLOR["success"],
    )


def _explorer_url(coin: str, txid: str) -> str:
    mapping = {
        "btc": f"https://mempool.space/tx/{txid}",
        "ltc": f"https://blockchair.com/litecoin/transaction/{txid}",
        "eth": f"https://etherscan.io/tx/{txid}",
        "sol": f"https://solscan.io/tx/{txid}",
    }
    return mapping.get(coin, "#")


async def _get_hot_wallet_address(coin: str) -> str:
    mapping = {
        "btc": os.getenv("BTC_ADDRESS", ""),
        "ltc": os.getenv("LTC_ADDRESS", ""),
        "eth": os.getenv("ETH_ADDRESS", ""),
        "sol": os.getenv("SOL_ADDRESS", ""),
    }
    return mapping.get(coin, "unknown")


async def _notify_withdraw_channels(bot: discord.Client, embed: discord.Embed):
    """Post to every guild's withdraw_log channel."""
    try:
        from bot.utils.database import get_all_guilds
        guilds = await get_all_guilds()
        for g in guilds:
            ch_id = g.get("withdraw_log")
            if not ch_id:
                continue
            ch = bot.get_channel(int(ch_id))
            if ch:
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass
    except Exception as exc:
        log.warning(f"[WITHDRAW] channel notify failed: {exc}")


# ── UI: Coin select ───────────────────────────────────────────────────────────

class CoinSelectWithdraw(discord.ui.Select):
    def __init__(self, uid: str):
        self.uid = uid
        options = [
            discord.SelectOption(label=f"{COINS[c]['label']} ({symbol(c)})", value=c)
            for c in ORDER
        ]
        super().__init__(
            placeholder="Choose a coin to withdraw…",
            options=options,
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.uid:
            return await interaction.response.send_message(
                embed=embed_error("Not Yours", ""), ephemeral=True
            )
        await interaction.response.send_modal(WithdrawUSDModal(self.values[0]))


class StartWithdrawView(discord.ui.View):
    def __init__(self, uid: str):
        super().__init__(timeout=180)
        self.add_item(CoinSelectWithdraw(uid))


# ── Modal: amount + address ───────────────────────────────────────────────────

class WithdrawUSDModal(discord.ui.Modal):
    def __init__(self, coin: str):
        super().__init__(title=f"Withdraw — {symbol(coin)}")
        self.coin = coin
        self.usd_amount = discord.ui.TextInput(
            label="Amount in USD ($)",
            placeholder="e.g. 25",
            min_length=1, max_length=12,
        )
        self.address = discord.ui.TextInput(
            label=f"Your {symbol(coin)} payout address",
            placeholder=address_hint(coin),
            min_length=5,
        )
        self.add_item(self.usd_amount)
        self.add_item(self.address)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid  = str(interaction.user.id)
        coin = self.coin

        # ── Parse amount ──────────────────────────────────────────────────────
        try:
            usd_amount = float(self.usd_amount.value.strip().replace("$", ""))
        except ValueError:
            return await interaction.followup.send(
                embed=embed_error("Invalid Amount", "Enter a number like 25 or 25.50."),
                ephemeral=True,
            )
        if usd_amount <= 0:
            return await interaction.followup.send(
                embed=embed_error("Invalid Amount", "Must be greater than zero."),
                ephemeral=True,
            )

        price = await get_usd_price(coin)
        if price <= 0:
            return await interaction.followup.send(
                embed=embed_error("Price Unavailable", "Couldn't fetch a live price — try again shortly."),
                ephemeral=True,
            )
        amount = round(usd_amount / price, 8)

        ok, msg_txt = await validate_amount(coin, amount)
        if not ok:
            return await interaction.followup.send(
                embed=embed_error("Below Minimum", msg_txt), ephemeral=True
            )

        # ── Check balance ─────────────────────────────────────────────────────
        balances = await get_all_balances(uid)
        bal = balances.get(coin, {}).get("balance", 0) or 0
        if amount > bal:
            return await interaction.followup.send(
                embed=embed_error(
                    "Insufficient Funds",
                    f"Balance: {fmt_coin(bal, coin)} (~{await coin_to_usd_str(bal, coin)})",
                ),
                ephemeral=True,
            )

        # ── Validate address ──────────────────────────────────────────────────
        addr = self.address.value.strip()
        if not validate_address(coin, addr):
            return await interaction.followup.send(
                embed=embed_error(
                    f"Invalid {symbol(coin)} Address",
                    f"Expected format: {address_hint(coin)}",
                ),
                ephemeral=True,
            )

        # Bind payout address
        await declare_sender_address(coin, addr, uid)

        fee = calc_fee(amount)
        net = calc_net(amount)

        # ── Check auto-withdraw limits ────────────────────────────────────────
        from bot.utils.database import get_withdraw_method
        method = await get_withdraw_method(coin)

        if method == "automatic":
            if coin not in AUTO_COINS:
                return await interaction.followup.send(
                    embed=embed_error(
                        "Auto-Withdraw Unsupported",
                        f"{symbol(coin)} doesn't support automatic withdrawals yet. Ask the owner to switch to manual.",
                    ),
                    ephemeral=True,
                )
            from bot.services.auto_withdraw import check_limits
            ok_limits, limit_msg = await check_limits(uid, usd_amount)
            if not ok_limits:
                return await interaction.followup.send(
                    embed=embed_error("Limit Exceeded", limit_msg), ephemeral=True
                )

        # ── Loading steps ─────────────────────────────────────────────────────
        steps = [
            f"{E['loading']} Validating request…",
            f"{E['loading']} Submitting to queue…",
            f"{E['loading']} Notifying authorised members…",
        ]
        msg = await interaction.followup.send(
            embed=discord.Embed(description=steps[0], color=COLOR["processing"]),
            ephemeral=True,
        )
        for step in steps[1:]:
            await asyncio.sleep(0.5)
            await msg.edit(embed=discord.Embed(description=step, color=COLOR["processing"]))

        wid = await create_withdrawal(uid, "DM", coin, addr, amount, fee=fee, net_amount=net, usd_value=usd_amount)

        usd_str = f"${usd_amount:,.2f}"

        # ── If AUTOMATIC: execute right away, no approval needed ──────────────
        if method == "automatic":
            await msg.edit(embed=discord.Embed(
                description=f"{E['loading']} Signing transaction on-chain…",
                color=COLOR["processing"],
            ))
            try:
                from bot.services.auto_withdraw import execute_auto_withdraw
                txid = await execute_auto_withdraw(coin, addr, amount, uid, wid)
            except Exception as exc:
                log.error(f"[AUTO_WITHDRAW] wid#{wid} failed: {exc}")
                await update_withdrawal_status(wid, "rejected", f"auto-broadcast failed: {exc}", handled_by="BOT_AUTO")
                return await msg.edit(embed=embed_error(
                    "Withdrawal Failed",
                    f"Transaction could not be broadcast: `{exc}`\n\nYour balance was **not deducted**.",
                ))

            hot_addr = await _get_hot_wallet_address(coin)
            confirm_embed = _confirm_embed(coin, hot_addr, addr, net, txid)
            await msg.edit(embed=confirm_embed)

            # Log to withdraw channels
            log_embed = discord.Embed(
                title=f"{E['withdraw']} Auto-Withdrawal Sent",
                description=(
                    f"{DIV}\n"
                    f"{E['id']} **Withdrawal** {S['bullet']} `#{wid}`\n"
                    f"{E['profile']} **User** {S['bullet']} <@{uid}> (`{uid}`)\n"
                    f"{coin_emoji(coin)} **Coin** {S['bullet']} `{symbol(coin)}`\n"
                    f"{E['balance']} **Amount** {S['bullet']} {usd_str} {S['double']} {fmt_coin(amount, coin)}\n"
                    f"{E['tick']} **Net Sent** {S['bullet']} {fmt_coin(net, coin)}\n"
                    f"{E['address']} **To** {S['bullet']} `{addr}`\n"
                    f"{E['id']} **TXID** {S['bullet']} `{txid}`\n"
                    f"{DIV}"
                ),
                color=COLOR["success"],
            )
            await _notify_withdraw_channels(interaction.client, log_embed)
            await add_log("DM", uid, "WITHDRAW_REQ", f"#{wid} ${usd_amount} {coin} auto txid:{txid}")
            return

        # ── MANUAL mode: submit for approval ─────────────────────────────────
        success_desc = (
            f"{DIV}\n"
            f"{E['history']} **Request ID** {S['bullet']} `#{wid}`\n"
            f"{coin_emoji(coin)} **Coin** {S['bullet']} `{symbol(coin)} — {COINS[coin]['label']}`\n"
            f"{E['payment']} **Amount** {S['bullet']} `{usd_str}` {S['double']} {fmt_coin(amount, coin)}\n"
            f"{E['payment']} **Fee** {S['bullet']} deducted on payout\n"
            f"{E['tick']} **You'll Receive** {S['bullet']} {fmt_coin(net, coin)}\n"
            f"{DIV}\n"
            f"{E['address']} **Payout Address**\n"
            f"```\n{addr}\n```\n"
            f"{DIV}\n"
            f"{E['time']} **Status** {S['bullet']} Pending Review\n"
            f"💬 An authorised member will process your withdrawal shortly.\n"
            f"{DIV}"
        )
        await msg.edit(embed=discord.Embed(
            title=f"{E['tick']} Withdrawal Submitted",
            description=success_desc,
            color=COLOR["success"],
        ))

        # Notify owner + authorised members
        recipients = {OWNER_ID} | {int(a["user_id"]) for a in await get_authorised_users()}
        owner_desc = (
            f"{DIV}\n{E['profile']} **User** {S['bullet']} {interaction.user.mention} (`{uid}`)\n"
            f"{coin_emoji(coin)} **Coin** {S['bullet']} `{symbol(coin)}`\n"
            f"{E['balance']} **Amount** {S['bullet']} {usd_str} {S['double']} {fmt_coin(amount, coin)}\n"
            f"{E['tick']} **Net Payout** {S['bullet']} {fmt_coin(net, coin)}\n"
            f"{E['secure']} **Address** {S['bullet']} `{addr}`\n"
            f"{E['id']} **ID** {S['bullet']} `#{wid}`\n{DIV}\n"
            f"Use `/pendingwithdrawals` to approve, then pay manually from your wallet and mark paid."
        )
        for rid in recipients:
            try:
                user = interaction.client.get_user(rid) or await interaction.client.fetch_user(rid)
                await user.send(
                    embed=discord.Embed(
                        title=f"{E['notify']} New Withdrawal Request",
                        description=owner_desc,
                        color=COLOR["warning"],
                    ),
                    view=ApprovalView(wid, uid, coin, amount, net, addr),
                )
            except Exception:
                pass

        await add_log("DM", uid, "WITHDRAW_REQ", f"#{wid} ${usd_amount} {coin}")


# ── Approval UI (manual mode only) ───────────────────────────────────────────

class ApprovalView(discord.ui.View):
    def __init__(self, wid: int, user_id: str, coin: str, amount: float, net: float, address: str):
        super().__init__(timeout=None)
        self.wid = wid
        self.user_id = user_id
        self.coin = coin
        self.amount = amount
        self.net = net
        self.address = address

    async def _check(self, interaction: discord.Interaction) -> bool:
        if not await is_authorised_or_owner(interaction.user.id):
            await interaction.response.send_message(
                embed=embed_error("Not Authorised", ""), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        await interaction.response.defer()
        wd = await get_withdrawal(self.wid)
        if not wd or wd["status"] != "pending":
            return await interaction.followup.send(
                embed=embed_error("Already Processed", ""), ephemeral=True
            )

        balances = await get_all_balances(self.user_id)
        bal = balances.get(self.coin, {}).get("balance", 0) or 0
        if bal < self.amount:
            return await interaction.followup.send(
                embed=embed_error("Insufficient Funds", "User's balance is too low."), ephemeral=True
            )

        await update_balance(self.user_id, self.coin, -self.amount)
        await update_withdrawal_status(
            self.wid, "approved",
            f"Approved by {interaction.user} — manual payout required",
            handled_by=str(interaction.user.id),
        )

        for c in self.children:
            c.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            embed=embed_success(
                f"Approved #{self.wid}",
                "Send the payout from your own wallet, then mark paid below.",
            ),
            view=MarkPaidView(self.wid, self.user_id, self.coin, self.net, self.address),
        )

        # Notify user
        user = interaction.client.get_user(int(self.user_id))
        if user:
            try:
                await user.send(embed=discord.Embed(
                    title=f"{E['tick']} Withdrawal Approved",
                    description=(
                        f"{DIV}\n{E['tick']} **Status** {S['bullet']} Approved\n"
                        f"{E['tick']} **Payout** {S['bullet']} {fmt_coin(self.net, self.coin)}\n"
                        f"{E['secure']} **Address** {S['bullet']} `{self.address}`\n{DIV}\n"
                        f"An authorised member will send this shortly."
                    ),
                    color=COLOR["success"],
                ))
            except Exception:
                pass

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        await interaction.response.send_modal(
            RejectReasonModal(self.wid, self.user_id, self.coin, self.amount, self)
        )


class MarkPaidView(discord.ui.View):
    def __init__(self, wid: int, user_id: str, coin: str, net: float, address: str):
        super().__init__(timeout=None)
        self.wid = wid
        self.user_id = user_id
        self.coin = coin
        self.net = net
        self.address = address

    @discord.ui.button(label="Mark Paid", style=discord.ButtonStyle.success, emoji="💸")
    async def mark_paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_authorised_or_owner(interaction.user.id):
            return await interaction.response.send_message(
                embed=embed_error("Not Authorised", ""), ephemeral=True
            )
        await interaction.response.send_modal(TxHashModal(self.wid, self.user_id, self.coin, self.net, self.address))


class TxHashModal(discord.ui.Modal, title="Mark Paid — Enter TXID"):
    txid_input = discord.ui.TextInput(
        label="Transaction ID / Hash",
        placeholder="Paste the blockchain TXID here",
        min_length=10,
        required=True,
    )

    def __init__(self, wid: int, user_id: str, coin: str, net: float, address: str):
        super().__init__()
        self.wid = wid
        self.user_id = user_id
        self.coin = coin
        self.net = net
        self.address = address

    async def on_submit(self, interaction: discord.Interaction):
        txid = self.txid_input.value.strip()
        await update_withdrawal_status(
            self.wid, "paid",
            f"Manually paid. txid:{txid}",
            handled_by=str(interaction.user.id),
        )

        for item in interaction.message.components:
            pass  # disable buttons via edit below
        try:
            view = discord.ui.View()
            for b in [discord.ui.Button(label="Mark Paid", disabled=True, style=discord.ButtonStyle.success, emoji="💸")]:
                view.add_item(b)
            await interaction.message.edit(view=view)
        except Exception:
            pass

        await interaction.response.send_message(
            embed=embed_success(f"Withdrawal #{self.wid} Marked Paid", f"TXID: `{txid[:32]}…`"),
            ephemeral=True,
        )

        # Send the rich confirmation card to the user (matches screenshot)
        user = interaction.client.get_user(int(self.user_id))
        if user:
            try:
                from bot.wallets import btc_wallet  # just to get env addr
                hot_addr = os.getenv(f"{self.coin.upper()}_ADDRESS", "unknown")
                confirm_embed = _confirm_embed(self.coin, hot_addr, self.address, self.net, txid)
                await user.send(embed=confirm_embed)
            except Exception as exc:
                log.warning(f"Could not send confirm to user {self.user_id}: {exc}")


class RejectReasonModal(discord.ui.Modal, title="Reject Withdrawal"):
    reason = discord.ui.TextInput(label="Rejection Reason", placeholder="Enter reason…", min_length=3)

    def __init__(self, wid: int, user_id: str, coin: str, amount: float, parent_view):
        super().__init__()
        self.wid = wid
        self.user_id = user_id
        self.coin = coin
        self.amount = amount
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await update_withdrawal_status(
            self.wid, "rejected", self.reason.value,
            handled_by=str(interaction.user.id),
        )
        user = interaction.client.get_user(int(self.user_id))
        if user:
            try:
                await user.send(embed=discord.Embed(
                    title=f"{E['declined']} Withdrawal Rejected",
                    description=(
                        f"{DIV}\n{E['error']} **Status** {S['bullet']} Rejected\n"
                        f"{coin_emoji(self.coin)} **Amount** {S['bullet']} {fmt_coin(self.amount, self.coin)}\n"
                        f"{E['tag']} **Reason** {S['bullet']} {self.reason.value}\n{DIV}\n"
                        f"Your balance was **not deducted**."
                    ),
                    color=COLOR["error"],
                ))
            except Exception:
                pass
        await interaction.response.send_message(
            embed=embed_error(f"Rejected #{self.wid}", f"Reason: {self.reason.value}")
        )
        for item in self.parent_view.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self.parent_view)
        except Exception:
            pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class Withdraw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paused = False

    @app_commands.command(name="withdraw", description="Withdraw crypto — opens in your DMs")
    async def withdraw(self, interaction: discord.Interaction):
        if self.paused:
            try:
                await interaction.user.send(embed=embed_error("Withdrawals Paused", "Temporarily unavailable. Try later."))
            except Exception:
                pass
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.delete_original_response()
            except Exception:
                pass
            return

        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.user.send(embed=coin_select_embed(), view=StartWithdrawView(uid))
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=embed_error("DMs Closed", "I couldn't DM you — enable DMs from server members and try again."),
                ephemeral=True,
            )

        try:
            await interaction.delete_original_response()
        except Exception:
            pass

    @commands.command(name="withdraw", aliases=["wd"])
    async def withdraw_prefix(self, ctx):
        uid = str(ctx.author.id)
        await ensure_user(uid, ctx.author.name)
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                pass
        try:
            await ctx.author.send(embed=coin_select_embed(), view=StartWithdrawView(uid))
        except discord.Forbidden:
            return

    @app_commands.command(name="withdrawstatus", description="Check your withdrawal history")
    async def withdrawstatus(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        wds = await get_user_withdrawals(str(interaction.user.id))
        if not wds:
            return await interaction.followup.send(
                embed=embed_error("No History", "You haven't made any withdrawal requests."),
                ephemeral=True,
            )
        ICONS = {
            "pending": E["loading"], "approved": E["tick"],
            "paid": E["tick"], "rejected": E["declined"],
        }
        lines = []
        for w in wds[:10]:
            icon = ICONS.get(w["status"], E["time"])
            lines.append(
                f"{icon} `#{w['id']}` {S['bullet']} "
                f"{fmt_coin(withdrawal_amount(w), w['method'])} {S['bullet']} `{w['status'].title()}`"
            )
        await interaction.followup.send(
            embed=discord.Embed(
                title=f"{E['withdraw']} Withdrawal History",
                description=f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}",
                color=COLOR["info"],
            ),
            ephemeral=True,
        )

    @app_commands.command(name="pendingwithdrawals", description="[Authorised] View and approve pending withdrawals")
    async def pendingwithdrawals(self, interaction: discord.Interaction):
        if not await is_authorised_or_owner(interaction.user.id):
            return await interaction.response.send_message(
                embed=embed_error("Not Authorised", ""), ephemeral=True
            )
        rows = await get_pending_withdrawals()
        if not rows:
            return await interaction.response.send_message(
                embed=embed_success("All Clear", "No pending withdrawals."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        for w in rows[:10]:
            amt = withdrawal_amount(w)
            desc = (
                f"{DIV}\n"
                f"👤 **User** {S['bullet']} <@{w['user_id']}>\n"
                f"{coin_emoji(w['method'])} **Coin** {S['bullet']} `{symbol(w['method'])}`\n"
                f"{E['balance']} **Amount** {S['bullet']} {fmt_coin(amt, w['method'])}\n"
                f"{E['tick']} **Net Payout** {S['bullet']} {fmt_coin(w['net_amount'] or 0, w['method'])}\n"
                f"{E['address']} **Payout Address**\n```\n{w['address']}\n```\n"
                f"{DIV}"
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"{E['id']} Withdrawal #{w['id']}",
                    description=desc,
                    color=COLOR["warning"],
                ),
                view=ApprovalView(w["id"], w["user_id"], w["method"], amt, w["net_amount"], w["address"]),
                ephemeral=True,
            )

    @app_commands.command(name="pausewithdraw", description="[Owner] Pause or resume withdrawals")
    async def pausewithdraw(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                embed=embed_error("No Permission", "Owner only."), ephemeral=True
            )
        self.paused = not self.paused
        state = "Paused" if self.paused else "Resumed"
        color = COLOR["error"] if self.paused else COLOR["success"]
        await interaction.response.send_message(embed=discord.Embed(
            title=f"{E['pause']} Withdrawals {state}",
            description=f"{DIV}\nWithdrawals are now **{state.lower()}**.\n{DIV}",
            color=color,
        ))


async def setup(bot):
    await bot.add_cog(Withdraw(bot))
