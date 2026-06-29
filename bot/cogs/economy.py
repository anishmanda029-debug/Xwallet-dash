"""
Economy Cog — /balance, /tip, /leaderboard + @XWALLET mention commands.

@XWALLET commands (mention the bot):
  @XWALLET balance [@user]               — view wallet
  @XWALLET tip $<amount> <coin> @user   — tip a user
  @XWALLET tip <amount> <coin> @user    — same without $
  @XWALLET wd                           — open withdraw panel
  @XWALLET depo                         — open deposit panel
  @XWALLET lb <coin>                    — leaderboard for coin

Prefix aliases: $bal $w $tip $lb $depo $wd
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re

from bot.utils.database import (
    ensure_user, get_user, get_all_balances, update_balance, add_log, get_top_holders
)
from bot.utils.embeds import (
    E, S, DIV, COLOR, embed_error, embed_processing, embed_success,
    fmt_coin, coin_to_usd_str, full_wallet_block, smart_wallet_embed,
    get_all_usd_prices, fmt_usd, get_usd_price, coin_emoji
)
from bot.utils.coins import COINS, ORDER, is_valid_coin, symbol, label as coin_label


def coin_choices():
    return [
        app_commands.Choice(name=f"{COINS[c]['label']} ({COINS[c]['symbol']})", value=c)
        for c in ORDER
    ]


# ── Close Button View ──────────────────────────────────────────────────────────

class CloseView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="✕ Close", style=discord.ButtonStyle.danger, custom_id="close_msg")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message(
                "Only the person who ran this command can close it.", ephemeral=True
            )
        try:
            await interaction.message.delete()
        except discord.Forbidden:
            # Can't delete (e.g. ephemeral or DM) — just remove buttons
            for item in self.children:
                item.disabled = True
            try:
                await interaction.response.edit_message(view=self)
            except Exception:
                await interaction.response.defer()
        except Exception:
            await interaction.response.defer()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Economy Cog ───────────────────────────────────────────────────────────────

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /balance ──────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="View your multi-coin wallet")
    @app_commands.describe(user="Check another user's balance (optional)")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        await interaction.response.defer(ephemeral=True)
        await ensure_user(str(target.id), target.name)
        balances = await get_all_balances(str(target.id))
        em = await smart_wallet_embed(target, balances)
        await interaction.followup.send(embed=em, view=CloseView(interaction.user.id), ephemeral=True)

    @commands.command(name="balance", aliases=["bal", "wallet", "w"])
    async def balance_prefix(self, ctx, user: discord.Member = None):
        target = user or ctx.author
        msg = await ctx.send(embed=embed_processing("Loading wallet…"))
        await ensure_user(str(target.id), target.name)
        balances = await get_all_balances(str(target.id))
        em = await smart_wallet_embed(target, balances)
        await msg.edit(embed=em, view=CloseView(ctx.author.id))

    # ── $depo hint ────────────────────────────────────────────────────────────

    @commands.command(name="depo")
    async def depo_prefix(self, ctx, coin_code: str = None):
        coins_list = " | ".join(f"`{symbol(c)}`" for c in ORDER)
        desc = (
            f"{DIV}\n"
            f"{E['deposit']} **Usage:** `$depo` or `/deposit`\n"
            f"{E['arrow1']} **Coins:** {coins_list}\n"
            f"{DIV}\n"
            f"{E['notify']} Use `/deposit` to open the full deposit panel in DMs.\n"
            f"{DIV}"
        )
        await ctx.send(
            embed=discord.Embed(title=f"{E['deposit']} Deposit Crypto", description=desc, color=COLOR["info"]),
            view=CloseView(ctx.author.id),
        )

    # ── $wd hint ──────────────────────────────────────────────────────────────

    @commands.command(name="wdinfo")
    async def wd_prefix(self, ctx, coin_code: str = None, amount: str = None, address: str = None):
        coins_list = " | ".join(symbol(c) for c in ORDER)
        desc = (
            f"{DIV}\n"
            f"{E['withdraw']} **Usage:** `/withdraw`\n"
            f"{E['arrow1']} **Coins:** {coins_list}\n"
            f"{DIV}\n"
            f"{E['notify']} Use `/withdraw` for the secure withdrawal panel in DMs.\n"
            f"{DIV}"
        )
        await ctx.send(
            embed=discord.Embed(title=f"{E['withdraw']} Withdraw Crypto", description=desc, color=COLOR["warning"]),
            view=CloseView(ctx.author.id),
        )

    # ── $si (server info) ─────────────────────────────────────────────────────

    @commands.command(name="si")
    @commands.guild_only()
    async def si_prefix(self, ctx):
        g = ctx.guild
        roles = len(g.roles) - 1
        desc = (
            f"{DIV}\n"
            f"{E['id']} **Server ID** {S['bullet']} `{g.id}`\n"
            f"{E['owner']} **Owner** {S['bullet']} <@{g.owner_id}>\n"
            f"{E['id']} **Members** {S['bullet']} `{g.member_count}`\n"
            f"{E['server']} **Channels** {S['bullet']} `{len(g.text_channels)}` text / `{len(g.voice_channels)}` voice\n"
            f"{E['admin']} **Roles** {S['bullet']} `{roles}`\n"
            f"{E['time']} **Created** {S['bullet']} <t:{int(g.created_at.timestamp())}:D>\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['server']} {g.name}", description=desc, color=COLOR["info"])
        em.set_thumbnail(url=g.icon.url if g.icon else None)
        em.set_footer(text=f"Boost Level: {g.premium_tier} • Boosts: {g.premium_subscription_count}")
        await ctx.send(embed=em, view=CloseView(ctx.author.id))

    # ── Tip logic ─────────────────────────────────────────────────────────────

    async def _do_tip(self, channel, sender: discord.Member, recipient: discord.Member,
                      coin_code: str, usd_amount: float):
        uid, rid = str(sender.id), str(recipient.id)

        if recipient.bot:
            return False, "Cannot tip bots."
        if uid == rid:
            return False, "Cannot tip yourself."
        if not is_valid_coin(coin_code):
            return False, f"Unknown coin `{coin_code}`. Supported: {', '.join(symbol(c) for c in ORDER)}"
        if usd_amount <= 0:
            return False, "Amount must be positive."

        price = await get_usd_price(coin_code)
        if price <= 0:
            return False, "Couldn't fetch a live price — try again shortly."
        amount = round(usd_amount / price, 8)

        await ensure_user(uid, sender.name)
        await ensure_user(rid, recipient.name)
        sender_balances = await get_all_balances(uid)
        sender_bal = sender_balances.get(coin_code, {}).get("balance", 0) or 0
        if sender_bal < amount:
            return False, f"You only have {fmt_coin(sender_bal, coin_code)} (~${sender_bal * price:.2f})"

        await update_balance(uid, coin_code, -amount)
        await update_balance(rid, coin_code, amount)
        await add_log(
            str(channel.guild.id) if channel.guild else "DM", uid, "TIP",
            f"{uid}→{rid}: {amount} {coin_code}",
        )

        usd_str = f"${usd_amount:,.2f}"
        desc = (
            f"{DIV}\n"
            f"{E['tag']} **To** {S['bullet']} {recipient.mention}\n"
            f"{coin_emoji(coin_code)} **Amount** {S['bullet']} {usd_str} {S['double']} {fmt_coin(amount, coin_code)}\n"
            f"{DIV}"
        )
        await channel.send(embed=discord.Embed(
            title=f"{E['gift']} Tip Sent!", description=desc, color=COLOR["success"]
        ))

        try:
            dm_desc = (
                f"{DIV}\n"
                f"{E['gift']} **From** {S['bullet']} {sender.mention}\n"
                f"{coin_emoji(coin_code)} **Amount** {S['bullet']} {usd_str} {S['double']} {fmt_coin(amount, coin_code)}\n"
                f"{DIV}"
            )
            await recipient.send(embed=discord.Embed(
                title=f"{E['gift']} You Got Tipped!", description=dm_desc, color=COLOR["success"]
            ))
        except Exception:
            pass

        return True, None

    @app_commands.command(name="tip", description="Tip another user crypto")
    @app_commands.describe(user="Recipient", coin="Which coin", usd_amount="Amount in USD ($)")
    @app_commands.choices(coin=coin_choices())
    async def tip(self, interaction: discord.Interaction, user: discord.Member,
                  coin: app_commands.Choice[str], usd_amount: float):
        await interaction.response.defer()
        ok, err = await self._do_tip(interaction.channel, interaction.user, user, coin.value, usd_amount)
        if not ok:
            await interaction.followup.send(embed=embed_error("Tip Failed", err), ephemeral=True)
        else:
            await interaction.delete_original_response()

    @commands.command(name="tip")
    async def tip_prefix(self, ctx, user: discord.Member = None, usd_amount: str = None, coin_code: str = "ltc"):
        if user is None or usd_amount is None:
            coins_list = " | ".join(symbol(c) for c in ORDER)
            desc = (
                f"{DIV}\n"
                f"{E['gift']} **Usage:** `$tip @user <amount_usd> [coin]`\n"
                f"{E['arrow1']} **Example:** `$tip @Alice 5 ltc`\n"
                f"{E['arrow1']} **Coins:** {coins_list}\n"
                f"{DIV}"
            )
            return await ctx.send(embed=discord.Embed(
                title=f"{E['gift']} Tip Crypto", description=desc, color=COLOR["info"]
            ), view=CloseView(ctx.author.id))

        try:
            usd_amount_f = float(usd_amount.replace("$", ""))
        except ValueError:
            return await ctx.send(embed=embed_error("Invalid Amount", "Amount must be a number like `5` or `5.50`"))

        ok, err = await self._do_tip(ctx.channel, ctx.author, user, coin_code.lower(), usd_amount_f)
        if not ok:
            await ctx.send(embed=embed_error("Tip Failed", err))

    # ── @XWALLET mention listener ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user:
            return

        # Must start with @XWALLET mention
        uid_pattern = rf"^<@!?{self.bot.user.id}>"
        if not re.match(uid_pattern, message.content):
            return

        rest = re.sub(rf"^<@!?{self.bot.user.id}>\s*", "", message.content).strip()
        cmd = rest.lower()

        # ── @XWALLET balance [@user] ──────────────────────────────────────────
        if cmd.startswith("balance") or cmd.startswith("bal"):
            mentioned = [m for m in message.mentions if not m.bot and m != self.bot.user]
            target = mentioned[0] if mentioned else message.author
            if not isinstance(target, discord.Member) and message.guild:
                try:
                    target = await message.guild.fetch_member(target.id)
                except Exception:
                    pass
            await ensure_user(str(target.id), target.name)
            balances = await get_all_balances(str(target.id))
            em = await smart_wallet_embed(target, balances)
            await message.channel.send(embed=em, view=CloseView(message.author.id))
            return

        # ── @XWALLET tip $<amount> <coin> @user ──────────────────────────────
        tip_m = re.match(
            r"tip\s+\$?([\d.]+)\$?\s+(\w+)\s+<@!?(\d+)>",
            rest, re.IGNORECASE
        )
        if tip_m:
            usd_amount = float(tip_m.group(1))
            coin_code  = tip_m.group(2).lower()
            recipient_id = int(tip_m.group(3))
            recipient = message.guild.get_member(recipient_id) if message.guild else None
            if not recipient:
                try:
                    recipient = await self.bot.fetch_user(recipient_id)
                except Exception:
                    return await message.channel.send(embed=embed_error("User Not Found", ""))
            ok, err = await self._do_tip(message.channel, message.author, recipient, coin_code, usd_amount)
            if not ok:
                await message.channel.send(embed=embed_error("Tip Failed", err))
            return

        # ── @XWALLET wd ───────────────────────────────────────────────────────
        if cmd.startswith("wd") or cmd.startswith("withdraw"):
            try:
                await message.author.send(
                    embed=discord.Embed(
                        title=f"{E['withdraw']} Withdraw Crypto",
                        description=(
                            f"{DIV}\nUse `/withdraw` to open the guided withdrawal panel in DMs.\n{DIV}"
                        ),
                        color=COLOR["info"],
                    )
                )
                await message.channel.send(
                    embed=discord.Embed(
                        description=f"{E['notify']} {message.author.mention}, check your DMs for the withdrawal panel.",
                        color=COLOR["info"],
                    )
                )
            except discord.Forbidden:
                await message.channel.send(
                    embed=embed_error("DMs Closed", f"{message.author.mention}, please enable DMs.")
                )
            return

        # ── @XWALLET depo ─────────────────────────────────────────────────────
        if cmd.startswith("depo") or cmd.startswith("deposit"):
            try:
                await message.author.send(
                    embed=discord.Embed(
                        title=f"{E['deposit']} Deposit Crypto",
                        description=(
                            f"{DIV}\nUse `/deposit` to open the guided deposit panel in DMs.\n{DIV}"
                        ),
                        color=COLOR["info"],
                    )
                )
                await message.channel.send(
                    embed=discord.Embed(
                        description=f"{E['notify']} {message.author.mention}, check your DMs for the deposit panel.",
                        color=COLOR["info"],
                    )
                )
            except discord.Forbidden:
                await message.channel.send(
                    embed=embed_error("DMs Closed", f"{message.author.mention}, please enable DMs.")
                )
            return

        # ── @XWALLET lb <coin> ────────────────────────────────────────────────
        lb_m = re.match(r"(?:lb|leaderboard|top|rich)\s+(\w+)", rest, re.IGNORECASE)
        if lb_m:
            coin_code = lb_m.group(1).lower()
            if not is_valid_coin(coin_code):
                return await message.channel.send(
                    embed=embed_error("Unknown Coin", f"Supported: {', '.join(symbol(c) for c in ORDER)}")
                )
            top = await get_top_holders(coin_code, limit=10)
            if not top:
                return await message.channel.send(
                    embed=embed_error("No Data", f"No {symbol(coin_code)} holders yet.")
                )
            medals = ["🥇", "🥈", "🥉"]
            lines = [
                f"{medals[i] if i < 3 else f'`{i+1}.`'} **{u['username'] or 'Unknown'}** {S['bullet']} {fmt_coin(u['balance'], coin_code)}"
                for i, u in enumerate(top)
            ]
            await message.channel.send(embed=discord.Embed(
                title=f"{E['diamond']} {symbol(coin_code)} Leaderboard",
                description=f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}",
                color=COLOR["gold"],
            ))
            return

        # ── @XWALLET help / unknown ───────────────────────────────────────────
        coins_list = " | ".join(symbol(c) for c in ORDER)
        help_desc = (
            f"{DIV}\n"
            f"{E['gift']} **Tip** {S['bullet']} `@XWALLET tip $<amount> <coin> @user`\n"
            f"{E['balance']} **Balance** {S['bullet']} `@XWALLET balance [@user]`\n"
            f"{E['withdraw']} **Withdraw** {S['bullet']} `@XWALLET wd`\n"
            f"{E['deposit']} **Deposit** {S['bullet']} `@XWALLET depo`\n"
            f"{E['diamond']} **Leaderboard** {S['bullet']} `@XWALLET lb <coin>`\n"
            f"{DIV}\n"
            f"{E['arrow1']} **Coins:** {coins_list}\n"
            f"{DIV}"
        )
        await message.channel.send(embed=discord.Embed(
            title=f"{E['notify']} XWALLET Commands",
            description=help_desc,
            color=COLOR["primary"],
        ))

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Top holders of a specific coin")
    @app_commands.describe(coin="Which coin's leaderboard")
    @app_commands.choices(coin=coin_choices())
    async def leaderboard(self, interaction: discord.Interaction, coin: app_commands.Choice[str]):
        await interaction.response.defer()
        coin_code = coin.value
        top = await get_top_holders(coin_code, limit=10)
        if not top:
            return await interaction.followup.send(
                embed=embed_error("No Data", f"No {symbol(coin_code)} holders yet.")
            )
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, u in enumerate(top):
            rank = medals[i] if i < 3 else f"`{i+1}.`"
            name = u["username"] or f"User {u['user_id'][:6]}"
            lines.append(f"{rank} **{name}** {S['bullet']} {fmt_coin(u['balance'], coin_code)}")
        em = discord.Embed(
            title=f"{E['diamond']} Richest in {coin_label(coin_code)}",
            description=f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}",
            color=COLOR["gold"],
        )
        em.set_footer(text=f"Top 10 by available {symbol(coin_code)} balance")
        await interaction.followup.send(embed=em)

    @commands.command(name="leaderboard", aliases=["lb", "top", "rich"])
    async def leaderboard_prefix(self, ctx, coin_code: str = None):
        if coin_code is None:
            coins_list = " | ".join(symbol(c) for c in ORDER)
            desc = (
                f"{DIV}\n"
                f"{E['diamond']} **Usage:** `$lb <coin>`\n"
                f"{E['arrow1']} **Coins:** {coins_list}\n"
                f"{DIV}"
            )
            return await ctx.send(embed=discord.Embed(
                title=f"{E['diamond']} Leaderboard", description=desc, color=COLOR["gold"]
            ), view=CloseView(ctx.author.id))

        coin_code = coin_code.lower()
        if not is_valid_coin(coin_code):
            return await ctx.send(embed=embed_error("Invalid Coin", f"Supported: {' | '.join(symbol(c) for c in ORDER)}"))
        msg = await ctx.send(embed=embed_processing("Loading leaderboard…"))
        top = await get_top_holders(coin_code, limit=10)
        if not top:
            return await msg.edit(embed=embed_error("No Data", "No holders yet."))
        lines = [
            f"`{i+1}.` **{u['username'] or 'Unknown'}** {S['bullet']} {fmt_coin(u['balance'], coin_code)}"
            for i, u in enumerate(top)
        ]
        await msg.edit(
            embed=discord.Embed(
                title=f"{E['diamond']} {symbol(coin_code)} Leaderboard",
                description=f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}",
                color=COLOR["gold"],
            ),
            view=CloseView(ctx.author.id),
        )


async def setup(bot):
    await bot.add_cog(Economy(bot))
