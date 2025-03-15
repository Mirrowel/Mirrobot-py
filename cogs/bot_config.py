import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from config.config_manager import save_config
from utils.embed_helper import create_embed_response

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
        
        # Build the fields
        fields = []
        
        # Get various configurations
        ocr_read_channels = config.get('ocr_read_channels', {})
        ocr_response_channels = config.get('ocr_response_channels', {})
        ocr_response_fallback = config.get('ocr_response_fallback', {})
        command_permissions = config.get('command_permissions', {})
        
        # OCR Read Channels field
        ocr_read_value = ""
        if guild_id in ocr_read_channels and ocr_read_channels[guild_id]:
            for channel_id in ocr_read_channels[guild_id]:
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                ocr_read_value += f"• {channel_name}\n"
        else:
            ocr_read_value = "No OCR read channels configured."
        fields.append({"name": "📷 OCR Read Channels", "value": ocr_read_value, "inline": False})
        
        # OCR Response Channels field
        ocr_response_value = ""
        if guild_id in ocr_response_channels and ocr_response_channels[guild_id]:
            for channel_id in ocr_response_channels[guild_id]:
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                ocr_response_value += f"• {channel_name}\n"
        else:
            ocr_response_value = "No OCR response channels configured."
        fields.append({"name": "💬 OCR Response Channels", "value": ocr_response_value, "inline": False})
        
        # OCR Fallback Channels field
        ocr_fallback_value = ""
        if guild_id in ocr_response_fallback and ocr_response_fallback[guild_id]:
            for channel_id in ocr_response_fallback[guild_id]:
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
                ocr_fallback_value += f"• {channel_name}\n"
        else:
            ocr_fallback_value = "No OCR fallback channels configured."
        fields.append({"name": "🔄 OCR Fallback Channels", "value": ocr_fallback_value, "inline": False})
        
        # Manager Roles field
        manager_roles_value = ""
        if guild_id in command_permissions and "*" in command_permissions[guild_id] and command_permissions[guild_id]["*"]:
            for role_id in command_permissions[guild_id]["*"]:
                role = ctx.guild.get_role(int(role_id))
                role_name = role.mention if role else f"Unknown Role ({role_id})"
                manager_roles_value += f"• {role_name}\n"
        else:
            manager_roles_value = "No bot manager roles configured."
        fields.append({"name": "👑 Bot Manager Roles", "value": manager_roles_value, "inline": False})
        
        # Manager Users field
        manager_users_value = ""
        if (guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and 
            "*" in command_permissions[guild_id]["users"] and 
            command_permissions[guild_id]["users"]["*"]):
            for user_id in command_permissions[guild_id]["users"]["*"]:
                user = await self.bot.fetch_user(int(user_id))
                user_name = f"@{user.name}" if user else f"Unknown User ({user_id})"
                manager_users_value += f"• {user_name}\n"
        if not manager_users_value:
            manager_users_value = "No bot manager users configured."
        fields.append({"name": "👤 Bot Manager Users", "value": manager_users_value, "inline": False})
        
        # Command-specific permissions fields - Roles
        cmd_roles_value = ""
        if guild_id in command_permissions:
            for cmd_name, roles in sorted(command_permissions[guild_id].items()):
                if cmd_name not in ["*", "users"] and roles:  # Skip wildcard and users entries
                    cmd_roles_value += f"**{cmd_name}**\n"
                    for role_id in roles:
                        role = ctx.guild.get_role(int(role_id))
                        role_name = role.mention if role else f"Unknown Role ({role_id})"
                        cmd_roles_value += f"• {role_name}\n"
                    cmd_roles_value += "\n"
        if not cmd_roles_value:
            cmd_roles_value = "No command-specific role permissions configured."
        fields.append({"name": "🔐 Command Role Permissions", "value": cmd_roles_value, "inline": False})
        
        # Command-specific permissions - Users
        cmd_users_value = ""
        if guild_id in command_permissions and "users" in command_permissions[guild_id]:
            for cmd_name, users in sorted(command_permissions[guild_id]["users"].items()):
                if cmd_name != "*" and users:  # Skip the wildcard entry
                    cmd_users_value += f"**{cmd_name}**\n"
                    for user_id in users:
                        try:
                            user = await self.bot.fetch_user(int(user_id))
                            user_name = f"@{user.name}" if user else f"Unknown User ({user_id})"
                            cmd_users_value += f"• {user_name}\n"
                        except:
                            cmd_users_value += f"• Unknown User ({user_id})\n"
                    cmd_users_value += "\n"
        if not cmd_users_value:
            cmd_users_value = "No command-specific user permissions configured."
        fields.append({"name": "👤 Command User Permissions", "value": cmd_users_value, "inline": False})
        
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
