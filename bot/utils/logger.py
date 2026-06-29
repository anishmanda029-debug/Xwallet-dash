"""
Logger Utility — File logging + Discord channel logging
"""

import discord
import logging
import os
from datetime import datetime
from bot.utils.embeds import E, DIV, COLOR

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(
            f"logs/bot_{datetime.utcnow().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("XWALLET")

ACTION_COLORS = {
    "DAILY": COLOR["success"], "WORK": COLOR["success"],
    "TRANSFER": COLOR["info"], "ADMIN_PAY": COLOR["gold"],
    "ADD_BAL": COLOR["gold"], "SET_BAL": COLOR["gold"],
    "RAIN_START": COLOR["primary"], "RAIN_END": COLOR["primary"],
    "GIVEAWAY_START": COLOR["gold"],
    "TICKET_OPEN": COLOR["primary"], "TICKET_CLOSE": COLOR["warning"],
    "TASK_OPEN": COLOR["info"], "TASK_COMPLETE": COLOR["success"],
    "WITHDRAW_REQ": COLOR["warning"], "DEPOSIT_REQ": COLOR["info"],
    "BAN": COLOR["error"], "KICK": COLOR["error"],
    "MUTE": COLOR["warning"], "WARN": COLOR["warning"],
    "ANTINUKE_BAN": COLOR["error"], "AUTOMOD": COLOR["warning"],
    "HOLD_RELEASE": COLOR["success"], "ADD_HOLD": COLOR["warning"],
    "MESSAGE": COLOR["info"], "BACKUP": COLOR["info"],
}

ACTION_ICONS = {
    "DAILY": E["gift"], "WORK": E["action"],
    "TRANSFER": E["arrow"], "ADMIN_PAY": E["admin"],
    "ADD_BAL": E["dollars"], "SET_BAL": E["edit"],
    "RAIN_START": "☔", "GIVEAWAY_START": E["giveaway"],
    "TICKET_OPEN": E["ticket"], "TICKET_CLOSE": E["mute"],
    "TASK_OPEN": E["action"], "TASK_COMPLETE": E["tick"],
    "WITHDRAW_REQ": E["card"], "DEPOSIT_REQ": E["diamond"],
    "BAN": E["declined"], "KICK": E["declined"],
    "MUTE": E["mute"], "WARN": E["mute"],
    "ANTINUKE_BAN": E["secure"], "AUTOMOD": E["settings"],
    "HOLD_RELEASE": E["security"],
}


async def send_to_log_channel(
    bot: discord.Client,
    guild_id: str,
    action: str,
    user_id: str,
    detail: str,
):
    """Send a structured log embed to the guild's log channel."""
    try:
        from bot.utils.database import get_guild
        g = await get_guild(guild_id)
        if not g or not g["log_channel"]:
            return
        ch = bot.get_channel(int(g["log_channel"]))
        if not ch:
            return

        color = ACTION_COLORS.get(action, COLOR["primary"])
        icon  = ACTION_ICONS.get(action, E["announcement"])

        em = discord.Embed(
            title=f"{icon} {action.replace('_',' ').title()}",
            description=(
                f"{DIV}\n"
                f"{E['members']} **User** · <@{user_id}>\n"
                f"{E['action']} **Action** · `{action}`\n"
                f"{E['tag']} **Detail** · {detail}\n"
                f"{DIV}"
            ),
            color=color,
            timestamp=datetime.utcnow(),
        )
        em.set_footer(text=f"Guild: {guild_id}")
        await ch.send(embed=em)
    except Exception as exc:
        log.warning(f"[Logger] Log channel send failed: {exc}")
