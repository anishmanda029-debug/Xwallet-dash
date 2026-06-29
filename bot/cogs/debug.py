"""
Debug Cog — /debug, Owner-only diagnostics panel.
Surfaces the kind of silent failures that are otherwise invisible: missing
permissions, unconfigured API keys, failed cogs, DB connectivity, latency,
and the current deposit/withdraw method per coin.
"""

import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import platform
from datetime import datetime
from bot.utils.database import get_pool, get_detection_method, get_withdraw_method
from bot.utils.embeds import E, S, DIV, COLOR
from bot.utils.checks import OWNER_ID
from bot.utils import alchemy
from bot.utils.coins import ORDER, symbol

START_TIME = time.time()


class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="debug", description="[Owner] Bot diagnostics panel")
    async def debug(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                embed=discord.Embed(title=f"{E['error']} Owner Only", description="This command is restricted to the bot owner.", color=COLOR["error"]),
                ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        # ── Cog load status ───────────────────────────────────────────────
        loaded = list(self.bot.cogs.keys())
        from bot.main import COGS
        expected = [c.split(".")[-1] for c in COGS]
        loaded_lower = {c.lower() for c in loaded}
        failed = [c for c in expected if c.lower() not in loaded_lower]
        cog_status = f"{E['tick']} `{len(loaded)}` loaded" + (f"\n{E['error']} Failed: `{', '.join(failed)}`" if failed else "")

        # ── Database check ────────────────────────────────────────────────
        db_status = f"{E['tick']} Connected"
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
        except Exception as e:
            db_status = f"{E['error']} Error: `{str(e)[:80]}`"

        # ── Alchemy config ──────────────────────────────────────────────────
        alchemy_status = f"{E['tick']} API key set" if alchemy.is_configured() else f"{E['error']} `ALCHEMY_API_KEY` not set"
        signing_status = f"{E['tick']} Signing key set" if os.getenv("ALCHEMY_SIGNING_KEY") else f"{E['error']} `ALCHEMY_SIGNING_KEY` not set (webhook unverified!)"
        public_url = os.getenv("PUBLIC_URL", "") or "Not set"
        watcher_secret = f"{E['tick']} Set" if os.getenv("WATCHER_SHARED_SECRET") else f"{E['error']} `WATCHER_SHARED_SECRET` not set"

        # ── Per-coin detection/withdraw methods ─────────────────────────────
        method_lines = []
        for c in ORDER:
            dep_m = await get_detection_method(c)
            wd_m = await get_withdraw_method(c)
            method_lines.append(f"{E['payment']} **{symbol(c)}** {S['bullet']} dep:`{dep_m}` wd:`{wd_m}`")

        # ── Per-guild permission check ───────────────────────────────────────
        guild_lines = []
        for guild in self.bot.guilds[:10]:
            me = guild.me
            perms = me.guild_permissions
            issues = []
            if not perms.send_messages:
                issues.append("Send Messages")
            if not perms.embed_links:
                issues.append("Embed Links")
            if not perms.manage_channels:
                issues.append("Manage Channels (tickets)")
            status = f"{E['tick']}" if not issues else f"{E['mute']} missing: {', '.join(issues)}"
            guild_lines.append(f"{status} **{guild.name}**")
        guild_block = "\n".join(guild_lines) if guild_lines else "No guilds."
        if len(self.bot.guilds) > 10:
            guild_block += f"\n…and {len(self.bot.guilds) - 10} more"

        # ── Env var presence (never show actual values) ────────────────────
        env_checks = {
            "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
            "OWNER_ID": os.getenv("OWNER_ID"),
            "OWNER_PASSWORD": os.getenv("OWNER_PASSWORD"),
            "WATCHER_SHARED_SECRET": os.getenv("WATCHER_SHARED_SECRET"),
            "ALCHEMY_API_KEY": os.getenv("ALCHEMY_API_KEY"),
            "ALCHEMY_SIGNING_KEY": os.getenv("ALCHEMY_SIGNING_KEY"),
            "PUBLIC_URL": os.getenv("PUBLIC_URL"),
            "LTC_ADDRESS": os.getenv("LTC_ADDRESS"),
            "BTC_ADDRESS": os.getenv("BTC_ADDRESS"),
            "ETH_ADDRESS": os.getenv("ETH_ADDRESS"),
            "SOL_ADDRESS": os.getenv("SOL_ADDRESS"),
        }
        env_lines = [f"{E['tick'] if v else E['error']} `{k}`" for k, v in env_checks.items()]

        uptime_s = int(time.time() - START_TIME)
        d, r = divmod(uptime_s, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)

        desc = (
            f"{DIV}\n"
            f"{E['admin']} **System**\n"
            f"{E['qr']} Python `{platform.python_version()}` {S['bullet']} discord.py `{discord.__version__}`\n"
            f"{E['tick']} Uptime `{d}d {h}h {m}m {s}s` {S['bullet']} Latency `{round(self.bot.latency*1000)}ms`\n"
            f"{DIV}\n"
            f"{E['admin']} **Cogs**\n{cog_status}\n"
            f"{DIV}\n"
            f"{E['secure']} **Database**\n{db_status}\n"
            f"{DIV}\n"
            f"{E['payment']} **Alchemy**\n{alchemy_status}\n{signing_status}\n"
            f"{E['secure']} Watcher Secret: {watcher_secret}\n"
            f"{E['qr']} Public URL: `{public_url}`\n"
            f"{DIV}\n"
            f"{E['payment']} **Deposit / Withdraw Methods**\n" + "\n".join(method_lines) + f"\n"
            f"{DIV}\n"
            f"{E['history']} **Environment Variables**\n" + "\n".join(env_lines) + f"\n"
            f"{DIV}\n"
            f"{E['profile']} **Guild Permissions** (first 10)\n{guild_block}\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{E['admin']} Debug Panel", description=desc, color=COLOR["dark"], timestamp=datetime.utcnow())
        em.set_footer(text=f"{len(self.bot.guilds)} guild(s) · {sum(g.member_count for g in self.bot.guilds)} users")
        await interaction.followup.send(embed=em, ephemeral=True)

    @commands.command(name="debug")
    async def debug_prefix(self, ctx):
        if ctx.author.id != OWNER_ID:
            return
        loaded = list(self.bot.cogs.keys())
        db_status = f"{E['tick']} Connected"
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
        except Exception as e:
            db_status = f"{E['error']} {str(e)[:60]}"
        desc = (f"{DIV}\nCogs loaded: `{len(loaded)}`\nDB: {db_status}\n"
                f"Latency: `{round(self.bot.latency*1000)}ms`\n{DIV}")
        await ctx.send(embed=discord.Embed(title=f"{E['admin']} Debug", description=desc, color=COLOR["dark"]))


async def setup(bot):
    await bot.add_cog(Debug(bot))
