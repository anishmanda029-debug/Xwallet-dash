"""
Tickets Cog — Dropdown panel, Support/Payment/Earning, transcripts, logs
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import os
from datetime import datetime
from bot.utils.database import (
    create_ticket, get_ticket, close_ticket, get_guild, add_log, ensure_user
)
from bot.utils.embeds import E, DIV, COLOR, embed_error, embed_processing, embed_success

TICKET_TYPES = {
    "support": {"label": "Support",  "color": COLOR["primary"], "emoji": "🎫"},
    "payment": {"label": "Payment",  "color": COLOR["gold"],    "emoji": "💳"},
    "earning": {"label": "Earning",  "color": COLOR["success"], "emoji": "💰"},
}

async def create_ticket_channel(guild, user, ticket_type, guild_data):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user:               discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True),
    }
    if guild_data and guild_data["staff_role"]:
        staff = guild.get_role(int(guild_data["staff_role"]))
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    count = len([c for c in guild.text_channels if c.name.startswith(ticket_type[:4])]) + 1
    name  = f"{ticket_type[:4]}-{user.name[:10].lower()}-{count:04d}"
    ch    = await guild.create_text_channel(
        name=name, overwrites=overwrites,
        topic=f"{ticket_type.title()} ticket | {user} | ID:{user.id}"
    )
    return ch


class TicketControlView(discord.ui.View):
    def __init__(self, ticket_channel_id: str, user_id: int):
        super().__init__(timeout=None)
        self.ticket_channel_id = ticket_channel_id
        self.user_id           = user_id

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="tkt_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        ticket  = await get_ticket(str(channel.id))
        if not ticket:
            return await interaction.response.send_message(embed=embed_error("Not a Ticket", ""), ephemeral=True)
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=embed_error("No Permission", ""), ephemeral=True)

        await interaction.response.send_message(embed=embed_processing("Closing ticket and saving transcript…"))
        await asyncio.sleep(1.5)

        # Build transcript
        lines = []
        async for msg in channel.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
            content = msg.content or "[embed/attachment]"
            lines.append(f"[{ts}] {msg.author.display_name}: {content}")
        transcript = "\n".join(lines)
        await close_ticket(str(channel.id), transcript)

        # Log channel
        guild_data = await get_guild(str(interaction.guild_id))
        if guild_data and guild_data["ticket_log"]:
            log_ch = interaction.guild.get_channel(int(guild_data["ticket_log"]))
            if log_ch:
                ticket_user = interaction.guild.get_member(int(ticket["user_id"]))
                user_mention = ticket_user.mention if ticket_user else f"<@{ticket['user_id']}>"
                log_em = discord.Embed(
                    title=f"{E['ticket']} Ticket Closed",
                    description=(
                        f"{DIV}\n"
                        f"{E['members']} **User** · {user_mention}\n"
                        f"{E['tag']} **Type** · `{ticket['type'].title()}`\n"
                        f"{E['id']} **Channel** · `{channel.name}`\n"
                        f"{E['mod']} **Closed By** · {interaction.user.mention}\n"
                        f"{DIV}"
                    ),
                    color=COLOR["warning"],
                    timestamp=datetime.utcnow(),
                )
                if transcript:
                    f = discord.File(io.BytesIO(transcript.encode()), filename=f"transcript-{channel.name}.txt")
                    await log_ch.send(embed=log_em, file=f)
                else:
                    await log_ch.send(embed=log_em)

        await add_log(str(interaction.guild_id), str(interaction.user.id), "TICKET_CLOSE", f"#{channel.name}")
        await asyncio.sleep(2)
        try:
            await channel.delete(reason="Ticket closed")
        except Exception:
            pass

    @discord.ui.button(label="➕ Add User", style=discord.ButtonStyle.secondary, custom_id="tkt_add")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=embed_error("No Permission", ""), ephemeral=True)
        await interaction.response.send_modal(AddUserModal(interaction.channel))

    @discord.ui.button(label="➖ Remove User", style=discord.ButtonStyle.secondary, custom_id="tkt_remove")
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=embed_error("No Permission", ""), ephemeral=True)
        await interaction.response.send_modal(RemoveUserModal(interaction.channel))


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    user_id = discord.ui.TextInput(label="User ID", placeholder="Enter Discord User ID")
    def __init__(self, channel): super().__init__(); self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(int(self.user_id.value)) or \
                     await interaction.guild.fetch_member(int(self.user_id.value))
            await self.channel.set_permissions(member, read_messages=True, send_messages=True)
            await interaction.response.send_message(embed=embed_success("User Added", f"{member.mention} can now see this ticket."))
        except Exception:
            await interaction.response.send_message(embed=embed_error("Not Found", "User not found."), ephemeral=True)


class RemoveUserModal(discord.ui.Modal, title="Remove User from Ticket"):
    user_id = discord.ui.TextInput(label="User ID", placeholder="Enter Discord User ID")
    def __init__(self, channel): super().__init__(); self.channel = channel
    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(int(self.user_id.value))
            if member:
                await self.channel.set_permissions(member, overwrite=None)
                await interaction.response.send_message(embed=embed_success("User Removed", f"{member.mention} removed."))
        except Exception:
            await interaction.response.send_message(embed=embed_error("Error", ""), ephemeral=True)


class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Support", description="General help & questions", emoji="🎫", value="support"),
            discord.SelectOption(label="Payment", description="Payment & billing issues", emoji="💳", value="payment"),
            discord.SelectOption(label="Earning", description="Task & earning support",  emoji="💰", value="earning"),
        ]
        super().__init__(placeholder="📂 Select a ticket category…", min_values=1, max_values=1,
                         options=options, custom_id="ticket_dropdown")

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)

        # Check for existing open ticket
        for channel in interaction.guild.text_channels:
            if channel.topic and str(interaction.user.id) in channel.topic:
                existing = await get_ticket(str(channel.id))
                if existing and existing["status"] == "open":
                    return await interaction.response.send_message(
                        embed=embed_error("Already Open", f"You have an open ticket: {channel.mention}\nClose it before opening a new one."),
                        ephemeral=True
                    )

        await interaction.response.send_message(embed=embed_processing("Creating your ticket…"), ephemeral=True)
        await asyncio.sleep(0.8)

        guild_data = await get_guild(str(interaction.guild_id))
        channel    = await create_ticket_channel(interaction.guild, interaction.user, ticket_type, guild_data)
        ticket_id  = await create_ticket(str(channel.id), str(interaction.guild_id), uid, ticket_type)

        info = TICKET_TYPES[ticket_type]
        desc = (
            f"{DIV}\n"
            f"{info['emoji']} **Type** · `{ticket_type.title()}`\n"
            f"{E['members']} **User** · {interaction.user.mention}\n"
            f"{E['id']} **Ticket** · `#{ticket_id:04d}`\n"
            f"{DIV}\n"
            f"{E['announcement']} Hello {interaction.user.mention}!\n"
            f"Describe your issue and a staff member will assist you shortly.\n"
            f"{DIV}"
        )
        em = discord.Embed(title=f"{info['emoji']} {ticket_type.title()} Ticket", description=desc, color=info["color"])
        em.set_footer(text="Use the buttons below to manage this ticket")

        ping = f"<@&{guild_data['staff_role']}>" if guild_data and guild_data["staff_role"] else None
        view = TicketControlView(str(channel.id), interaction.user.id)
        await channel.send(content=ping, embed=em, view=view)

        if ticket_type == "earning":
            task_msg = (guild_data["task_message"] if guild_data and guild_data["task_message"]
                        else "First Name:\nEmail:\nPassword:")
            task_em = discord.Embed(
                title=f"{E['form']} Task Form",
                description=(
                    f"{DIV}\n"
                    f"Please fill in the following details:\n\n"
                    f"```\n{task_msg}\n```\n"
                    f"{DIV}\n"
                    f"{E['action']} Use **I Registered** once each step is done."
                ),
                color=COLOR["primary"],
            )
            from bot.cogs.tasks import TaskView
            await channel.send(embed=task_em, view=TaskView(str(channel.id)))

        await interaction.edit_original_response(
            embed=embed_success("Ticket Created!", f"Your ticket: {channel.mention}")
        )
        await add_log(str(interaction.guild_id), uid, "TICKET_OPEN", f"#{ticket_type}")


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(TicketPanelView())

    @app_commands.command(name="ticketpanel", description="Send the support ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        desc = (
            f"{DIV}\n"
            f"🎫 **Support** — General help & questions\n"
            f"💳 **Payment** — Billing & payment issues\n"
            f"💰 **Earning** — Tasks & earning support\n"
            f"{DIV}\n"
            f"Select a category from the dropdown below."
        )
        em = discord.Embed(title=f"{E['ticket']} Support Center", description=desc, color=COLOR["primary"])
        em.set_footer(text="XWALLET • Support System")
        await interaction.channel.send(embed=em, view=TicketPanelView())
        await interaction.followup.send(embed=embed_success("Panel Sent!"), ephemeral=True)

    @commands.command(name="ticketpanel")
    @commands.has_permissions(administrator=True)
    async def ticketpanel_prefix(self, ctx):
        desc = (f"{DIV}\n🎫 Support · 💳 Payment · 💰 Earning\n{DIV}\nPick a category below.")
        em = discord.Embed(title=f"{E['ticket']} Support Center", description=desc, color=COLOR["primary"])
        await ctx.send(embed=em, view=TicketPanelView())
        try: await ctx.message.delete()
        except Exception: pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
