"""
XWALLET — Enhanced Main Entry Point
Full error handling, event logging, presence rotation, invite cache
"""

import discord
from discord.ext import commands, tasks
import asyncio, os, logging, traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("XWALLET")

COGS = [
    "bot.cogs.economy", "bot.cogs.rain",
    "bot.cogs.withdraw",
    "bot.cogs.deposit", "bot.cogs.admin", "bot.cogs.rules",
    "bot.cogs.info",
    "bot.cogs.help",
    "bot.cogs.debug",
    "bot.cogs.tos",
    "bot.cogs.tickets",
]

PRESENCES = [
    (discord.ActivityType.watching,  "/help | XWALLET"),
    (discord.ActivityType.listening, "your tips"),
    (discord.ActivityType.playing,   "Economy • Crypto "),
    (discord.ActivityType.watching,  "Admin watching 👀 "),
    (discord.ActivityType.playing,   "XWALLET v1.0"),
]


async def get_guild_prefix(bot, message):
    default = os.getenv("BOT_PREFIX", "$")
    if not message.guild:
        return commands.when_mentioned_or(default)(bot, message)
    try:
        from bot.utils.database import get_prefix
        prefix = await get_prefix(str(message.guild.id))
        prefix = prefix or default
    except Exception:
        prefix = default
    return commands.when_mentioned_or(prefix)(bot, message)


class XWalletBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=get_guild_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
            max_messages=1000,
        )
        self.owner_id_int  = int(os.getenv("OWNER_ID", "0"))
        self.invite_cache  = {}
        self._presence_idx = 0
        self.start_time    = datetime.utcnow()

    async def setup_hook(self):
        from bot.utils.database import init_db
        await init_db()
        log.info("✅ Database ready")
        failed = []
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"   ✅ {cog.split('.')[-1]}")
            except Exception as e:
                log.error(f"   ❌ {cog}: {e}")
                traceback.print_exc()
                failed.append(cog)
        if failed:
            log.warning(f"⚠️ {len(failed)} cog(s) failed: {', '.join(c.split('.')[-1] for c in failed)}")
        try:
            synced = await self.tree.sync()
            log.info(f"🌐 Synced {len(synced)} slash commands")
        except Exception as e:
            log.error(f"❌ Sync failed: {e}")
        self.rotate_presence.start()

    async def on_ready(self):
        log.info("=" * 52)
        log.info(f"  ⚡ XWALLET Online!")
        log.info(f"  🤖 {self.user} (ID: {self.user.id})")
        log.info(f"  🏠 Guilds : {len(self.guilds)}")
        log.info(f"  👥 Users  : {sum(g.member_count for g in self.guilds)}")
        log.info(f"  📋 Cmds   : {len(self.commands)} prefix | {len(self.tree.get_commands())} slash")
        log.info("=" * 52)
        # Show hot wallet addresses on startup
        try:
            from bot.wallets.mnemonic import get_all_addresses
            addrs = get_all_addresses()
            src = "🔑 Mnemonic (Trust Wallet)" if addrs['source'] == 'mnemonic' else "📄 Manual (.env)"
            log.info(f"  💳 Wallet Source : {src}")
            log.info(f"  🟠  BTC : {addrs['btc'] or '❌ Not set'}")
            log.info(f"  🪙  LTC : {addrs['ltc'] or '❌ Not set'}")
            log.info(f"  🔷  ETH : {addrs['eth'] or '❌ Not set'}")
            log.info(f"  🟣  SOL : {addrs['sol'] or '❌ Not set (install PyNaCl)'}")
        except Exception as e:
            log.warning(f"  ⚠️  Could not display wallet addresses: {e}")
        log.info("=" * 52)
        from bot.utils.database import upsert_bot_guild
        for guild in self.guilds:
            try:
                await upsert_bot_guild(str(guild.id), guild.name, str(guild.icon.url) if guild.icon else "", guild.member_count)
            except Exception as e:
                log.warning(f"Could not register guild {guild.id} for dashboard stats: {e}")

    @tasks.loop(minutes=5)
    async def rotate_presence(self):
        atype, name = PRESENCES[self._presence_idx % len(PRESENCES)]
        await self.change_presence(
            activity=discord.Activity(type=atype, name=name),
            status=discord.Status.online,
        )
        self._presence_idx += 1

    @rotate_presence.before_loop
    async def before_rotate(self):
        await self.wait_until_ready()

    async def on_guild_join(self, guild):
        log.info(f"📥 Joined: {guild.name} ({guild.id})")
        from bot.utils.database import get_guild, upsert_bot_guild
        await get_guild(str(guild.id))
        await upsert_bot_guild(str(guild.id), guild.name, str(guild.icon.url) if guild.icon else "", guild.member_count)
        from bot.utils.embeds import E, S, DIV, COLOR
        em = discord.Embed(
            title=f"{E['premium']} XWALLET is here!",
            description=(
                f"{DIV}\n"
                f"{E['tick']} Thanks for adding me to **{guild.name}**!\n\n"
                f"{E['inr']} `/deposit` {S['bullet']} Deposit LTC\n"
                f"{E['card']} `/withdraw` {S['bullet']} Withdraw LTC\n"
                f"{E['ticket']} `/ticketpanel` {S['bullet']} Deploy support/task panel\n"
                f"{E['tag']} `/setlogchannel` `/setwithdrawlog` {S['bullet']} Set logs\n"
                f"{E['announcement']} `/help` {S['bullet']} Full command reference\n"
                f"{DIV}"
            ),
            color=COLOR["primary"],
        )
        em.set_thumbnail(url=self.user.display_avatar.url)
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                try:
                    await ch.send(embed=em)
                except Exception:
                    pass
                break

    async def on_guild_remove(self, guild):
        log.info(f"📤 Left: {guild.name} ({guild.id})")
        from bot.utils.database import mark_bot_guild_inactive
        await mark_bot_guild_inactive(str(guild.id))

    async def on_member_join(self, member):
        from bot.utils.database import ensure_user
        await ensure_user(str(member.id), member.name)

    async def on_interaction(self, interaction: discord.Interaction):
        """Fires the one-time rules DM on a user's first ever interaction
        with the bot, regardless of which command they used."""
        if interaction.type == discord.InteractionType.application_command and interaction.user:
            rules_cog = self.get_cog("Rules")
            if rules_cog:
                await rules_cog.maybe_onboard(interaction.user)

    async def on_command_error(self, ctx, error):
        from bot.utils.embeds import embed_error, E, DIV, COLOR, S
        if isinstance(error, commands.CommandNotFound):
            # Show hint: what command were they trying?
            attempted = ctx.message.content.split()[0] if ctx.message.content else "?"
            em = discord.Embed(
                title=f"{E['error']} Unknown Command",
                description=(
                    f"{DIV}\n"
                    f"{E['arrow1']} `{attempted}` is not a valid command.\n"
                    f"{E['notify']} Use `$help` or `/help` to see all commands.\n"
                    f"{DIV}"
                ),
                color=COLOR["error"]
            )
            try:
                return await ctx.send(embed=em, delete_after=8)
            except Exception:
                return
        if isinstance(error, commands.MissingPermissions):
            em = embed_error("No Permission", f"Missing: `{'`, `'.join(error.missing_permissions)}`")
        elif isinstance(error, commands.BotMissingPermissions):
            em = embed_error("Bot Missing Permissions", f"I need: `{'`, `'.join(error.missing_permissions)}`")
        elif isinstance(error, commands.MissingRequiredArgument):
            # Provide a detailed usage hint
            cmd_name = ctx.command.name if ctx.command else "?"
            usage = ctx.command.usage or f"`${cmd_name} <{error.param.name}>`"
            em = discord.Embed(
                title=f"{E['error']} Missing Argument",
                description=(
                    f"{DIV}\n"
                    f"{E['arrow1']} Missing: `{error.param.name}`\n"
                    f"{E['notify']} **Full usage:** {usage}\n"
                    f"{E['help']} Use `$help` to see command details.\n"
                    f"{DIV}"
                ),
                color=COLOR["error"]
            )
        elif isinstance(error, commands.BadArgument):
            em = embed_error("Invalid Argument", str(error))
        elif isinstance(error, commands.CommandOnCooldown):
            em = embed_error("Cooldown", f"Try again in `{error.retry_after:.1f}s`")
        elif isinstance(error, commands.CheckFailure):
            em = embed_error("Access Denied", str(error) or "You cannot use this command.")
        elif isinstance(error, commands.NoPrivateMessage):
            em = embed_error("Server Only", "This command only works in a server.")
        else:
            log.error(f"Unhandled error in {ctx.command}: {error}")
            em = embed_error("Unexpected Error", f"`{type(error).__name__}`")
        try:
            await ctx.send(embed=em, delete_after=10)
        except Exception:
            pass

    async def on_app_command_error(self, interaction, error):
        from bot.utils.embeds import embed_error
        from discord import app_commands
        if isinstance(error, app_commands.CommandOnCooldown):
            em = embed_error("Cooldown", f"Try again in `{error.retry_after:.1f}s`")
        elif isinstance(error, app_commands.MissingPermissions):
            em = embed_error("No Permission", f"Missing: `{'`, `'.join(error.missing_permissions)}`")
        elif isinstance(error, app_commands.CheckFailure):
            em = embed_error("Access Denied", str(error) or "You cannot use this command.")
        else:
            log.error(f"Slash error: {error}")
            em = embed_error("Error", f"`{type(error).__name__}`")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=em, ephemeral=True)
            else:
                await interaction.response.send_message(embed=em, ephemeral=True)
        except Exception:
            pass

    async def on_message_delete(self, message):
        if message.author.bot or not message.guild or not message.content:
            return
        try:
            from bot.utils.database import get_guild
            g = await get_guild(str(message.guild.id))
            if g and g["log_channel"]:
                ch = self.get_channel(int(g["log_channel"]))
                if ch:
                    from bot.utils.embeds import E, DIV, COLOR
                    em = discord.Embed(
                        title=f"{E['mute']} Message Deleted",
                        description=(
                            f"{DIV}\n"
                            f"{E['members']} **Author** · {message.author.mention}\n"
                            f"{E['tag']} **Channel** · {message.channel.mention}\n"
                            f"{E['form']} **Content** · {message.content[:500]}\n"
                            f"{DIV}"
                        ),
                        color=COLOR["warning"],
                        timestamp=datetime.utcnow(),
                    )
                    await ch.send(embed=em)
        except Exception:
            pass

    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        try:
            from bot.utils.database import get_guild
            g = await get_guild(str(before.guild.id))
            if g and g["log_channel"]:
                ch = self.get_channel(int(g["log_channel"]))
                if ch:
                    from bot.utils.embeds import E, DIV, COLOR
                    em = discord.Embed(
                        title=f"{E['edit']} Message Edited",
                        description=(
                            f"{DIV}\n"
                            f"{E['members']} **Author** · {before.author.mention}\n"
                            f"{E['tag']} **Channel** · {before.channel.mention}\n"
                            f"{E['form']} **Before** · {before.content[:300]}\n"
                            f"{E['next']} **After** · {after.content[:300]}\n"
                            f"{DIV}"
                        ),
                        color=COLOR["info"],
                        timestamp=datetime.utcnow(),
                    )
                    em.set_footer(text=f"ID: {before.id}")
                    await ch.send(embed=em)
        except Exception:
            pass


async def main():
    bot = XWalletBot()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        log.critical("❌ DISCORD_TOKEN not set in .env!")
        return
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
