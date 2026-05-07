import discord
from discord import app_commands
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.discord_utils import reply_or_send
from utils.permissions import check_target_permissions, has_command_permission, command_category
from config.config_manager import save_config
from utils.embed_helper import create_embed_response
import asyncio

logger = get_logger()

class ServerConfigCog(commands.Cog, name="Server Configuration"):
    """Cog for managing server-specific configurations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_subcommand_help(self, ctx: commands.Context):
        """Sends a detailed help embed for a specific subcommand."""
        command = ctx.command
        # For nested subcommands (like prefix set), get the parent's parent
        if command.parent and command.parent.parent:
            title = f"Help for: `!{command.parent.parent.name} {command.parent.name} {command.name}`"
        else:
            title = f"Help for: `!{command.parent.name} {command.name}`"
        
        help_embed = discord.Embed(
            title=title,
            description=command.help,
            color=discord.Color.orange()
        )
        await ctx.send(embed=help_embed)

    @commands.hybrid_group(name="server", help="""
    Manages server-specific settings for the bot.
    This command group provides tools to configure the command prefix and view the current server configuration.
    Usage: `!server <subcommand> [value]`
    """)
    @has_command_permission()
    @command_category("Bot Configuration")
    async def server(self, ctx: commands.Context):
        """Manages server-specific settings. Use without a subcommand to see help."""
        if ctx.invoked_subcommand is None:
            help_embed = discord.Embed(
                title="Server Configuration Help",
                description=self.server.help,
                color=discord.Color.blue()
            )
            for command in self.server.commands:
                signature = f"`!server {command.name}"
                # Handle nested groups like 'prefix'
                if isinstance(command, commands.Group):
                    for sub_cmd in command.commands:
                        sub_signature = f"`!server {command.name} {sub_cmd.name}"
                        for param in sub_cmd.clean_params.values():
                            sub_signature += f" <{param.name}>"
                        sub_signature += "`"
                        help_embed.add_field(name=f"**{command.name.capitalize()} {sub_cmd.name.capitalize()}**", value=f"{sub_signature}\n{sub_cmd.help}", inline=False)
                else:
                    for param in command.clean_params.values():
                        signature += f" <{param.name}>"
                    signature += "`"
                    help_embed.add_field(name=f"**{command.name.capitalize()}**", value=f"{signature}\n{command.help}", inline=False)
            await ctx.send(embed=help_embed)

    @server.command(name="status", help="""
    Displays all bot configuration settings for this server.
    Shows the current command prefix, OCR settings, and permission configurations.
    Usage: `!server status`
    """)
    @has_command_permission()
    @commands.bot_has_permissions(embed_links=True)
    async def status(self, ctx: commands.Context):
        """Display all server configuration settings"""
        if not ctx.guild:
            await reply_or_send(ctx, "This command can only be used in a server.")
            return

        config = self.bot.config
        guild_id = str(ctx.guild.id)
        
        from core.bot import get_server_prefix
        current_prefix = get_server_prefix(self.bot, ctx.message)
        
        thumbnail_url = ctx.guild.icon.url if ctx.guild.icon else None
        
        description = f"Server configuration for **{ctx.guild.name}**\n\n**Current prefix:** `{current_prefix}`"
        
        ocr_read_channels = config.get('ocr_read_channels', {}).get(guild_id, [])
        ocr_response_channels = config.get('ocr_response_channels', {}).get(guild_id, [])
        ocr_response_fallback = config.get('ocr_response_fallback', {}).get(guild_id, [])
        command_permissions = config.get('command_permissions', {}).get(guild_id, {})

        async def get_ocr_read_channels_field():
            if not ocr_read_channels:
                return {"name": "📷 OCR Read Channels", "value": "No OCR read channels configured.", "inline": False}
            lines = []
            for channel_id in ocr_read_channels:
                channel = self.bot.get_channel(channel_id)
                lang = config.get('ocr_channel_config', {}).get(guild_id, {}).get(str(channel_id), {}).get('lang', 'eng')
                lang_display = " (Russian)" if lang == "rus" else ""
                lines.append(f"• {channel.mention if channel else f'Unknown Channel ({channel_id})'}{lang_display}")
            return {"name": "📷 OCR Read Channels", "value": "\n".join(lines), "inline": False}

        async def get_ocr_response_channels_field():
            if not ocr_response_channels:
                return {"name": "💬 OCR Response Channels", "value": "No OCR response channels configured.", "inline": False}
            lines = []
            for channel_id in ocr_response_channels:
                channel = self.bot.get_channel(channel_id)
                lines.append(f"• {channel.mention if channel else f'Unknown Channel ({channel_id})'}")
            return {"name": "💬 OCR Response Channels", "value": "\n".join(lines), "inline": False}

        async def get_ocr_fallback_channels_field():
            if not ocr_response_fallback:
                return {"name": "🔄 OCR Fallback Channels", "value": "No OCR fallback channels configured.", "inline": False}
            lines = []
            for channel_id in ocr_response_fallback:
                channel = self.bot.get_channel(channel_id)
                lines.append(f"• {channel.mention if channel else f'Unknown Channel ({channel_id})'}")
            return {"name": "🔄 OCR Fallback Channels", "value": "\n".join(lines), "inline": False}

        async def get_manager_roles_field():
            manager_roles = command_permissions.get("*", [])
            if not manager_roles:
                return {"name": "👑 Bot Manager Roles", "value": "No bot manager roles configured.", "inline": False}
            lines = [f"• {ctx.guild.get_role(int(r_id)).mention if ctx.guild.get_role(int(r_id)) else f'Unknown Role ({r_id})'}" for r_id in manager_roles]
            return {"name": "👑 Bot Manager Roles", "value": "\n".join(lines), "inline": False}

        async def get_manager_users_field():
            manager_users = command_permissions.get("users", {}).get("*", [])
            if not manager_users:
                return {"name": "👤 Bot Manager Users", "value": "No bot manager users configured.", "inline": False}
            
            users = await asyncio.gather(*[self.bot.fetch_user(int(u_id)) for u_id in manager_users], return_exceptions=True)
            lines = [f"• @{user.name}" if isinstance(user, discord.User) else f"• Unknown User ({uid})" for user, uid in zip(users, manager_users)]
            return {"name": "👤 Bot Manager Users", "value": "\n".join(lines), "inline": False}

        tasks = [
            get_ocr_read_channels_field(),
            get_ocr_response_channels_field(),
            get_ocr_fallback_channels_field(),
            get_manager_roles_field(),
            get_manager_users_field(),
        ]
        
        fields = await asyncio.gather(*tasks)
        
        footer_text = f"{ctx.guild.name} | Server ID: {ctx.guild.id}"
        
        await create_embed_response(
            ctx=ctx,
            title="Server Configuration Status",
            description=description,
            fields=list(fields),
            footer_text=footer_text,
            thumbnail_url=thumbnail_url
        )

    @server.group(name="prefix", help="Manages the command prefix for this server.")
    @has_command_permission()
    async def prefix(self, ctx: commands.Context):
        """Manages the command prefix."""
        if ctx.invoked_subcommand is None:
            await self._send_subcommand_help(ctx)

    @prefix.command(name="set", help="""
    Changes the command prefix for this server.
    The prefix is the character(s) you put before a command name.
    Usage: `!server prefix set <new_prefix>`
    Example: `!server prefix set $`
    """)
    @has_command_permission()
    @app_commands.describe(new_prefix="The new prefix to use (e.g., $, !, >). Max 5 characters.")
    async def set_prefix(self, ctx: commands.Context, new_prefix: str):
        """Change the command prefix for this server."""
        if not ctx.guild:
            await create_embed_response(ctx, title="❌ Error", description="This command can only be used in a server.", color=discord.Color.red())
            return
        
        if len(new_prefix) > 5:
            await create_embed_response(ctx, title="❌ Error", description="Prefix must be 5 characters or less.", color=discord.Color.red())
            return
        
        config = self.bot.config
        server_prefixes = config.get('server_prefixes', {})
        guild_id = str(ctx.guild.id)
        
        from core.bot import get_server_prefix
        old_prefix = get_server_prefix(self.bot, ctx.message)
        
        server_prefixes[guild_id] = new_prefix
        config['server_prefixes'] = server_prefixes
        save_config(config)
        
        await create_embed_response(ctx, title="✅ Prefix Updated", description=f"Command prefix for this server has been changed from `{old_prefix}` to `{new_prefix}`.", color=discord.Color.green())

    @prefix.command(name="reset", help="""
    Resets the command prefix for this server to the bot's default (!).
    Usage: `!server prefix reset`
    """)
    @has_command_permission()
    async def reset_prefix(self, ctx: commands.Context):
        """Reset the command prefix for this server to the default."""
        if not ctx.guild:
            await create_embed_response(ctx, title="❌ Error", description="This command can only be used in a server.", color=discord.Color.red())
            return
            
        config = self.bot.config
        server_prefixes = config.get('server_prefixes', {})
        guild_id = str(ctx.guild.id)
        
        if guild_id in server_prefixes:
            old_prefix = server_prefixes.pop(guild_id)
            config['server_prefixes'] = server_prefixes
            save_config(config)
            await create_embed_response(ctx, title="✅ Prefix Reset", description=f"Command prefix for this server has been reset from `{old_prefix}` to the default `!`.", color=discord.Color.green())
        else:
            await create_embed_response(ctx, title="ℹ️ Info", description="Command prefix for this server is already set to the default `!`.", color=discord.Color.blue())

async def setup(bot: commands.Bot):
    """Set up the ServerConfigCog."""
    await bot.add_cog(ServerConfigCog(bot))
