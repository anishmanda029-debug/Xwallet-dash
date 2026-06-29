"""
XWALLET Help Menu — Full command list with category selector.
Admin/Owner/Dev section visible ONLY in HOME_GUILD_ID.
"""

import discord
from discord.ext import commands
from discord import app_commands
import os

from bot.utils.embeds import E, DIV, COLOR, S
from bot.utils.checks import STAFF_IDS, HOME_GUILD_ID

# ── Category definitions ─────────────────────────────────────────────────────

PUBLIC_CATEGORIES = {
    "wallet": {
        "emoji": "💰",
        "label": "Wallet",
        "color": COLOR["gold"],
        "cmds": [
            ("/balance [user]",   "View your (or another user's) wallet — only coins with balance are shown"),
            ("$bal / $w [user]",  "Prefix shortcut for wallet"),
            ("/tip @user coin $", "Tip crypto to another user"),
            ("$tip @user $ coin", "Prefix tip — `$tip @Alice 5 ltc`"),
            ("@XWALLET tip 5$ ltc @user", "Mention-style tipping"),
        ],
    },
    "deposit": {
        "emoji": "📥",
        "label": "Deposit",
        "color": COLOR["success"],
        "cmds": [
            ("/deposit",   "Open deposit panel — get your address & QR code (DM only)"),
            ("$depo [coin]", "Prefix deposit shortcut — shows instructions"),
        ],
    },
    "withdraw": {
        "emoji": "📤",
        "label": "Withdraw",
        "color": COLOR["primary"],
        "cmds": [
            ("/withdraw",           "Open withdrawal panel (DM only)"),
            ("$wd <coin> <amount> <address>", "Prefix withdraw — `$wd ltc 0.5 LTC123...`"),
        ],
    },
    "rain": {
        "emoji": "🌧️",
        "label": "Rain",
        "color": COLOR["info"],
        "cmds": [
            ("/rain",  "Start a rain drop event for active members"),
            ("$rain",  "Prefix rain shortcut"),
        ],
    },
    "leaderboard": {
        "emoji": "🏆",
        "label": "Leaderboard",
        "color": COLOR["gold"],
        "cmds": [
            ("/leaderboard <coin>", "Top 10 holders of a coin"),
            ("$lb <coin>",          "Prefix leaderboard — `$lb ltc`"),
        ],
    },
    "info": {
        "emoji": "🔗",
        "label": "Info",
        "color": COLOR["info"],
        "cmds": [
            ("/invite",             "Get the bot's invite link (generated from bot ID)"),
            ("$invite",             "Prefix invite link"),
            ("/support",            "Support server link (set SUPPORT_SERVER_URL in env)"),
            ("$support",            "Prefix support link"),
            ("/dashboard",          "Open the web dashboard (set DASHBOARD_URL in env)"),
            ("$dashboard / $dash",  "Prefix dashboard link"),
            ("/profile",            "Your wallet profile — balances, total worth, tip stats"),
            ("$profile / $me",      "Prefix profile — same as /profile"),
        ],
    },
    "utility": {
        "emoji": "🔧",
        "label": "Utility",
        "color": COLOR["info"],
        "cmds": [
            ("/serverinfo",        "View server information"),
            ("$si",                "Prefix server info"),
            ("/userinfo [user]",   "View user profile & wallet info"),
            ("/ping",              "Check bot latency"),
            ("$ping",              "Prefix ping"),
            ("/rules",             "View wallet rules"),
            ("/help",              "Open this help menu"),
            ("$help / $h",         "Prefix help"),
        ],
    },
    "tickets": {
        "emoji": "🎫",
        "label": "Tickets",
        "color": COLOR["primary"],
        "cmds": [
            ("/ticketpanel", "Deploy a support / task ticket panel"),
        ],
    },
}

STAFF_CATEGORY = {
    "emoji": "🛡️",
    "label": "Owner / Dev",
    "color": COLOR["warning"],
    "cmds": [
        # Owner commands
        ("/setbal @user coin amount",     "[Owner/Dev] Set a user's coin balance"),
        ("/addbal @user coin amount",     "[Owner/Dev] Add or deduct balance"),
        ("/setprefix <prefix>",           "[Owner/Dev] Change bot prefix for this server"),
        ("/broadcast <msg>",              "[Owner/Dev] Broadcast DM to all users"),
        ("/announce <msg>",               "[Owner/Dev] Server announcement"),
        ("/addauthorised @user",          "[Owner/Dev] Grant authorised user status"),
        ("/removeauthorised @user",       "[Owner/Dev] Revoke authorised status"),
        ("/listauthorised",               "[Owner/Dev] List all authorised users"),
        ("/servers",                      "[Owner/Dev] List all servers the bot is in"),
        ("/setdetection <coin> <on|off>", "[Owner/Dev] Toggle coin deposit detection"),
        ("/setwithdraw <coin> <on|off>",  "[Owner/Dev] Toggle coin withdrawals"),
        # Prefix staff
        ("$setbal @user coin amount",     "Prefix: set balance"),
        ("$addbal @user coin amount",     "Prefix: add balance"),
        ("$payouts",                       "[Staff] Deposit/withdraw config + mnemonic status + addresses (DM only)"),
    ],
}


