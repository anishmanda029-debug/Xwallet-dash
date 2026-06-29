"""
XWALLET — Info Cog
Commands: /invite $invite | /support $support | /dashboard $dashboard
          /profile $profile $me | $payouts (staff only)
"""

import os
import discord
from discord.ext import commands
from discord import app_commands

from bot.utils.embeds import (
    E, S, DIV, COLOR, coin_emoji,
    get_all_usd_prices, fmt_coin,
)
from bot.utils.coins import COINS, ORDER
from bot.utils.checks import STAFF_IDS
from bot.utils.database import get_all_balances, _fetchall, _fetchone, ensure_user

# ── Env vars ──────────────────────────────────────────────────────────────────

SUPPORT_SERVER_URL = os.getenv("SUPPORT_SERVER_URL", "")
DASHBOARD_URL      = os.getenv("DASHBOARD_URL", "")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _invite_url(bot_id: int) -> str:
    perms = discord.Permissions(
        send_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        manage_channels=True,
        manage_roles=True,
        view_channel=True,
        add_reactions=True,
        use_application_commands=True,
    )
    return discord.utils.oauth_url(bot_id, permissions=perms)


async def _profile_embed(user: discord.User, bot_id: int) -> discord.Embed:
    """Build the $profile embed for a user with live USD totals and tip stats."""
    uid = str(user.id)
    await ensure_user(uid, user.name)

    prices   = await get_all_usd_prices()
    balances = await get_all_balances(uid)

    # ── Balance lines + total worth ──────────────────────────────────────────
    total_usd = 0.0
    coin_lines = []
    for code in ORDER:
        bal   = (balances.get(code) or {}).get("balance", 0) or 0
        price = prices.get(code, 0)
        usd   = bal * price
        total_usd += usd
        if bal > 0:
            coin_lines.append(
                f"{coin_emoji(code)} **{COINS[code]['symbol']}** {S['bullet']} "
                f"`{fmt_coin(bal, code)}` (~${usd:,.2f})"
            )

    if not coin_lines:
        coin_lines = [f"{E['balance']} No balances yet."]

    # ── Tip stats from logs table ─────────────────────────────────────────────
    # Each TIP log detail: "SENDER_ID→RECIPIENT_ID: AMOUNT COIN"
    all_logs = await _fetchall(
        "SELECT action, detail, created_at FROM logs WHERE (user_id=$1 AND action='TIP') "
        "ORDER BY created_at DESC",
        (uid,)
    )

    today_str = discord.utils.utcnow().strftime("%Y-%m-%d")
    today_sent_usd    = 0.0
    today_recv_usd    = 0.0
    lifetime_sent_usd = 0.0

    for row in all_logs:
        detail = row["detail"] or ""
        # format: "SENDER→RECIP: 0.5 ltc"
        try:
            parts        = detail.split(": ", 1)
            sender_recip = parts[0]
            amt_coin     = parts[1].split()
            amount       = float(amt_coin[0])
            coin_code    = amt_coin[1].lower()
            price_now    = prices.get(coin_code, 0)
            usd_val      = amount * price_now
            is_today     = (row["created_at"] or "")[:10] == today_str
            is_sender    = sender_recip.startswith(uid + "→")
            is_recipient = "→" + uid in sender_recip

            if is_sender:
                lifetime_sent_usd += usd_val
                if is_today:
                    today_sent_usd += usd_val
            if is_recipient and is_today:
                today_recv_usd += usd_val
        except Exception:
            pass

    desc = (
        f"{DIV}\n"
        f"{E['id']} **{user.display_name}** {S['bullet']} `{user.id}`\n"
        f"{DIV}\n"
        f"**{E['balance']} Balances**\n"
        + "\n".join(coin_lines)
        + f"\n\n{E['payment']} **Total Worth** {S['bullet']} `${total_usd:,.2f}`\n"
        f"{DIV}\n"
        f"**{E['history']} Tip Stats**\n"
        f"{E['arrow1']} Today Sent {S['bullet']} `${today_sent_usd:,.2f}`\n"
        f"{E['arrow1']} Today Received {S['bullet']} `${today_recv_usd:,.2f}`\n"
        f"{E['arrow1']} Lifetime Sent {S['bullet']} `${lifetime_sent_usd:,.2f}`\n"
        f"{DIV}"
    )

    em = discord.Embed(title=f"{E['xwallet']} Wallet Profile", description=desc, color=COLOR["primary"])
    em.set_thumbnail(url=user.display_avatar.url)
    em.set_footer(text="Live prices via CoinGecko")
    return em


async def _payouts_embed(bot_id: int) -> discord.Embed:
    """Staff-only: deposit/withdraw method + mnemonic status + derived addresses."""
    from bot.utils.addresses import get_address

    mn = os.getenv("WALLET_MNEMONIC", "").strip()
    mn_status = f"{E['tick']} Set ({len(mn.split())} words)" if mn else f"{E['error']} NOT SET (using manual addresses)"

    lines = [
        f"{DIV}",
        f"{E['secure']} **Mnemonic** {S['bullet']} {mn_status}",
        f"{DIV}",
        f"**{E['deposit']} Deposit / Withdraw Methods**\n",
    ]

    for code in ORDER:
        coin_info = COINS[code]
        addr = get_address(code) or "⚠️ Not configured"
        method = "HD Wallet" if (mn and code != "usdttrc20") else "Manual ENV"
        lines.append(
            f"{coin_emoji(code)} **{coin_info['label']}** (`{coin_info['symbol']}`)\n"
            f"  {S['bullet']} Method: `{method}`\n"
            f"  {S['bullet']} Address: `{addr}`"
        )

    lines.append(DIV)
    desc = "\n".join(lines)

    em = discord.Embed(title=f"{E['admin']} Payout Configuration", description=desc, color=COLOR["warning"])
    em.set_footer(text="Staff only • Never share mnemonic")
    return em


