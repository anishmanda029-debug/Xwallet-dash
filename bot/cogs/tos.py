"""
XWALLET Terms of Service / Terms & Conditions
- /terms — show current T&C (all users)
- $settos <text> — owner sets T&C (supports multiline with \\n)
- $viewtos — view raw T&C text
- T&C stored in database, changeable anytime by owner
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

from bot.utils.embeds import E, S, DIV, COLOR, embed_error, embed_success
from bot.utils.checks import dev_prefix_only, OWNER_IDS, STAFF_IDS
from bot.utils.database import _execute, _fetchone

DEFAULT_TOS = """**1. Eligibility**
You must be 18+ to use XWALLET. By using this bot you confirm you meet this requirement.

**2. Accepted Use**
XWALLET is a crypto tip and wallet bot. You may deposit, withdraw, tip, and transfer supported currencies within Discord.

**3. Prohibited Activities**
• Money laundering or financing illegal activities
• Exploiting bugs or attempting to steal funds
• Creating multiple accounts to abuse bonuses
• Any activity that violates Discord's Terms of Service

**4. No Liability**
XWALLET is not responsible for lost funds due to incorrect wallet addresses provided by users, network failures, or force majeure events.

**5. Fees**
A small network fee may be charged on withdrawals. Fee details are shown on every invoice before you confirm.

**6. Privacy**
We store your Discord ID and transaction history to operate the bot. No private keys or personal data are shared with third parties.

**7. Changes**
These terms may be updated at any time. Continued use of XWALLET constitutes acceptance of the updated terms.

**8. Contact**
For support, open a ticket or contact the server owner."""


async def get_tos() -> str:
    try:
        row = await _fetchone("SELECT value FROM bot_settings WHERE key='tos'", ())
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return DEFAULT_TOS


async def set_tos(text: str):
    await _execute(
        "INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('tos', ?)",
        (text,)
    )


async def get_tos_updated() -> str:
    try:
        row = await _fetchone("SELECT value FROM bot_settings WHERE key='tos_updated'", ())
        return row["value"] if row else "Never"
    except Exception:
        return "Never"


class TOS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /terms ────────────────────────────────────────────────────────────────
    @app_commands.command(name="terms", description="📜 View XWALLET Terms & Conditions")
    async def terms(self, interaction: discord.Interaction):
        tos_text = await get_tos()
        updated  = await get_tos_updated()

        # Split into chunks if too long
        chunks = []
        lines  = tos_text.split("\n")
        chunk  = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 3800:
                chunks.append(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk:
            chunks.append(chunk)

        # First embed
        em = discord.Embed(
            title=f"{E['secure']} XWALLET Terms & Conditions",
            description=f"{DIV}\n{chunks[0]}\n{DIV}",
            color=COLOR["primary"],
        )
        em.set_footer(text=f"Last updated: {updated} • Use /help for commands")
        await interaction.response.send_message(embed=em, ephemeral=True)

        # Additional chunks if needed
        for chunk in chunks[1:]:
            em2 = discord.Embed(description=chunk, color=COLOR["primary"])
            await interaction.followup.send(embed=em2, ephemeral=True)

    @commands.command(name="terms", aliases=["tos", "tc"])
    async def terms_prefix(self, ctx):
        """View Terms & Conditions."""
        tos_text = await get_tos()
        updated  = await get_tos_updated()
        em = discord.Embed(
            title=f"{E['secure']} XWALLET Terms & Conditions",
            description=f"{DIV}\n{tos_text[:3800]}\n{DIV}",
            color=COLOR["primary"],
        )
        em.set_footer(text=f"Last updated: {updated}")
        await ctx.send(embed=em)

    # ── $settos <text> ────────────────────────────────────────────────────────
    @commands.command(name="settos", aliases=["settoc", "setterms"], hidden=True)
    @dev_prefix_only()
    async def settos(self, ctx, *, text: str):
        """Set Terms & Conditions. Use \\n for new lines."""
        # Allow \\n in text to become actual newlines
        text = text.replace("\\n", "\n")
        await set_tos(text)
        now = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
        await _execute(
            "INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('tos_updated', ?)",
            (now,)
        )
        desc = (
            f"{DIV}\n"
            f"{E['tick']} Terms updated successfully.\n"
            f"{E['time']} **Updated at** {S['bullet']} `{now}`\n"
            f"{E['notify']} Users can view with `/terms` or `$terms`\n"
            f"{DIV}"
        )
        await ctx.send(embed=discord.Embed(
            title=f"{E['secure']} Terms Updated",
            description=desc,
            color=COLOR["success"]
        ))

    # ── $viewtos ──────────────────────────────────────────────────────────────
    @commands.command(name="viewtos", aliases=["rawtos"], hidden=True)
    @dev_prefix_only()
    async def viewtos(self, ctx):
        """View raw T&C text (admin only)."""
        tos_text = await get_tos()
        updated  = await get_tos_updated()
        # Send as file if too long
        if len(tos_text) > 1800:
            import io
            await ctx.send(
                content=f"{E['history']} Current T&C (last updated: {updated})",
                file=discord.File(io.StringIO(tos_text), filename="terms.txt")
            )
        else:
            await ctx.send(embed=discord.Embed(
                title=f"{E['history']} Current T&C (raw)",
                description=f"```\n{tos_text[:1800]}\n```\nLast updated: {updated}",
                color=COLOR["info"]
            ))


async def setup(bot):
    await bot.add_cog(TOS(bot))