# ── Embeds ───────────────────────────────────────────────────────────────────

def home_embed(show_staff: bool = False) -> discord.Embed:
    total = sum(len(c["cmds"]) for c in PUBLIC_CATEGORIES.values())
    if show_staff:
        total += len(STAFF_CATEGORY["cmds"])

    lines = []
    for cat in PUBLIC_CATEGORIES.values():
        lines.append(f"{cat['emoji']} **{cat['label']}** • `{len(cat['cmds'])}` commands")

    if show_staff:
        lines.append(
            f"{STAFF_CATEGORY['emoji']} **{STAFF_CATEGORY['label']}** • `{len(STAFF_CATEGORY['cmds'])}` commands"
            f"  *(staff only)*"
        )

    desc = (
        f"{DIV}\n"
        f"{E['xwallet']} **XWALLET CRYPTO WALLET**\n"
        f"{DIV}\n"
        f"{E['payment']} Multi-Coin: BTC • LTC • ETH • SOL • USDT\n"
        f"{E['server']} Prefix: `$`\n"
        f"{DIV}\n"
        + "\n".join(lines)
        + f"\n{DIV}\n"
        f"{E['notify']} Select a category below."
    )

    em = discord.Embed(title=f"{E['xwallet']} Help Menu", description=desc, color=COLOR["primary"])
    em.set_footer(text=f"XWALLET • {total} commands total")
    return em


def category_embed(key: str) -> discord.Embed:
    if key == "__staff__":
        cat = STAFF_CATEGORY
    else:
        cat = PUBLIC_CATEGORIES[key]

    lines = []
    for cmd, desc in cat["cmds"]:
        lines.append(f"{E['arrow1']} `{cmd}`\n{desc}")

    em = discord.Embed(
        title=f"{cat['emoji']} {cat['label']}",
        description=f"{DIV}\n" + "\n\n".join(lines) + f"\n{DIV}",
        color=cat["color"],
    )
    em.set_footer(text=f"{len(cat['cmds'])} commands")
    return em


# ── Views ────────────────────────────────────────────────────────────────────

class HelpSelect(discord.ui.Select):
    def __init__(self, show_staff: bool = False):
        options = [
            discord.SelectOption(label="Home", value="home", emoji="🏠", description="XWALLET overview")
        ]
        for key, cat in PUBLIC_CATEGORIES.items():
            options.append(discord.SelectOption(
                label=cat["label"], value=key, emoji=cat["emoji"],
                description=f"{len(cat['cmds'])} commands"
            ))
        if show_staff:
            options.append(discord.SelectOption(
                label=STAFF_CATEGORY["label"], value="__staff__",
                emoji=STAFF_CATEGORY["emoji"],
                description=f"{len(STAFF_CATEGORY['cmds'])} commands (staff only)"
            ))

        super().__init__(placeholder="Select a category…", min_values=1, max_values=1, options=options)
        self._show_staff = show_staff

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "home":
            await interaction.response.edit_message(embed=home_embed(self._show_staff))
        else:
            await interaction.response.edit_message(embed=category_embed(self.values[0]))


class HelpView(discord.ui.View):
    def __init__(self, show_staff: bool = False):
        super().__init__(timeout=300)
        self.add_item(HelpSelect(show_staff))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ──────────────────────────────────────────────────────────────────────

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_home_guild(self, guild_id) -> bool:
        return HOME_GUILD_ID != 0 and guild_id == HOME_GUILD_ID

    def _show_staff(self, user_id: int, guild_id: int) -> bool:
        return user_id in STAFF_IDS and self._is_home_guild(guild_id)

    @app_commands.command(name="help", description="View all bot commands")
    async def help_slash(self, interaction: discord.Interaction):
        show = self._show_staff(interaction.user.id, interaction.guild_id or 0)
        await interaction.response.send_message(
            embed=home_embed(show),
            view=HelpView(show),
            ephemeral=True
        )

    @commands.command(name="help", aliases=["h", "cmds", "commands"])
    async def help_prefix(self, ctx):
        guild_id = ctx.guild.id if ctx.guild else 0
        show = self._show_staff(ctx.author.id, guild_id)
        await ctx.send(embed=home_embed(show), view=HelpView(show))


async def setup(bot):
    await bot.add_cog(Help(bot))
