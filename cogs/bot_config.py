import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from config.config_manager import save_config
from utils.embed_helper import create_embed_response
import asyncio

logger = get_logger()

class BotConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='set_prefix', help='Change the command prefix for this server.\nArguments: prefix (str) - The new prefix to use\nExample: !set_prefix $ or !set_prefix >')
    @has_command_permission()
    @command_category("Bot Configuration")
    async def set_prefix(self, ctx, prefix: str):
        config = self.bot.config
        server_prefixes = config.get('server_prefixes', {})
        
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.")
            return
        
        # Limit prefix length to prevent abuse
        if len(prefix) > 5:
            await ctx.reply("Prefix must be 5 characters or less.")
            return
        
        guild_id = str(ctx.guild.id)
        from core.bot import get_server_prefix
        old_prefix = server_prefixes.get(guild_id, get_server_prefix(self.bot, ctx.message))
        server_prefixes[guild_id] = prefix
        
        # Save the updated configuration
        config['server_prefixes'] = server_prefixes
        save_config(config)
        
        response = f"Command prefix for this server has been changed from `{old_prefix}` to `{prefix}`"
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='reset_prefix', help='Reset the command prefix for this server to the default (!).\nNo additional arguments required.\nExample: {prefix}reset_prefix')
    @has_command_permission()
    @command_category("Bot Configuration")
    async def reset_prefix(self, ctx):
        config = self.bot.config
        server_prefixes = config.get('server_prefixes', {})
        
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.")
            return
        
        guild_id = str(ctx.guild.id)
        
        if guild_id in server_prefixes:
            old_prefix = server_prefixes[guild_id]
            del server_prefixes[guild_id]
            
            # Save the updated configuration
            config['server_prefixes'] = server_prefixes
            save_config(config)
            
            response = f"Command prefix for this server has been reset from `{old_prefix}` to the default `!`"
        else:
            response = f"Command prefix for this server is already set to the default `!`"
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='server_info', help='Display all bot configuration settings for this server.\nNo additional arguments required.\nExample: !server_info')
    @has_command_permission()
    @command_category("Bot Configuration")
    async def server_info(self, ctx):
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.")
            return
        
        config = self.bot.config
        guild_id = str(ctx.guild.id)
        
        # Get current prefix
        from core.bot import get_server_prefix
        current_prefix = config.get('server_prefixes', {}).get(guild_id, config.get('command_prefix', '!'))
        
        # Get server icon URL for the thumbnail
        thumbnail_url = None
        if ctx.guild and ctx.guild.icon:
            thumbnail_url = ctx.guild.icon.url
        elif ctx.guild and ctx.guild.me.avatar:  # Fallback to bot's server avatar if no server icon
            thumbnail_url = ctx.guild.me.avatar.url
        elif self.bot.user.avatar:  # Fallback to bot's global avatar if no server icon
            thumbnail_url = self.bot.user.avatar.url
        
        # Create description with server prefix info
        description = f"Server configuration for **{ctx.guild.name}**\n\n**Current prefix:** `{current_prefix}`"
        
        # Get configurations needed for async fetching
        ocr_read_channels = config.get('ocr_read_channels', {})
        ocr_response_channels = config.get('ocr_response_channels', {})
        ocr_response_fallback = config.get('ocr_response_fallback', {})
        command_permissions = config.get('command_permissions', {})
        
        # Define async fetch functions
        async def get_ocr_read_channels():
            result = ""
            if guild_id in ocr_read_channels and ocr_read_channels[guild_id]:
                channels = []
                for channel_id in ocr_read_channels[guild_id]:
                    channel = self.bot.get_channel(channel_id)
                    channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                    # Get language for this channel
                    lang = "eng"
                    if 'ocr_channel_config' in config and guild_id in config['ocr_channel_config'] and str(channel_id) in config['ocr_channel_config'][guild_id]:
                        lang = config['ocr_channel_config'][guild_id][str(channel_id)].get('lang', 'eng')
                    lang_display = " (Russian)" if lang == "rus" else ""
                    channels.append(f"• {channel_name}{lang_display}")
                result = "\n".join(channels)
            else:
                result = "No OCR read channels configured."
            return {"name": "📷 OCR Read Channels", "value": result, "inline": False}
            
        async def get_ocr_response_channels():
            result = ""
            if guild_id in ocr_response_channels and ocr_response_channels[guild_id]:
                channels = []
                for channel_id in ocr_response_channels[guild_id]:
                    channel = self.bot.get_channel(channel_id)
                    channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                    # Get language for this channel
                    lang = "eng"
                    if 'ocr_channel_config' in config and guild_id in config['ocr_channel_config'] and str(channel_id) in config['ocr_channel_config'][guild_id]:
                        lang = config['ocr_channel_config'][guild_id][str(channel_id)].get('lang', 'eng')
                    lang_display = " (Russian)" if lang == "rus" else ""
                    channels.append(f"• {channel_name}{lang_display}")
                result = "\n".join(channels)
            else:
                result = "No OCR response channels configured."
            return {"name": "💬 OCR Response Channels", "value": result, "inline": False}
            
        async def get_ocr_fallback_channels():
            result = ""
            if guild_id in ocr_response_fallback and ocr_response_fallback[guild_id]:
                channels = []
                for channel_id in ocr_response_fallback[guild_id]:
                    channel = self.bot.get_channel(channel_id)
                    channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                    channels.append(f"• {channel_name}")
                result = "\n".join(channels)
            else:
                result = "No OCR fallback channels configured."
            return {"name": "🔄 OCR Fallback Channels", "value": result, "inline": False}
            
        async def get_manager_roles():
            result = ""
            if guild_id in command_permissions and "*" in command_permissions[guild_id] and command_permissions[guild_id]["*"]:
                roles = []
                for role_id in command_permissions[guild_id]["*"]:
                    role = ctx.guild.get_role(int(role_id))
                    role_name = role.mention if role else f"Unknown Role ({role_id})"
                    roles.append(f"• {role_name}")
                result = "\n".join(roles)
            else:
                result = "No bot manager roles configured."
            return {"name": "👑 Bot Manager Roles", "value": result, "inline": False}
            
        async def get_manager_users():
            result = ""
            if (guild_id in command_permissions and 
                "users" in command_permissions[guild_id] and 
                "*" in command_permissions[guild_id]["users"] and 
                command_permissions[guild_id]["users"]["*"]):
                users = []
                fetch_tasks = []
                for user_id in command_permissions[guild_id]["users"]["*"]:
                    fetch_tasks.append(self.bot.fetch_user(int(user_id)))
                
                if fetch_tasks:
                    fetched_users = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                    for i, user_or_error in enumerate(fetched_users):
                        user_id = command_permissions[guild_id]["users"]["*"][i]
                        if isinstance(user_or_error, Exception):
                            users.append(f"• Unknown User ({user_id})")
                        else:
                            users.append(f"• @{user_or_error.name}")
                    result = "\n".join(users)
                
            if not result:
                result = "No bot manager users configured."
            return {"name": "👤 Bot Manager Users", "value": result, "inline": False}
            
        async def get_cmd_role_permissions():
            result = ""
            if guild_id in command_permissions:
                sections = []
                for cmd_name, roles in sorted(command_permissions[guild_id].items()):
                    if cmd_name not in ["*", "users"] and roles:  # Skip wildcard and users entries
                        role_lines = [f"**{cmd_name}**"]
                        for role_id in roles:
                            role = ctx.guild.get_role(int(role_id))
                            role_name = role.mention if role else f"Unknown Role ({role_id})"
                            role_lines.append(f"• {role_name}")
                        sections.append("\n".join(role_lines))
                if sections:
                    result = "\n\n".join(sections)
            if not result:
                result = "No command-specific role permissions configured."
            return {"name": "🔐 Command Role Permissions", "value": result, "inline": False}
            
        async def get_cmd_user_permissions():
            result = ""
            if guild_id in command_permissions and "users" in command_permissions[guild_id]:
                sections = []
                for cmd_name, users in sorted(command_permissions[guild_id]["users"].items()):
                    if cmd_name != "*" and users:  # Skip the wildcard entry
                        user_lines = [f"**{cmd_name}**"]
                        fetch_tasks = []
                        user_ids = []
                        for user_id in users:
                            user_ids.append(user_id)
                            fetch_tasks.append(self.bot.fetch_user(int(user_id)))
                        
                        if fetch_tasks:
                            fetched_users = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                            for i, user_or_error in enumerate(fetched_users):
                                user_id = user_ids[i]
                                if isinstance(user_or_error, Exception):
                                    user_lines.append(f"• Unknown User ({user_id})")
                                else:
                                    user_lines.append(f"• @{user_or_error.name}")
                        sections.append("\n".join(user_lines))
                if sections:
                    result = "\n\n".join(sections)
            if not result:
                result = "No command-specific user permissions configured."
            return {"name": "👤 Command User Permissions", "value": result, "inline": False}
        
        # Execute all fetch operations concurrently with asyncio.gather
        fetch_tasks = [
            get_ocr_read_channels(),
            get_ocr_response_channels(),
            get_ocr_fallback_channels(),
            get_manager_roles(),
            get_manager_users(),
            get_cmd_role_permissions(),
            get_cmd_user_permissions()
        ]
        
        # Wait for all tasks to complete
        fields = await asyncio.gather(*fetch_tasks)
        
        # Add footer
        footer_text = f"{ctx.guild.name} | Server ID: {ctx.guild.id}"
        
        # Use the universal embed response function
        await create_embed_response(
            ctx=ctx,
            title="Server Configuration",
            description=description,
            fields=fields,
            footer_text=footer_text,
            thumbnail_url=thumbnail_url
        )

async def setup(bot):
    await bot.add_cog(BotConfigCog(bot))
