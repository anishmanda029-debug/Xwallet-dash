"""
Checks Utility — Permission helpers for XWALLET.

Owner commands: work on ANY server, but only for OWNER_IDs.
Dev commands:   work on ANY server, but only for STAFF_IDS.
Admin commands: work on any server for server admins or STAFF_IDS.
"""

import os
import discord
from discord.ext import commands
from discord import app_commands
from bot.utils.database import get_guild, get_subscription, is_authorised

OWNER_ID_1 = int(os.getenv("OWNER_ID_1", os.getenv("OWNER_ID", "0")))
OWNER_ID_2 = int(os.getenv("OWNER_ID_2", "0"))
DEV_ID_1   = int(os.getenv("DEV_ID_1", "0"))
DEV_ID_2   = int(os.getenv("DEV_ID_2", "0"))

HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID", os.getenv("DEV_GUILD_ID", "0")))

OWNER_IDS = {OWNER_ID_1, OWNER_ID_2} - {0}
DEV_IDS   = {DEV_ID_1, DEV_ID_2} - {0}
STAFF_IDS = OWNER_IDS | DEV_IDS

# Legacy aliases
OWNER_ID     = OWNER_ID_1
DEV_GUILD_ID = HOME_GUILD_ID


# ── Prefix checks ─────────────────────────────────────────────────────────────

def is_owner_check():
    """Owner only — any server."""
    async def pred(ctx):
        if ctx.author.id in OWNER_IDS:
            return True
        raise commands.CheckFailure("Owner only.")
    return commands.check(pred)


def dev_prefix_only():
    """Staff only (owner + devs) — any server."""
    async def pred(ctx):
        if ctx.author.id in STAFF_IDS:
            return True
        raise commands.CheckFailure("Staff only.")
    return commands.check(pred)


def staff_prefix():
    """Staff or server admin — any server."""
    async def pred(ctx):
        if ctx.author.id in STAFF_IDS:
            return True
        if ctx.guild and ctx.author.guild_permissions.administrator:
            return True
        raise commands.CheckFailure("You need Administrator permission or Staff role.")
    return commands.check(pred)


# ── Slash checks ──────────────────────────────────────────────────────────────

def owner_only():
    """Slash: owner IDs only — any server."""
    async def pred(interaction: discord.Interaction):
        if interaction.user.id not in OWNER_IDS:
            raise app_commands.CheckFailure("Owner only.")
        return True
    return app_commands.check(pred)


def dev_only():
    """Slash: staff only — any server."""
    async def pred(interaction: discord.Interaction):
        if interaction.user.id not in STAFF_IDS:
            raise app_commands.CheckFailure("Staff only.")
        return True
    return app_commands.check(pred)


# ── Authorised check ──────────────────────────────────────────────────────────

async def is_authorised_or_owner(user_id: int) -> bool:
    if user_id in STAFF_IDS:
        return True
    return await is_authorised(str(user_id))


def authorised_only():
    async def pred(interaction: discord.Interaction):
        if await is_authorised_or_owner(interaction.user.id):
            return True
        raise app_commands.CheckFailure("Only the Owner or an authorised member can use this.")
    return app_commands.check(pred)


# ── Server staff ──────────────────────────────────────────────────────────────

def is_staff():
    async def pred(ctx):
        if ctx.author.id in STAFF_IDS:
            return True
        if ctx.guild and ctx.author.guild_permissions.administrator:
            return True
        if ctx.guild:
            g = await get_guild(str(ctx.guild.id))
            if g and g.get("staff_role"):
                role = ctx.guild.get_role(int(g["staff_role"]))
                if role and role in ctx.author.roles:
                    return True
        return False
    return commands.check(pred)


def slash_is_staff():
    async def pred(interaction: discord.Interaction):
        if interaction.user.id in STAFF_IDS:
            return True
        if interaction.guild and interaction.user.guild_permissions.administrator:
            return True
        g = await get_guild(str(interaction.guild_id))
        if g and g.get("staff_role"):
            role = interaction.guild.get_role(int(g["staff_role"]))
            if role and role in interaction.user.roles:
                return True
        raise app_commands.CheckFailure("Staff only.")
    return app_commands.check(pred)


# ── Subscription ──────────────────────────────────────────────────────────────

def has_subscription():
    async def pred(ctx):
        return await get_subscription(str(ctx.author.id), str(ctx.guild.id))
    return commands.check(pred)


# ── Helpers ───────────────────────────────────────────────────────────────────

def user_is_owner(uid: int) -> bool:
    return uid in OWNER_IDS

def is_dev(uid: int) -> bool:
    return uid in STAFF_IDS

def member_is_above(mod: discord.Member, target: discord.Member) -> bool:
    return mod.top_role > target.top_role

async def get_or_fetch_member(guild: discord.Guild, user_id: int):
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return None
    return member

async def safe_send(channel, **kwargs):
    try:
        return await channel.send(**kwargs)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        return None

async def safe_delete(message: discord.Message) -> bool:
    try:
        await message.delete()
        return True
    except Exception:
        return False

async def safe_dm(user, **kwargs) -> bool:
    try:
        await user.send(**kwargs)
        return True
    except Exception:
        return False