# ── Cog ───────────────────────────────────────────────────────────────────────

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /invite  $invite ──────────────────────────────────────────────────────

    @app_commands.command(name="invite", description="Get the bot's invite link")
    async def invite_slash(self, interaction: discord.Interaction):
        url = _invite_url(self.bot.user.id)
        em = discord.Embed(
            title=f"{E['xwallet']} Invite XWALLET",
            description=f"{DIV}\n{E['arrow1']} [**Click here to add XWALLET to your server**]({url})\n{DIV}",
            color=COLOR["primary"],
        )
        await interaction.response.send_message(embed=em, ephemeral=True)

    @commands.command(name="invite", aliases=["inv"])
    async def invite_prefix(self, ctx):
        url = _invite_url(self.bot.user.id)
        em = discord.Embed(
            title=f"{E['xwallet']} Invite XWALLET",
            description=f"{DIV}\n{E['arrow1']} [**Click here to add XWALLET to your server**]({url})\n{DIV}",
            color=COLOR["primary"],
        )
        await ctx.send(embed=em)

    # ── /support  $support ────────────────────────────────────────────────────

    @app_commands.command(name="support", description="Get the support server link")
    async def support_slash(self, interaction: discord.Interaction):
        if not SUPPORT_SERVER_URL:
            return await interaction.response.send_message(
                f"{E['error']} Support server link not configured yet.", ephemeral=True
            )
        em = discord.Embed(
            title=f"{E['ticket']} Support Server",
            description=f"{DIV}\n{E['arrow1']} [**Join our support server**]({SUPPORT_SERVER_URL})\n{DIV}",
            color=COLOR["info"],
        )
        await interaction.response.send_message(embed=em, ephemeral=True)

    @commands.command(name="support", aliases=["help_server", "discord"])
    async def support_prefix(self, ctx):
        if not SUPPORT_SERVER_URL:
            return await ctx.send(f"{E['error']} Support server link not configured yet.")
        em = discord.Embed(
            title=f"{E['ticket']} Support Server",
            description=f"{DIV}\n{E['arrow1']} [**Join our support server**]({SUPPORT_SERVER_URL})\n{DIV}",
            color=COLOR["info"],
        )
        await ctx.send(embed=em)

    # ── /dashboard  $dashboard ────────────────────────────────────────────────

    @app_commands.command(name="dashboard", description="Open the web dashboard")
    async def dashboard_slash(self, interaction: discord.Interaction):
        if not DASHBOARD_URL:
            return await interaction.response.send_message(
                f"{E['error']} Dashboard URL not configured yet.", ephemeral=True
            )
        em = discord.Embed(
            title=f"{E['history']} Web Dashboard",
            description=f"{DIV}\n{E['arrow1']} [**Open XWALLET Dashboard**]({DASHBOARD_URL})\n{DIV}",
            color=COLOR["primary"],
        )
        await interaction.response.send_message(embed=em, ephemeral=True)

    @commands.command(name="dashboard", aliases=["dash", "panel"])
    async def dashboard_prefix(self, ctx):
        if not DASHBOARD_URL:
            return await ctx.send(f"{E['error']} Dashboard URL not configured yet.")
        em = discord.Embed(
            title=f"{E['history']} Web Dashboard",
            description=f"{DIV}\n{E['arrow1']} [**Open XWALLET Dashboard**]({DASHBOARD_URL})\n{DIV}",
            color=COLOR["primary"],
        )
        await ctx.send(embed=em)

    # ── /profile  $profile  $me ───────────────────────────────────────────────

    @app_commands.command(name="profile", description="View your wallet profile, balances, and tip stats")
    async def profile_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        em = await _profile_embed(interaction.user, self.bot.user.id)
        await interaction.followup.send(embed=em, ephemeral=True)

    @commands.command(name="profile", aliases=["me", "st"])
    async def profile_prefix(self, ctx):
        async with ctx.typing():
            em = await _profile_embed(ctx.author, self.bot.user.id)
        await ctx.send(embed=em)

    # ── $payouts (staff/admin only) ───────────────────────────────────────────

    @commands.command(name="payouts", aliases=["payout_info", "walletinfo"])
    async def payouts_prefix(self, ctx):
        if ctx.author.id not in STAFF_IDS:
            # Also allow server admins
            if not (ctx.guild and ctx.author.guild_permissions.administrator):
                return await ctx.send(f"{E['error']} Staff/admin only.", delete_after=5)

        async with ctx.typing():
            em = await _payouts_embed(self.bot.user.id)
        await ctx.author.send(embed=em)
        await ctx.message.add_reaction("✅")
        if ctx.guild:
            await ctx.send(f"{E['tick']} Sent to your DMs.", delete_after=5)


async def setup(bot):
    await bot.add_cog(Info(bot))
