import discord
from discord.ext import commands
import platform
import socket
import psutil
import os
import cpuinfo
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from core.pattern_manager import load_patterns
from utils.embed_helper import create_embed_response
from core.bot import get_server_prefix
from utils.constants import (
    BOT_NAME, BOT_VERSION, AUTHOR_NAME, AUTHOR_URL, 
    AUTHOR_ICON_URL, REPO_URL, GITHUB_ICON_URL, get_uptime
)
from utils.stats_tracker import get_ocr_stats

logger = get_logger()

class SystemCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='shutdown', help='Shut down the bot completely (owner only).\nNo arguments required.\nExample: !shutdown')
    @commands.is_owner()  # Only the bot owner can use this command
    @command_category("System")
    async def shutdown(self, ctx):
        """Shut down the bot"""
        response = "Shutting down."
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.info(f"Response: {response}")
        await ctx.reply(response)
        await self.bot.close()  # Gracefully close the bot

    @commands.command(name='reload_patterns', help='Reload pattern configurations from the patterns.json file.\nNo arguments required.\nExample: !reload_patterns')
    @commands.is_owner()  # Only the bot owner can use this command
    @command_category("System")
    async def reload_patterns(self, ctx):
        """Reload patterns from the patterns.json file"""
        if load_patterns():
            await ctx.reply("Successfully reloaded pattern configurations.")
        else:
            await ctx.reply("Error loading pattern configurations. Check the log for details.")

    @commands.command(name='help', aliases=['info'], help='Show info about the bot and its features.\nArguments: [command] (optional) - Get detailed help on a specific command\nExample: !help, !info or !help server_info')
    @commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
    @command_category("System")
    async def help_command(self, ctx, command_name=None):
        """Display help information about the bot and its commands"""
        prefix = get_server_prefix(self.bot, ctx.message)
        
        # If a specific command is requested, show detailed help for that command
        if command_name:
            cmd = self.bot.get_command(command_name)
            if cmd:
                # Check if user has permission to use this command
                try:
                    can_run = await cmd.can_run(ctx)
                except:
                    can_run = False
                    
                if not can_run:
                    await ctx.send(f"You don't have permission to use the `{command_name}` command.")
                    return
                
                # Build fields for specific command help    
                fields = []
                
                # Add category if available
                if hasattr(cmd, 'category'):
                    fields.append({"name": "Category", "value": cmd.category, "inline": True})
                
                # Check for required arguments in the command signature
                signature = cmd.signature
                if signature:
                    fields.append({"name": "Usage", "value": f"`{prefix}{cmd.name} {signature}`", "inline": False})
                else:
                    fields.append({"name": "Usage", "value": f"`{prefix}{cmd.name}`", "inline": False})
                    
                # Add aliases if any exist
                if cmd.aliases:
                    aliases = ", ".join([f"{prefix}{alias}" for alias in cmd.aliases])
                    fields.append({"name": "Aliases", "value": aliases, "inline": False})
                
                await create_embed_response(
                    ctx=ctx,
                    title=f"Command: {prefix}{cmd.name}",
                    description=cmd.help or "No description available",
                    fields=fields,
                    footer_text=f"{BOT_NAME} v{BOT_VERSION} | Type {prefix}help for a list of all commands"
                )
                return
            else:
                await ctx.send(f"No command called '{command_name}' found.")
                return
    
        # Create main description
        description = f"Use `{prefix}help <command>` for detailed information on a command.\n" \
                      f"**Note:** You only see commands you have permission to use.\n\n" \
                      f"**Current prefix:** `{prefix}`"
        
        # Define fields
        fields = []
        
        # Add bot info section
        uptime = get_uptime()
        fields.append({
            "name": "📝 About", 
            "value": f"{BOT_NAME} is an open-source bot developed by @{AUTHOR_NAME}.\n" \
                     "It uses OCR (Optical Character Recognition) to scan images for text patterns and provide automatic responses to common issues.\n",
            "inline": False
        })
    
        # Dynamically organize commands by their categories
        categories = {}
        for cmd in self.bot.commands:
            # Skip commands the user can't use
            try:
                if not await cmd.can_run(ctx):
                    continue
            except:
                continue  # Skip if can_run raises an exception
            
            # Get the command's category (or "Miscellaneous" if not set)
            # Make sure to check the command itself first, then the callback
            if hasattr(cmd, 'category'):
                category = cmd.category
            elif hasattr(cmd, 'callback') and hasattr(cmd.callback, 'category'):
                category = cmd.callback.category
            else:
                category = "Miscellaneous"
            
            # Add command to its category
            if category not in categories:
                categories[category] = []
            categories[category].append(cmd)
        
        # Process categories and add fields
        for category_name, cmds in sorted(categories.items()):
            if cmds:
                # Sort commands by name
                sorted_cmds = sorted(cmds, key=lambda x: x.name)
                
                # Format command list with brief descriptions
                command_entries = []
                for cmd in sorted_cmds:
                    brief_desc = cmd.help.split('\n')[0] if cmd.help else "No description"
                    command_entries.append(f"• `{prefix}{cmd.name}` - {brief_desc}")
                
                # Combine entries and check length
                category_value = "\n".join(command_entries)
                
                # If value is too long, break it into multiple fields
                if len(category_value) > 1024:
                    # Calculate how to split entries into multiple fields
                    parts = []
                    current_part = []
                    current_length = 0
                    
                    for entry in command_entries:
                        if current_length + len(entry) + 1 > 1024:  # +1 for the newline
                            parts.append("\n".join(current_part))
                            current_part = [entry]
                            current_length = len(entry) + 1
                        else:
                            current_part.append(entry)
                            current_length += len(entry) + 1
                            
                    if current_part:
                        parts.append("\n".join(current_part))
                    
                    # Create multiple fields with proper naming
                    for i, part in enumerate(parts):
                        field_name = f"📋 {category_name}"
                        if len(parts) > 1:
                            field_name += f" ({i+1}/{len(parts)})"
                        
                        fields.append({
                            "name": field_name,
                            "value": part,
                            "inline": False
                        })
                else:
                    fields.append({
                        "name": f"📋 {category_name}",
                        "value": category_value,
                        "inline": False
                    })
                    
        # Add footer text
        footer_text = f"{BOT_NAME} v{BOT_VERSION} | Type {prefix}help <command> for more info\n" \
                        f"Uptime: {uptime}"
        
        # Send the response
        await create_embed_response(
            ctx=ctx,
            title=BOT_NAME,
            url=REPO_URL,  # clickable title
            author_name=AUTHOR_NAME,
            author_url=AUTHOR_URL,
            author_icon_url=AUTHOR_ICON_URL,
            description=description,
            fields=fields,
            footer_text=footer_text,
            footer_icon_url=GITHUB_ICON_URL
        )

    @commands.command(name='host', help='Display detailed information about the host system.\nNo arguments required.\nExample: !host')
    @command_category("System")
    @commands.is_owner()  # Only the bot owner can use this command
    async def host(self, ctx):
        """Display information about the host system running the bot"""
        # Get system information
        uname = platform.uname()
        hostname = socket.gethostname()
        
        # Get detailed CPU info
        try:
            cpu_info = cpuinfo.get_cpu_info()
            cpu_model = cpu_info.get('brand_raw', 'Unknown')
        except:
            cpu_model = "Could not detect (py-cpuinfo module may be missing)"
        
        # Prepare system information
        system_info = {
            "System": uname.system,
            "Node Name": hostname,
            #"Release": uname.release,
            #"Version": uname.version,
            #"Machine": uname.machine,
            "Processor": uname.processor if uname.processor else "Unknown",
            "CPU Model": cpu_model,
            "Python Version": platform.python_version()
        }
        
        # Get resource usage
        cpu_usage = f"{psutil.cpu_percent()}%"
        memory = psutil.virtual_memory()
        ram_usage = f"{memory.percent}% ({round(memory.used/1024/1024/1024, 2)} GB / {round(memory.total/1024/1024/1024, 2)} GB)"
        
        disk = psutil.disk_usage('/')
        disk_usage = f"{disk.percent}% ({round(disk.used/1024/1024/1024, 2)} GB / {round(disk.total/1024/1024/1024, 2)} GB)"
        
        # Get bot information
        uptime = get_uptime()
        pid = os.getpid()
        process = psutil.Process(pid)
        bot_memory = f"{round(process.memory_info().rss/1024/1024, 2)} MB"
        
        # Get OCR stats
        try:
            ocr_stats = get_ocr_stats()
            avg_process_time = f"{ocr_stats.get('avg_time', 0):.2f} seconds"
            total_images = ocr_stats.get('total_processed', 0)
            ocr_info = f"**Average Processing Time:** {avg_process_time}\n**Total Images Processed:** {total_images}"
        except Exception as e:
            logger.error(f"Could not get OCR stats: {str(e)}")
            ocr_info = "**OCR Stats:** Not available"
        
        # Create fields for the embed
        fields = [
            {"name": "🖥️ Host System", "value": "\n".join([f"**{k}:** {v}" for k, v in system_info.items()]), "inline": False},
            #{"name": "📊 Resource Usage", "value": f"**CPU:** {cpu_usage}\n**RAM:** {ram_usage}\n**Disk:** {disk_usage}", "inline": False},
            {"name": "🤖 Bot Details", "value": f"**Name:** {BOT_NAME} v{BOT_VERSION}\n**Process ID:** {pid}\n**Memory Usage:** {bot_memory}\n**Uptime:** {uptime}", "inline": False},
            {"name": "🔍 OCR Performance", "value": ocr_info, "inline": False}
        ]
        
        await create_embed_response(
            ctx=ctx,
            title="Host Information",
            description=f"Detailed information about the system hosting {BOT_NAME}",
            fields=fields,
            footer_text=f"{BOT_NAME} v{BOT_VERSION}"
        )
