"""
XWALLET Admin — Prefix-only commands (hidden from public).
All admin commands use $ prefix and require STAFF_IDS or admin perms.

Prefix Commands:
  $setbal @user <coin> <amount>     — Set exact balance
  $addbal @user <coin> <amount>     — Add/deduct balance  
  $bals @user                       — Full balance breakdown
  $pay @user <coin> <amount>        — Admin credit payment
  $userinfo [@user]                 — Deep user profile
  $ownerbal                         — Economy overview (password protected)
  $addauth @user                    — Authorise staff member
  $removeauth @user                 — Deauthorise member
  $listauth                         — List authorised members
  $msg @user <text>                 — DM a user
  $broadcast <scope> <text>         — Broadcast message (server/all/auth)
  $setprefix <prefix>               — Change bot prefix
  $setlogchannel #channel           — Set log channel
  $setwdlog #channel                — Set withdraw log channel
  $setdeplog #channel               — Set deposit log channel
  $setdetect <coin> <watcher/alch>  — Set deposit detection method
  $setwdmethod <coin> <auto/manual> — Set withdraw method
  $detectstatus                     — Show detection/withdraw status
  $servers                          — List all servers bot is in
  $announce #ch <title> | <text>    — Post announcement
  $ping                             — Latency check
  $uptime                           — Bot uptime
  $si                               — Server info (public)
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from datetime import datetime

from bot.utils.checks import (
    dev_prefix_only, is_authorised_or_owner,
    OWNER_ID, HOME_GUILD_ID, STAFF_IDS, OWNER_IDS
)
from bot.utils.database import (
    ensure_user, get_user, get_all_balances, set_balance, update_balance,
    get_guild, update_guild, add_log, get_all_users, get_total_holdings_by_coin,
    add_authorised_user, remove_authorised_user, get_authorised_users,
    get_all_withdrawals, get_all_deposits
)
from bot.utils.embeds import (
    E, S, DIV, COLOR,
    embed_error, embed_processing, embed_success,
    fmt_coin, fmt_usd, get_all_usd_prices, get_usd_price, coin_emoji
)
from bot.utils.coins import COINS, ORDER, symbol, is_valid_coin

OWNER_PW = os.getenv("OWNER_PASSWORD", "changeme")
DEV_GUILD_ID = HOME_GUILD_ID

def _is_staff(ctx) -> bool:
    return ctx.author.id in STAFF_IDS or (ctx.guild and ctx.author.guild_permissions.administrator)

def _staff_only():
    async def pred(ctx):
        return _is_staff(ctx)
    return commands.check(pred)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── $setbal @user <coin> <amount> ────────────────────────────────────────
    @commands.command(name="setbal", hidden=True)
    @_staff_only()
    async def setbal(self, ctx, user: discord.Member, coin_code: str, amount: float):
        """Set a user's exact balance for a coin."""
        coin_code = coin_code.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Coin", f"Supported: {', '.join(ORDER)}"))
        await ensure_user(str(user.id), user.name)
        await set_balance(str(user.id), coin_code, max(0, amount))
        desc = (
            f"{DIV}\n"
            f"👤 **User** {S['bullet']} {user.mention}\n"
            f"{coin_emoji(coin_code)} **Coin** {S['bullet']} `{symbol(coin_code)}`\n"
            f"{E['balance']} **New Balance** {S['bullet']} {fmt_coin(amount, coin_code)}\n"
            f"{E['authorized']} **Set by** {S['bullet']} {ctx.author.mention}\n"
            f"{DIV}"
        )
        await ctx.send(embed=discord.Embed(title="{E['admin']} Balance Set", description=desc, color=COLOR["gold"]))
        await add_log(str(ctx.guild.id) if ctx.guild else "DM", str(ctx.author.id), "SET_BAL", f"{user.id}={amount}{coin_code}")

    # ── $addbal @user <coin> <amount> ────────────────────────────────────────
    @commands.command(name="addbal", aliases=["grant"], hidden=True)
    @_staff_only()
    async def addbal(self, ctx, user: discord.Member, coin_code: str, amount: float):
        """Add or deduct balance from a user (negative to deduct)."""
        coin_code = coin_code.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Coin", f"Supported: {', '.join(ORDER)}"))
        await ensure_user(str(user.id), user.name)
        await update_balance(str(user.id), coin_code, amount)
        bals = await get_all_balances(str(user.id))
        new_bal = bals.get(coin_code, {}).get("balance", 0) or 0
        sign = "+" if amount >= 0 else ""
        desc = (
            f"{DIV}\n"
            f"👤 **User** {S['bullet']} {user.mention}\n"
            f"{coin_emoji(coin_code)} **Change** {S['bullet']} `{sign}{amount:.8f} {symbol(coin_code)}`\n"
            f"{E['balance']} **New Balance** {S['bullet']} {fmt_coin(new_bal, coin_code)}\n"
            f"{DIV}"
        )
        await ctx.send(embed=discord.Embed(title="{E['tick']} Balance Updated", description=desc, color=COLOR["success"]))
        await add_log(str(ctx.guild.id) if ctx.guild else "DM", str(ctx.author.id), "ADD_BAL", f"{sign}{amount}{coin_code}→{user.id}")

    # ── $bals @user ───────────────────────────────────────────────────────────
    @commands.command(name="bals", aliases=["adminbal", "checkbal"], hidden=True)
    @_staff_only()
    async def bals(self, ctx, user: discord.Member = None):
        """View full balance breakdown of any user."""
        target = user or ctx.author
        await ensure_user(str(target.id), target.name)
        bals = await get_all_balances(str(target.id))
        prices = await get_all_usd_prices()
        total_usd = sum((bals.get(c, {}).get("balance", 0) or 0) * prices.get(c, 0) for c in ORDER)

        lines = []
        for c in ORDER:
            bal = bals.get(c, {}).get("balance", 0) or 0
            hold = bals.get(c, {}).get("hold", 0) or 0
            usd = bal * prices.get(c, 0)
            if bal > 0 or hold > 0:
                lines.append(
                    f"{coin_emoji(c)} **{symbol(c)}** {S['bullet']} "
                    f"`{fmt_coin(bal, c)}` (~`${usd:.2f}`) "
                    + (f"| 🔒 Hold: `{fmt_coin(hold, c)}`" if hold > 0 else "")
                )

        bal_block = "\n".join(lines) if lines else f"💸 No holdings."
        desc = (
            f"{DIV}\n"
            f"👤 **{target}** (`{target.id}`)\n"
            f"{DIV}\n"
            f"{bal_block}\n"
            f"{DIV}\n"
            f"{E['xwallet']} **Total Value** {S['bullet']} `${total_usd:,.4f} USD`\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['balance']} Balance — {target.display_name}", description=desc, color=COLOR["info"])
        em.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=em)

    # ── $pay @user <coin> <amount> ────────────────────────────────────────────
    @commands.command(name="pay", aliases=["adminpay"], hidden=True)
    @dev_prefix_only()
    async def pay(self, ctx, user: discord.Member, coin_code: str, amount: float):
        """Admin credit payment to a user's balance."""
        coin_code = coin_code.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Coin", f"Supported: {', '.join(ORDER)}"))
        msg = await ctx.send(embed=embed_processing(f"{E['payment']} Processing payment to {user.display_name}…"))
        await ensure_user(str(user.id), user.name)
        await update_balance(str(user.id), coin_code, amount)
        bals = await get_all_balances(str(user.id))
        new_bal = bals.get(coin_code, {}).get("balance", 0) or 0
        desc = (
            f"{DIV}\n"
            f"👤 **Recipient** {S['bullet']} {user.mention}\n"
            f"{coin_emoji(coin_code)} **Paid** {S['bullet']} {fmt_coin(amount, coin_code)}\n"
            f"{E['balance']} **New Balance** {S['bullet']} {fmt_coin(new_bal, coin_code)}\n"
            f"{E['authorized']} **By** {S['bullet']} {ctx.author.mention}\n"
            f"{DIV}"
        )
        await msg.edit(embed=discord.Embed(title="{E['payment']} Admin Payment", description=desc, color=COLOR["gold"]))
        await add_log(str(ctx.guild.id) if ctx.guild else "DM", str(ctx.author.id), "ADMIN_PAY", f"+{amount}{coin_code}→{user.id}")

    # ── $userinfo [@user] ─────────────────────────────────────────────────────
    @commands.command(name="userinfo", aliases=["ui", "whois"], hidden=True)
    @_staff_only()
    async def userinfo(self, ctx, user: discord.Member = None):
        """Deep user profile with balances and stats."""
        target = user or ctx.author
        await ensure_user(str(target.id), target.name)
        bals = await get_all_balances(str(target.id))
        prices = await get_all_usd_prices()
        total_usd = sum((bals.get(c, {}).get("balance", 0) or 0) * prices.get(c, 0) for c in ORDER)

        held_lines = [
            f"  {coin_emoji(c)} `{fmt_coin(bals[c]['balance'], c)}` (~`${bals[c]['balance'] * prices.get(c,0):.2f}`)"
            for c in ORDER if bals.get(c, {}).get("balance", 0)
        ]
        held_block = "\n".join(held_lines) if held_lines else "  💸 No holdings."

        # Get deposits/withdrawals count
        deps = await get_all_deposits()
        wds = await get_all_withdrawals()
        uid = str(target.id)
        user_deps = [d for d in deps if d["user_id"] == uid]
        user_wds  = [w for w in wds if w["user_id"] == uid]

        roles = [r.mention for r in reversed(target.roles) if r.name != "@everyone"]
        roles_str = " ".join(roles[:5]) if roles else "`None`"

        desc = (
            f"{DIV}\n"
            f"{E['id']} **ID** {S['bullet']} `{target.id}`\n"
            f"🏷️ **Username** {S['bullet']} `{target}`\n"
            f"{E['time']} **Joined** {S['bullet']} `{target.joined_at.strftime('%d %b %Y') if target.joined_at else 'Unknown'}`\n"
            f"{E['time']} **Account Created** {S['bullet']} <t:{int(target.created_at.timestamp())}:D>\n"
            f"{DIV}\n"
            f"**Holdings:**\n{held_block}\n"
            f"{E['xwallet']} **Total USD** {S['bullet']} `${total_usd:,.4f}`\n"
            f"{DIV}\n"
            f"{E['deposit']} **Deposits** {S['bullet']} `{len(user_deps)}`  📤 **Withdrawals** {S['bullet']} `{len(user_wds)}`\n"
            f"{DIV}\n"
            f"🎭 **Roles** {S['bullet']} {roles_str}\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['id']} {target.display_name}", description=desc, color=COLOR["info"])
        em.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=em)

    # ── $ownerbal (password protected) ───────────────────────────────────────
    @commands.command(name="ownerbal", aliases=["stats", "economy"], hidden=True)
    @dev_prefix_only()
    async def ownerbal(self, ctx):
        """Economy overview — password protected."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        await ctx.send(embed=discord.Embed(
            description=f"{E['secure']} Enter owner password to continue (you have 30s):",
            color=COLOR["warning"]
        ))
        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
            if msg.content != OWNER_PW:
                return await ctx.send(embed=embed_error("{E['error']} Wrong Password", "Access denied."))
            try: await msg.delete()
            except Exception: pass
        except asyncio.TimeoutError:
            return await ctx.send(embed=embed_error("⏰ Timeout", "Password not entered in time."))

        users = await get_all_users()
        totals = await get_total_holdings_by_coin()
        prices = await get_all_usd_prices()
        total_usd = sum((totals.get(c, {}).get("balance", 0) or 0) * prices.get(c, 0) for c in ORDER)
        hold_usd  = sum((totals.get(c, {}).get("hold",    0) or 0) * prices.get(c, 0) for c in ORDER)

        lines = [
            f"  {coin_emoji(c)} **{symbol(c)}** {S['bullet']} {fmt_coin(totals.get(c,{}).get('balance',0),c)} (~`${(totals.get(c,{}).get('balance',0) or 0)*prices.get(c,0):.2f}`)"
            for c in ORDER if totals.get(c, {}).get("balance", 0)
        ] or ["  💸 No holdings."]

        desc = (
            f"{DIV}\n"
            f"👥 **Total Users** {S['bullet']} `{len(users)}`\n"
            f"{DIV}\n"
            f"**Holdings:**\n" + "\n".join(lines) + "\n"
            f"{DIV}\n"
            f"{E['xwallet']} **Total Value (USD)** {S['bullet']} `${total_usd:,.4f}`\n"
            f"{E['secure']} **On Hold (USD)** {S['bullet']} `${hold_usd:,.4f}`\n"
            f"{DIV}"
        )
        await ctx.send(embed=discord.Embed(title="{E['owner']} Owner Economy Panel", description=desc, color=COLOR["gold"]))

    # ── $addauth / $removeauth / $listauth ────────────────────────────────────
    @commands.command(name="addauth", aliases=["addauthorised"], hidden=True)
    @dev_prefix_only()
    async def addauth(self, ctx, user: discord.Member):
        """Authorise a member for deposit/withdraw approvals."""
        await add_authorised_user(str(user.id), user.name, str(ctx.author.id))
        await ctx.send(embed=embed_success("{E['tick']} Authorised", f"{user.mention} can now approve transactions."))
        await add_log(str(ctx.guild.id) if ctx.guild else "GLOBAL", str(ctx.author.id), "ADD_AUTHORISED", str(user.id))

    @commands.command(name="removeauth", aliases=["removeauthorised", "deauth"], hidden=True)
    @dev_prefix_only()
    async def removeauth(self, ctx, user: discord.Member):
        """Remove authorisation from a member."""
        await remove_authorised_user(str(user.id))
        await ctx.send(embed=embed_success("{E['tick']} Removed", f"{user.mention} is no longer authorised."))
        await add_log(str(ctx.guild.id) if ctx.guild else "GLOBAL", str(ctx.author.id), "REMOVE_AUTHORISED", str(user.id))

    @commands.command(name="listauth", aliases=["listauthorised", "auths"], hidden=True)
    @dev_prefix_only()
    async def listauth(self, ctx):
        """List all authorised members."""
        rows = await get_authorised_users()
        if not rows:
            return await ctx.send(embed=embed_success("{E['history']} Authorised Members", "None yet."))
        lines = [f"{E['tick']} <@{r['user_id']}> {S['bullet']} added by <@{r['added_by']}>" for r in rows]
        desc = f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}"
        await ctx.send(embed=discord.Embed(title="{E['authorized']} Authorised Members", description=desc, color=COLOR["info"]))

    # ── $msg @user <text> ─────────────────────────────────────────────────────
    @commands.command(name="msg", aliases=["dm", "message"], hidden=True)
    @dev_prefix_only()
    async def msg(self, ctx, target: discord.Member, *, content: str):
        """DM a specific user as staff."""
        em = discord.Embed(
            title=f"{E['dm']} Message from Staff",
            description=f"{DIV}\n{content}\n{DIV}",
            color=COLOR["primary"]
        )
        em.set_footer(text=f"Sent by {ctx.author.display_name}")
        try:
            await target.send(embed=em)
            await ctx.send(embed=embed_success("{E['tick']} Sent", f"DM delivered to {target.mention}"))
        except discord.Forbidden:
            await ctx.send(embed=embed_error("{E['error']} Failed", "Could not DM that user — they may have DMs closed."))

    # ── $broadcast <scope> <text> ────────────────────────────────────────────
    @commands.command(name="broadcast", aliases=["bc"], hidden=True)
    @dev_prefix_only()
    async def broadcast(self, ctx, scope: str, *, content: str):
        """Broadcast a message. Scopes: server | all | auth"""
        scope = scope.lower()
        if scope not in ("server", "all", "auth"):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Scope", "Use: `server`, `all`, or `auth`"))
        em = discord.Embed(
            title=f"{E['broadcast']} Announcement",
            description=f"{DIV}\n{content}\n{DIV}",
            color=COLOR["gold"]
        )
        em.set_footer(text=f"From {ctx.author.display_name}")
        msg = await ctx.send(embed=embed_processing("📡 Sending broadcast…"))
        count, fail = 0, 0

        if scope == "auth":
            auth_rows = await get_authorised_users()
            ids = {OWNER_ID} | {int(r["user_id"]) for r in auth_rows}
            for uid in ids:
                try:
                    u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    await u.send(embed=em); count += 1; await asyncio.sleep(0.4)
                except Exception: fail += 1
        elif scope == "all":
            seen = set()
            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.bot or member.id in seen: continue
                    seen.add(member.id)
                    try: await member.send(embed=em); count += 1; await asyncio.sleep(0.4)
                    except Exception: fail += 1
        else:  # server
            if not ctx.guild: return await msg.edit(embed=embed_error("{E['error']} Server Only", "Use inside a server."))
            for member in ctx.guild.members:
                if member.bot: continue
                try: await member.send(embed=em); count += 1; await asyncio.sleep(0.4)
                except Exception: fail += 1

        await msg.edit(embed=embed_success("📡 Broadcast Complete", f"{E['tick']} Sent: `{count}` | ❌ Failed: `{fail}`"))
        await add_log(str(ctx.guild.id) if ctx.guild else "GLOBAL", str(ctx.author.id), "BROADCAST", f"scope={scope}")

    # ── $setprefix <prefix> ───────────────────────────────────────────────────
    @commands.command(name="setprefix", aliases=["prefix"], hidden=True)
    @dev_prefix_only()
    async def setprefix(self, ctx, prefix: str):
        """Change the bot prefix for this server."""
        if len(prefix) > 5:
            return await ctx.send(embed=embed_error("{E['error']} Too Long", "Max 5 characters."))
        from bot.utils.database import set_prefix
        await set_prefix(str(ctx.guild.id), prefix)
        await ctx.send(embed=embed_success("{E['tick']} Prefix Updated", f"New prefix: `{prefix}`"))

    # ── $setlogchannel / $setwdlog / $setdeplog ───────────────────────────────
    @commands.command(name="setlogchannel", aliases=["setlog"], hidden=True)
    @dev_prefix_only()
    async def setlogchannel(self, ctx, channel: discord.TextChannel):
        await update_guild(str(ctx.guild.id), log_channel=str(channel.id))
        await ctx.send(embed=embed_success("{E['tick']} Log Channel Set", channel.mention))

    @commands.command(name="setwdlog", aliases=["setwithdrawlog"], hidden=True)
    @dev_prefix_only()
    async def setwdlog(self, ctx, channel: discord.TextChannel):
        await update_guild(str(ctx.guild.id), withdraw_log=str(channel.id))
        await ctx.send(embed=embed_success("{E['tick']} Withdraw Log Set", channel.mention))

    @commands.command(name="setdeplog", aliases=["setdepositlog"], hidden=True)
    @dev_prefix_only()
    async def setdeplog(self, ctx, channel: discord.TextChannel):
        await update_guild(str(ctx.guild.id), deposit_log=str(channel.id))
        await ctx.send(embed=embed_success("{E['tick']} Deposit Log Set", channel.mention))

    # ── $setdetect <coin> <method> ────────────────────────────────────────────
    @commands.command(name="setdetect", aliases=["setdetection"], hidden=True)
    @dev_prefix_only()
    async def setdetect(self, ctx, coin_code: str, method: str):
        """Set deposit detection method. Methods: watcher, alchemy"""
        coin_code = coin_code.lower(); method = method.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Coin", f"Supported: {', '.join(ORDER)}"))
        if method not in ("watcher", "alchemy"):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Method", "Use: `watcher` or `alchemy`"))
        if method == "alchemy" and coin_code not in ("eth", "usdterc20"):
            return await ctx.send(embed=embed_error("{E['error']} Not Supported", "Alchemy only works for ETH and USDT ERC20."))
        from bot.utils.database import set_detection_method
        await set_detection_method(coin_code, method)
        await ctx.send(embed=embed_success("{E['tick']} Detection Updated", f"`{symbol(coin_code)}` → `{method}`"))

    # ── $setwdmethod <coin> <method> ─────────────────────────────────────────
    @commands.command(name="setwdmethod", aliases=["setwithdrawmethod"], hidden=True)
    @dev_prefix_only()
    async def setwdmethod(self, ctx, coin_code: str, method: str):
        """Set withdraw method per coin. Methods: manual, automatic"""
        coin_code = coin_code.lower(); method = method.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Coin", f"Supported: {', '.join(ORDER)}"))
        if method not in ("manual", "automatic"):
            return await ctx.send(embed=embed_error("{E['error']} Invalid Method", "Use: `manual` or `automatic`"))
        if method == "automatic" and coin_code not in {"btc", "ltc", "eth", "sol"}:
            return await ctx.send(embed=embed_error("{E['error']} Unsupported", f"Auto withdrawal not supported for `{symbol(coin_code)}`."))
        from bot.utils.database import set_withdraw_method
        await set_withdraw_method(coin_code, method)
        await ctx.send(embed=embed_success("{E['tick']} Withdraw Method Updated", f"`{symbol(coin_code)}` → `{method}`"))

    # ── $detectstatus ─────────────────────────────────────────────────────────
    @commands.command(name="detectstatus", aliases=["detectionstatus", "methods"], hidden=True)
    @dev_prefix_only()
    async def detectstatus(self, ctx):
        """Show detection and withdrawal method status for all coins."""
        from bot.utils.database import get_detection_method, get_withdraw_method
        lines = []
        for c in ORDER:
            dep_m = await get_detection_method(c)
            wd_m  = await get_withdraw_method(c)
            lines.append(f"{coin_emoji(c)} **{symbol(c)}** {S['bullet']} 📥 `{dep_m}` / 📤 `{wd_m}`")
        desc = f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}"
        await ctx.send(embed=discord.Embed(title="{E['admin']} Detection / Withdraw Status", description=desc, color=COLOR["gold"]))

    # ── $servers ──────────────────────────────────────────────────────────────
    @commands.command(name="servers", hidden=True)
    @dev_prefix_only()
    async def servers(self, ctx):
        """List all servers the bot is in."""
        lines = [
            f"{E['server']} **{g.name}** {S['bullet']} `{g.member_count}` members `{g.id}`"
            for g in self.bot.guilds
        ]
        desc = f"{DIV}\n" + "\n".join(lines[:25]) + f"\n{DIV}\n🌐 **Total:** `{len(self.bot.guilds)}`"
        await ctx.send(embed=discord.Embed(title="{E['server']} Bot Servers", description=desc, color=COLOR["gold"]))

    # ── $announce #channel <title> | <text> ──────────────────────────────────
    @commands.command(name="announce", aliases=["ann"], hidden=True)
    @dev_prefix_only()
    async def announce(self, ctx, channel: discord.TextChannel, *, args: str):
        """Post an announcement. Format: $announce #channel Title | Message"""
        if "|" in args:
            title, content = args.split("|", 1)
        else:
            title, content = "{E['broadcast']} Announcement", args
        em = discord.Embed(
            title=f"{E['broadcast']} {title.strip()}",
            description=f"{DIV}\n{content.strip()}\n{DIV}",
            color=COLOR["gold"],
            timestamp=datetime.utcnow()
        )
        em.set_footer(text=f"Announced by {ctx.author.display_name}")
        await channel.send(embed=em)
        await ctx.send(embed=embed_success("{E['tick']} Announced", f"Posted in {channel.mention}"))
        await add_log(str(ctx.guild.id), str(ctx.author.id), "ANNOUNCE", title.strip())

    # ── $ping ─────────────────────────────────────────────────────────────────
    @commands.command(name="ping")
    async def ping(self, ctx):
        lat = round(self.bot.latency * 1000)
        color = COLOR["success"] if lat < 100 else COLOR["warning"] if lat < 200 else COLOR["error"]
        bar = "🟢" if lat < 100 else "🟡" if lat < 200 else "🔴"
        await ctx.send(embed=discord.Embed(
            title=f"{E['notify']} Pong!",
            description=f"{DIV}\n{bar} **WebSocket Latency** {S['bullet']} `{lat}ms`\n{DIV}",
            color=color
        ))

    # ── $uptime ───────────────────────────────────────────────────────────────
    @commands.command(name="uptime", aliases=["up"])
    async def uptime(self, ctx):
        delta = datetime.utcnow() - self.bot.start_time
        d, r = divmod(int(delta.total_seconds()), 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        ts = int(self.bot.start_time.timestamp())
        desc = (
            f"{DIV}\n"
            f"{E['loading']} **Uptime** {S['bullet']} `{d}d {h}h {m}m {s}s`\n"
            f"{E['time']} **Started** {S['bullet']} <t:{ts}:F>\n"
            f"{DIV}"
        )
        await ctx.send(embed=discord.Embed(title=f"{E['xwallet']} Bot Uptime", description=desc, color=COLOR["success"]))

    # ── $si — Server Info (public) ────────────────────────────────────────────
    @commands.command(name="sinfo", aliases=["serverinfo", "guildinfo"])
    @commands.guild_only()
    async def si(self, ctx):
        g = ctx.guild
        desc = (
            f"{DIV}\n"
            f"{E['id']} **Server ID** {S['bullet']} `{g.id}`\n"
            f"{E['owner']} **Owner** {S['bullet']} <@{g.owner_id}>\n"
            f"👥 **Members** {S['bullet']} `{g.member_count}`\n"
            f"💬 **Channels** {S['bullet']} `{len(g.text_channels)}` text / `{len(g.voice_channels)}` voice\n"
            f"🎭 **Roles** {S['bullet']} `{len(g.roles) - 1}`\n"
            f"🚀 **Boost Level** {S['bullet']} `{g.premium_tier}` ({g.premium_subscription_count} boosts)\n"
            f"{E['time']} **Created** {S['bullet']} <t:{int(g.created_at.timestamp())}:D>\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['server']} {g.name}", description=desc, color=COLOR["info"])
        if g.icon: em.set_thumbnail(url=g.icon.url)
        await ctx.send(embed=em)

    # ── $profile [@user] ──────────────────────────────────────────────────────
    @commands.command(name="pf", aliases=["myprofile"])
    async def profile(self, ctx, user: discord.Member = None):
        """User profile: currency sent, total worth, today sent/received."""
        target = user or ctx.author
        await ensure_user(str(target.id), target.name)
        bals = await get_all_balances(str(target.id))
        prices = await get_all_usd_prices()
        total_usd = sum((bals.get(c, {}).get("balance", 0) or 0) * prices.get(c, 0) for c in ORDER)

        # Today stats from withdrawals/deposits
        all_deps = await get_all_deposits()
        all_wds  = await get_all_withdrawals()
        uid = str(target.id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_received = sum(
            d.get("net_amount", 0) or 0
            for d in all_deps
            if d["user_id"] == uid and (d.get("created_at") or "").startswith(today) and d.get("status") == "approved"
        )
        today_sent = sum(
            w.get("net_amount", 0) or 0
            for w in all_wds
            if w["user_id"] == uid and (w.get("created_at") or "").startswith(today) and w.get("status") in ("approved", "paid", "sent")
        )
        total_deposited = sum(d.get("net_amount", 0) or 0 for d in all_deps if d["user_id"] == uid and d.get("status") == "approved")
        total_withdrawn = sum(w.get("net_amount", 0) or 0 for w in all_wds if w["user_id"] == uid and w.get("status") in ("approved", "paid", "sent"))

        bal_lines = [
            f"  {coin_emoji(c)} `{fmt_coin(bals.get(c,{}).get('balance',0),c)}` (~`${(bals.get(c,{}).get('balance',0) or 0)*prices.get(c,0):.2f}`)"
            for c in ORDER if bals.get(c, {}).get("balance", 0)
        ] or ["  💸 Empty wallet"]

        desc = (
            f"{DIV}\n"
            f"👤 **{target.display_name}**\n"
            f"{E['id']} `{target.id}`\n"
            f"{DIV}\n"
            f"**💼 Holdings:**\n" + "\n".join(bal_lines) + "\n"
            f"{E['xwallet']} **Total Worth** {S['bullet']} `${total_usd:,.4f} USD`\n"
            f"{DIV}\n"
            f"**📊 Activity:**\n"
            f"  📥 **Total Deposited** {S['bullet']} `${total_deposited:,.4f}`\n"
            f"  📤 **Total Withdrawn** {S['bullet']} `${total_withdrawn:,.4f}`\n"
            f"  🌅 **Today Received** {S['bullet']} `${today_received:,.4f}`\n"
            f"  🌅 **Today Sent** {S['bullet']} `${today_sent:,.4f}`\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['history']} Profile — {target.display_name}", description=desc, color=COLOR["primary"])
        em.set_thumbnail(url=target.display_avatar.url)
        em.set_footer(text=f"XWALLET • {datetime.utcnow().strftime('%d %b %Y')}")
        await ctx.send(embed=em)


async def setup(bot):
    await bot.add_cog(Admin(bot))
