"""
XWALLET Rules Cog — /rules, plus first-interaction onboarding DM.
Same content shown both ways so there's one source of truth.
"""

import discord
from discord.ext import commands
from discord import app_commands
from bot.utils.database import ensure_user, is_onboarded, mark_onboarded
from bot.utils.embeds import E, S, DIV, COLOR
from bot.utils.coins import COINS, ORDER, symbol


def rules_embed() -> discord.Embed:
    coin_list = ", ".join(symbol(c) for c in ORDER)
    desc = (
        f"{DIV}\n"
        f"{E['xwallet']} **Welcome to XWALLET** — a crypto tip wallet for this server.\n"
        f"{DIV}\n"
        f"{E['deposit']} `/deposit` {S['bullet']} Add funds (opens in your DMs)\n"
        f"{E['withdraw']} `/withdraw` {S['bullet']} Cash out (opens in your DMs)\n"
        f"{E['gift']} `/tip` or `@XWALLET tip 10$ ltc @user` {S['bullet']} Send crypto instantly\n"
        f"{E['balance']} `/balance` {S['bullet']} Check your wallet\n"
        f"{DIV}\n"
        f"{E['secure']} **Good to know**\n"
        f"{S['bullet']} Supported coins: {coin_list}\n"
        f"{S['bullet']} Deposits/withdrawals always need a one-time address confirmation\n"
        f"{S['bullet']} A small fee applies to deposits and withdrawals\n"
        f"{S['bullet']} Withdrawals are reviewed before payout — this protects everyone\n"
        f"{DIV}\n"
        f"{E['admin']} Never share your private keys or seed phrase with anyone, including staff.\n"
        f"XWALLET will never DM you first asking for them.\n{DIV}"
    )
    return discord.Embed(title=f"{E['xwallet']} XWALLET — Rules & Guide", description=desc, color=COLOR["primary"])


class Rules(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rules", description="View XWALLET's rules and quick guide")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=rules_embed(), ephemeral=True)

    @commands.command(name="rules")
    async def rules_prefix(self, ctx):
        await ctx.send(embed=rules_embed())

    async def maybe_onboard(self, user: discord.User):
        """Call this from anywhere a user first interacts with the bot.
        DMs the rules exactly once per user."""
        uid = str(user.id)
        await ensure_user(uid, user.name)
        if await is_onboarded(uid):
            return
        try:
            await user.send(embed=rules_embed())
        except Exception:
            pass  # DMs closed — they can still run /rules manually
        await mark_onboarded(uid)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Covers prefix commands too — on_interaction in main.py only
        fires for slash commands."""
        if message.author.bot:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:  # only onboard on an actual recognized command
            await self.maybe_onboard(message.author)


async def setup(bot):
    await bot.add_cog(Rules(bot))
