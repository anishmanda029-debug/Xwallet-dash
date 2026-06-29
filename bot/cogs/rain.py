"""
Rain Cog — /rain (LTC only). Live countdown, claim buttons, animated embed
updates. Host rains a fixed amount of LTC into a channel; claimers split it
randomly when the timer ends.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio, json, random
from datetime import datetime, timedelta
from bot.utils.database import (
    ensure_user, get_all_balances, update_balance, create_rain,
    get_rain, update_rain_claimers, end_rain, get_active_rains, add_log
)
from bot.utils.embeds import E, DIV, COLOR, embed_error, embed_processing, fmt_coin, coin_to_usd_str
from bot.utils.currency import min_coin_amount

RAIN_DURATION = 60   # seconds
RAIN_COIN     = "ltc"


def rain_embed(host: discord.Member, amount: float, claimers: list, end_time: datetime, ended=False) -> discord.Embed:
    now       = datetime.utcnow()
    remaining = max(0, (end_time - now).total_seconds())
    m, s      = divmod(int(remaining), 60)

    if ended:
        status = f"{E['tick']} Rain ended — **{len(claimers)}** claimed!"
        color  = COLOR["success"]
        timer  = "`Ended`"
    else:
        status = f"{E['loading']} Active — click **☔ Claim** to grab LTC!"
        color  = COLOR["primary"]
        timer  = f"`{m:02d}:{s:02d}`"

    per   = amount / max(len(claimers), 1) if claimers else amount
    split = f"~{fmt_coin(per, RAIN_COIN)} each" if claimers else "All yours if 1 claims!"

    desc = (
        f"{DIV}\n"
        f"{E['shop']} **Total** · {fmt_coin(amount, RAIN_COIN)}\n"
        f"{DIV}\n"
        f"{E['members']} **Claimers** · `{len(claimers)}` — {split}\n"
        f"⏱️ **Time Left** · {timer}\n"
        f"{DIV}\n"
    )
    if claimers:
        names = ", ".join(f"<@{c}>" for c in claimers[:8])
        if len(claimers) > 8:
            names += f" +{len(claimers)-8} more"
        desc += f"{E['gift']} **Claimed by** · {names}\n{DIV}\n"
    desc += status

    em = discord.Embed(title="☔ LTC Rain!", description=desc, color=color)
    em.set_footer(text=f"Hosted by {host.display_name} · XWALLET")
    return em


class ClaimView(discord.ui.View):
    def __init__(self, message_id: str, host: discord.Member, amount: float, end_time: datetime):
        super().__init__(timeout=RAIN_DURATION + 10)
        self.message_id = message_id
        self.host       = host
        self.amount     = amount
        self.end_time   = end_time

    @discord.ui.button(label="☔ Claim Rain", style=discord.ButtonStyle.primary, emoji="☔")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid  = str(interaction.user.id)
        rain = await get_rain(self.message_id)
        if not rain or rain["status"] != "active":
            return await interaction.response.send_message(embed=embed_error("Ended", "This rain has already ended."), ephemeral=True)
        claimers = json.loads(rain["claimers"] or "[]")
        if uid in claimers:
            return await interaction.response.send_message(embed=embed_error("Already Claimed", "You already claimed from this rain!"), ephemeral=True)
        if uid == rain["host_id"]:
            return await interaction.response.send_message(embed=embed_error("Not Allowed", "You can't claim your own rain."), ephemeral=True)
        claimers.append(uid)
        await update_rain_claimers(self.message_id, claimers)
        await ensure_user(uid, interaction.user.name)

        em = discord.Embed(
            title=f"{E['tick']} Claimed!",
            description=(f"{DIV}\n{E['loading']} LTC will be distributed when the rain ends.\n"
                          f"{E['members']} `{len(claimers)}` people have claimed so far.\n{DIV}"),
            color=COLOR["success"],
        )
        await interaction.response.send_message(embed=em, ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(int(self.message_id))
            await msg.edit(embed=rain_embed(self.host, self.amount, claimers, self.end_time))
        except Exception:
            pass


class Rain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rain_checker.start()

    def cog_unload(self):
        self.rain_checker.cancel()

    @tasks.loop(seconds=5)
    async def rain_checker(self):
        try:
            rains = await get_active_rains()
            for rain in rains:
                end_time = datetime.fromisoformat(rain["end_time"])
                if datetime.utcnow() >= end_time:
                    await self._finalize(rain)
        except Exception:
            pass

    @rain_checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    async def _finalize(self, rain):
        try:
            claimers = json.loads(rain["claimers"] or "[]")
            amount   = float(rain["amount"])
            channel  = self.bot.get_channel(int(rain["channel_id"]))
            if not channel:
                return
            await end_rain(rain["message_id"])

            if not claimers:
                em = discord.Embed(
                    title="☔ Rain Ended",
                    description=f"{DIV}\n{E['mute']} Nobody claimed. LTC refunded to host.\n{DIV}",
                    color=COLOR["error"],
                )
                try:
                    msg = await channel.fetch_message(int(rain["message_id"]))
                    await msg.edit(embed=em, view=None)
                except Exception:
                    pass
                await update_balance(rain["host_id"], RAIN_COIN, amount)
                return

            # Split randomly, keep 8 decimal precision
            splits  = [random.random() for _ in claimers]
            total   = sum(splits)
            amounts = [round(amount * (s / total), 8) for s in splits]
            diff    = round(amount - sum(amounts), 8)
            amounts[0] = round(amounts[0] + diff, 8)

            for uid, share in zip(claimers, amounts):
                await ensure_user(uid)
                if share > 0:
                    await update_balance(uid, RAIN_COIN, share)

            host = self.bot.get_user(int(rain["host_id"]))
            if not host:
                try:
                    host = await self.bot.fetch_user(int(rain["host_id"]))
                except Exception:
                    host = None

            if host:
                end_dt = datetime.fromisoformat(rain["end_time"])
                try:
                    msg = await channel.fetch_message(int(rain["message_id"]))
                    await msg.edit(embed=rain_embed(host, amount, claimers, end_dt, ended=True), view=None)
                except Exception:
                    pass

            lines = [f"<@{uid}> → **{fmt_coin(share, RAIN_COIN)}**" for uid, share in zip(claimers, amounts)][:15]
            if len(claimers) > 15:
                lines.append(f"… and {len(claimers)-15} more")

            sum_em = discord.Embed(
                title=f"{E['gift']} Rain Distribution",
                description=f"{DIV}\n" + "\n".join(lines) + f"\n{DIV}",
                color=COLOR["gold"],
            )
            await channel.send(embed=sum_em)
            await add_log(rain["guild_id"], rain["host_id"], "RAIN_END", f"{amount} LTC to {len(claimers)} users")
        except Exception:
            pass

    # ── /rain ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="rain", description="Rain LTC for others to claim!")
    @app_commands.describe(amount="Total LTC to rain")
    async def rain_cmd(self, interaction: discord.Interaction, amount: float):
        await interaction.response.defer()
        uid = str(interaction.user.id)

        min_amt = await min_coin_amount(RAIN_COIN)
        if amount < min_amt:
            return await interaction.followup.send(embed=embed_error("Too Low", f"Minimum rain: {fmt_coin(min_amt, RAIN_COIN)}"), ephemeral=True)

        await ensure_user(uid, interaction.user.name)
        balances = await get_all_balances(uid)
        bal = balances.get(RAIN_COIN, {}).get("balance", 0) or 0
        if bal < amount:
            return await interaction.followup.send(embed=embed_error("Insufficient Funds", f"Balance: {fmt_coin(bal, RAIN_COIN)}"), ephemeral=True)

        proc = embed_processing("Preparing rain…")
        msg  = await interaction.followup.send(embed=proc)
        await asyncio.sleep(1.2)

        await update_balance(uid, RAIN_COIN, -amount)
        end_time = datetime.utcnow() + timedelta(seconds=RAIN_DURATION)
        view     = ClaimView(str(msg.id), interaction.user, amount, end_time)

        await msg.edit(embed=rain_embed(interaction.user, amount, [], end_time), view=view)
        await create_rain(str(msg.id), str(interaction.channel_id), str(interaction.guild_id), uid, RAIN_COIN, amount, end_time)

        for _ in range(RAIN_DURATION // 10):
            await asyncio.sleep(10)
            rain = await get_rain(str(msg.id))
            if not rain or rain["status"] != "active":
                break
            claimers = json.loads(rain["claimers"] or "[]")
            try:
                await msg.edit(embed=rain_embed(interaction.user, amount, claimers, end_time))
            except Exception:
                break

        await add_log(str(interaction.guild_id), uid, "RAIN_START", f"{amount} LTC")

    @commands.command(name="rain")
    async def rain_prefix(self, ctx, amount: float = 0):
        uid = str(ctx.author.id)
        min_amt = await min_coin_amount(RAIN_COIN)
        if amount < min_amt:
            return await ctx.send(embed=embed_error("Too Low", f"Min: {fmt_coin(min_amt, RAIN_COIN)}"))
        await ensure_user(uid, ctx.author.name)
        balances = await get_all_balances(uid)
        bal = balances.get(RAIN_COIN, {}).get("balance", 0) or 0
        if bal < amount:
            return await ctx.send(embed=embed_error("Insufficient", f"Balance: {fmt_coin(bal, RAIN_COIN)}"))
        msg = await ctx.send(embed=embed_processing("Preparing rain…"))
        await asyncio.sleep(1)
        await update_balance(uid, RAIN_COIN, -amount)
        end_time = datetime.utcnow() + timedelta(seconds=RAIN_DURATION)
        view     = ClaimView(str(msg.id), ctx.author, amount, end_time)
        await msg.edit(embed=rain_embed(ctx.author, amount, [], end_time), view=view)
        await create_rain(str(msg.id), str(ctx.channel.id), str(ctx.guild.id), uid, RAIN_COIN, amount, end_time)


async def setup(bot):
    await bot.add_cog(Rain(bot))
