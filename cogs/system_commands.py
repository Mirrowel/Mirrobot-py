import discord
from discord.ext import commands
import platform
import psutil
import os
import time  # Added for ping command
import socket
import cpuinfo
import asyncio  # Add this import
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from core.pattern_manager import load_patterns
from utils.embed_helper import create_embed_response
from core.bot import get_ocr_queue_stats, get_server_prefix
from utils.constants import (
    BOT_NAME, BOT_VERSION, AUTHOR_NAME, AUTHOR_URL, 
    AUTHOR_ICON_URL, REPO_URL, GITHUB_ICON_URL, get_uptime
)
from utils.stats_tracker import get_ocr_stats
from discord.ui import View, Select, Button
from typing import Dict, List, Optional, Union
import re

logger = get_logger()

def get_emoji(input_text: str, max_emojis: int = 1) -> str:
    """
    Return appropriate emojis based on keywords found in the input text.
    
    Args:
        input_text: The text to search for keywords
        max_emojis: Maximum number of emojis to return (default: 1)
        
    Returns:
        String containing 1 or more emoji characters
    """
    # Convert to lowercase for case-insensitive matching
    input_lower = input_text.lower()
    
    # Define keyword to emoji mappings
    keyword_emojis = {
        # Primary categories
        "pattern": "🔍",
        "ocr": "📷",
        "system": "⚙️",
        "permission": "🔐",
        "configuration": "🛠️",
        "utilities": "🔧",
        "config": "🛠️",
        "setup": "🔧",
        "admin": "👑",
        "moderation": "🔨",
        "help": "❓",
        "info": "ℹ️",
        "utility": "🔧",
        "tools": "🧰",
        "image": "🖼️",
        "text": "📝",
        "chat": "💬",
        "management": "📊",
        "server": "🖥️",
        "bot": "🤖",
        "stats": "📈",
        "analytic": "📊",
        "notification": "🔔",
        "alert": "⚠️",
        "misc": "📌",
        "miscellaneous": "📌",
        "other": "📎",
    }
    
    # Find all matching keywords with their positions in the input string
    matched_keywords = []
    for keyword, emoji in keyword_emojis.items():
        pos = input_lower.find(keyword)
        if pos != -1:
            matched_keywords.append((pos, keyword, emoji))
    
    # Sort by position in the input string
    matched_keywords.sort()
    
    # Extract emojis in order of appearance
    matched_emojis = [emoji for _, _, emoji in matched_keywords]
    
    # Return the appropriate number of emojis
    if not matched_emojis:
        return "📌"  # Default emoji if no match
    elif len(matched_emojis) == 1:
        return matched_emojis[0]
    # Return unique emojis up to max_emojis
    unique_emojis = []
    for emoji in matched_emojis:
        if emoji not in unique_emojis:
            unique_emojis.append(emoji)
            if len(unique_emojis) >= max_emojis:
                break
    
    return "".join(unique_emojis[:max_emojis])

class HelpView(discord.ui.View):
    def __init__(self, ctx, help_data, timeout=180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.help_data = help_data
        self.current_category = None
        self.current_page = 0
        self.pages_per_category = {}
        self.embeds_per_category = {}
        
        # Initialize category selector
        self.setup_category_selector()
        # Create embeds for each category
        self.generate_category_embeds()
        
    def setup_category_selector(self):
        # Create the category dropdown
        options = []
        
        # Add overview option
        options.append(discord.SelectOption(
            label="Overview", 
            description="General bot information and commands overview",
            emoji="📋",
            value="overview"
        ))
        
        # Add options for each category
        for category in sorted(self.help_data['categories'].keys()):
            if category == "System" and self.ctx.author.id != self.ctx.bot.owner_id:
                # Skip system category for non-owners if it contains only owner commands
                if all(cmd.checks and commands.is_owner().predicate in [c.__func__ for c in cmd.checks] 
                       for cmd in self.help_data['categories'][category]):
                    continue
                
            # Get appropriate emoji for the category using our helper function - limit to 1
            emoji = get_emoji(category, max_emojis=1)
            
            options.append(discord.SelectOption(
                label=category,
                description=f"View {category} commands",
                emoji=emoji,
                value=category
            ))
        
        # Create the select menu
        select = Select(
            placeholder="Select a command category...",
            options=options,
            custom_id="category_select"
        )
        select.callback = self.category_select_callback
        self.add_item(select)
    
    async def category_select_callback(self, interaction: discord.Interaction):
        # Get selected category
        self.current_category = interaction.data['values'][0]
        self.current_page = 0
        
        # Update buttons state
        self.update_button_states()
        
        # Display the appropriate embed
        await interaction.response.edit_message(
            embed=self.get_current_embed(),
            view=self
        )
    
    def generate_category_embeds(self):
        prefix = self.help_data['prefix']
        
        # Create overview embed first
        self.embeds_per_category['overview'] = self.create_overview_embed()
        
        # Then create embeds for each category
        for category, cmds in self.help_data['categories'].items():
            if not cmds:
                continue
                
            embeds = []
            
            # Create embeds with paginated commands
            command_entries = []
            for cmd in sorted(cmds, key=lambda x: x.name):
                brief_desc = cmd.help.split('\n')[0] if cmd.help else "No description"
                command_entries.append(f"• `{prefix}{cmd.name}` - {brief_desc}")
            
            # Split into pages to avoid hitting the 1024 character limit
            pages = []
            current_page = []
            current_page_text = ""
            
            for entry in command_entries:
                # Check if adding this entry would exceed Discord's field value limit
                if len(current_page_text + entry + "\n") > 1024:  # Using 1024 as a safe limit
                    if current_page:  # Only add if we have entries
                        pages.append(current_page)
                    current_page = [entry]
                    current_page_text = entry + "\n"
                else:
                    current_page.append(entry)
                    current_page_text += entry + "\n"
            
            if current_page:  # Add any remaining entries
                pages.append(current_page)
            
            # Store page count for navigation
            self.pages_per_category[category] = len(pages)
            
            # Get the appropriate emoji for this category
            category_emoji = get_emoji(category, max_emojis=2)
            
            # Create an embed for each page
            for i, page_entries in enumerate(pages):
                embed = discord.Embed(
                    title=f"{category_emoji} {category} Commands",
                    description=f"Commands related to {category.lower()} functionality.\nPage {i+1} of {len(pages)}",
                    color=discord.Color.blue()
                )
                
                # Add fields with commands
                embed.add_field(
                    name="Available Commands",
                    value="\n".join(page_entries),
                    inline=False
                )
                
                # Add navigation instructions
                embed.set_footer(
                    text=f"{BOT_NAME} v{BOT_VERSION} | Use {prefix}help <command> for detailed help"
                )
                
                embeds.append(embed)
            
            self.embeds_per_category[category] = embeds
    
    def create_overview_embed(self):
        """Creates the main overview embed for help command"""
        prefix = self.help_data['prefix']
        
        embed = discord.Embed(
            title=f"{BOT_NAME} Help Menu",
            url=REPO_URL,
            description=f"Select a category from the dropdown menu below to view available commands.\n"
                        f"**Note:** You only see commands you have permission to use.\n\n"
                        f"**Current prefix:** `{prefix}`",
            color=discord.Color.blue()
        )
        
        # Add bot info
        embed.add_field(
            name="📝 About", 
            value=f"{BOT_NAME} is an open-source bot developed by @{AUTHOR_NAME}.\n" \
                  f"It uses OCR (Optical Character Recognition) to scan images for text patterns "
                  f"and provide automatic responses to common issues.",
            inline=False
        )
        
        # Add category summary
        categories_text = ""
        for category, cmds in sorted(self.help_data['categories'].items()):
            if cmds:
                # Get appropriate emoji for this category - can use up to 2 for embed content
                emoji = get_emoji(category, max_emojis=2)
                categories_text += f"{emoji} **{category}** - {len(cmds)} commands\n"
        
        embed.add_field(
            name="📋 Categories",
            value=categories_text or "No categories available",
            inline=False
        )
        
        # Add usage tips
        embed.add_field(
            name="💡 Tips",
            value=f"• Use the dropdown below to browse command categories\n"
                  f"• Use `{prefix}help <command>` for detailed help on a specific command\n"
                  f"• Use `{prefix}help` for a simple text-based help menu",
            inline=False
        )
        
        # Add footer info
        embed.set_footer(
            text=f"{BOT_NAME} v{BOT_VERSION} | Uptime: {get_uptime()}"
        )
        
        # Set author info
        embed.set_author(
            name=AUTHOR_NAME,
            url=AUTHOR_URL,
            icon_url=AUTHOR_ICON_URL
        )
        
        return embed
    
    def get_current_embed(self):
        """Returns the current embed to display based on category and page"""
        if not self.current_category:
            self.current_category = "overview"
            
        if self.current_category == "overview":
            return self.embeds_per_category["overview"]
        
        category_embeds = self.embeds_per_category.get(self.current_category, [])
        if not category_embeds:
            return discord.Embed(
                title="No Commands Available",
                description="There are no commands in this category that you can use.",
                color=discord.Color.red()
            )
        
        # Make sure page index is valid
        if self.current_page >= len(category_embeds):
            self.current_page = 0
        elif self.current_page < 0:
            self.current_page = len(category_embeds) - 1
            
        return category_embeds[self.current_page]
    
    def update_button_states(self):
        """Update button states based on current page and category"""
        # No pagination needed for overview
        if self.current_category == "overview":
            for item in self.children:
                if isinstance(item, Button):
                    item.disabled = True
            return
            
        # Get number of pages for current category
        page_count = len(self.embeds_per_category.get(self.current_category, []))
        
        # Enable/disable buttons based on page count
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = page_count <= 1
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        self.current_page -= 1
        if self.current_page < 0:
            self.current_page = len(self.embeds_per_category.get(self.current_category, [])) - 1
            
        await interaction.response.edit_message(
            embed=self.get_current_embed(),
            view=self
        )
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=True)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        self.current_page += 1
        if self.current_page >= len(self.embeds_per_category.get(self.current_category, [])):
            self.current_page = 0
            
        await interaction.response.edit_message(
            embed=self.get_current_embed(),
            view=self
        )

class SystemCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._permission_cache = {}  # Cache for command permissions
    
    # Clear the permission cache periodically or when permissions might have changed
    def clear_permission_cache(self):
        self._permission_cache.clear()

    # Helper method to check permissions with caching
    async def check_command_permission(self, ctx, cmd):
        # Create a unique cache key based on user, guild, and command
        cache_key = f"{ctx.author.id}:{ctx.guild.id}:{cmd.name}"
        
        # Check if we have a cached result
        if cache_key in self._permission_cache:
            return self._permission_cache[cache_key]
            
        try:
            result = await cmd.can_run(ctx)
            self._permission_cache[cache_key] = result
            return result
        except:
            self._permission_cache[cache_key] = False
            return False

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
    @commands.bot_has_permissions(embed_links=True)
    @command_category("System")
    async def help_command(self, ctx, command_name=None):
        """Display help information about the bot and its commands"""
        prefix = get_server_prefix(self.bot, ctx.message)
        
        # If a specific command is requested, show detailed help for that command
        if command_name:
            cmd = self.bot.get_command(command_name)
            if cmd:
                # Check if user has permission to use this command - use cached check
                can_run = await self.check_command_permission(ctx, cmd)
                    
                if not can_run:
                    await ctx.send(f"You don't have permission to use the `{command_name}` command.")
                    return
                
                # Build fields for specific command help    
                fields = []
                
                # Add category if available
                if hasattr(cmd, 'category'):
                    category = cmd.category
                    emoji = get_emoji(category)
                    fields.append({"name": "Category", "value": f"{emoji} {category}", "inline": True})
                
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
                      f"**Current prefix:** `{prefix}`\n\n" \
                      f"For an interactive help menu with dropdown categories, use `{prefix}helpmenu`"
        
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
        
        # Collect all commands for permission check
        commands_to_check = list(self.bot.commands)
        check_tasks = [self.check_command_permission(ctx, cmd) for cmd in commands_to_check]
        
        # Run permission checks in parallel
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        # Process results
        for i, cmd in enumerate(commands_to_check):
            # Skip commands the user can't use
            if not isinstance(results[i], bool) or not results[i]:
                continue
            
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
                # Get the appropriate emoji for this category - use max 2 emojis
                emoji = get_emoji(category_name, 2)
                
                # Sort commands by name
                sorted_cmds = sorted(cmds, key=lambda x: x.name)
                
                # Format command list with brief descriptions
                command_entries = []
                for cmd in sorted_cmds:
                    brief_desc = cmd.help.split('\n')[0] if cmd.help else "No description"
                    command_entries.append(f"• `{prefix}{cmd.name}` - {brief_desc}")
                
                # Combine entries and check length
                category_value = "\n".join(command_entries)
                fields.append({
                    "name": f"{emoji} {category_name}",
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
            footer_icon_url=GITHUB_ICON_URL,
            field_unbroken=True # Keep fields unbroken for better formatting
        )
        
    @commands.command(name='helpmenu', help='Shows an interactive help menu with dropdown categories and command pagination.\nNo arguments required.\nExample: !helpmenu')
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True)
    @command_category("System")
    async def helpmenu_command(self, ctx):
        """Display an interactive help menu with dropdown categories"""
        prefix = get_server_prefix(self.bot, ctx.message)
        
        # Prepare help data structure
        help_data = {
            'prefix': prefix,
            'categories': {}
        }
        
        # Collect all commands for permission check
        commands_to_check = list(self.bot.commands)
        check_tasks = [self.check_command_permission(ctx, cmd) for cmd in commands_to_check]
        
        # Run permission checks in parallel
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        # Process results
        for i, cmd in enumerate(commands_to_check):
            # Skip commands the user can't use
            if not isinstance(results[i], bool) or not results[i]:
                continue
            
            # Get the command's category
            if hasattr(cmd, 'category'):
                category = cmd.category
            elif hasattr(cmd, 'callback') and hasattr(cmd.callback, 'category'):
                category = cmd.callback.category
            else:
                category = "Miscellaneous"
                
            # Add command to its category
            if category not in help_data['categories']:
                help_data['categories'][category] = []
                
            help_data['categories'][category].append(cmd)
            
        # Create and send the interactive help view
        view = HelpView(ctx, help_data)
        await ctx.send(embed=view.get_current_embed(), view=view)

    @commands.command(name='host', help='Display detailed information about the host system.\nNo arguments required.\nExample: !host')
    @command_category("System")
    @commands.is_owner()  # Only the bot owner can use this command
    @commands.bot_has_permissions(embed_links=True)
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
            #"Node Name": hostname,
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

    @commands.command(name='ping', help='Check the bot\'s current latency.\nNo arguments required.\nExample: !ping')
    @commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
    @command_category("System")
    @has_command_permission()
    async def ping(self, ctx):
        """Ping command to check bot latency"""
        # Initial message and timing for message response
        start_response = time.time()
        message = await ctx.send("Measuring ping over multiple tries...")
        end_response = time.time()
        response_time = round((end_response - start_response) * 1000)
        
        # Discord API latency
        api_latency = round(self.bot.latency * 1000)
        
        # Perform multiple ping measurements
        num_pings = 3
        ping_results = []
        
        for i in range(num_pings):
            start_time = time.time()
            # Use ctx.typing() which is the correct context manager for typing indicator
            async with ctx.typing():
                # Just measuring the time it takes to send a typing indicator
                pass
            end_time = time.time()
            ping_ms = round((end_time - start_time) * 1000)
            ping_results.append(ping_ms)
            await asyncio.sleep(0.5)  # Small delay between measurements
        
        # Calculate average ping
        avg_ping = round(sum(ping_results) / len(ping_results))
        
        # Create embed with results
        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
        embed.add_field(name="Discord API Latency", value=f"{api_latency}ms", inline=True)
        embed.add_field(name="Message Response Time", value=f"{response_time}ms", inline=True)
        
        # Add individual ping results
        ping_values = "\n".join([f"Ping #{i+1}: **{ping}ms**" for i, ping in enumerate(ping_results)])
        embed.add_field(name="Typing Indicator Roundtrips", value=f"{ping_values}\n\n**Average**: {avg_ping}ms", inline=False)
        
        await message.edit(content=None, embed=embed)

    @commands.command(name='uptime', help='Display how long the bot has been running.\nNo arguments required.\nExample: !uptime')
    @commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
    @command_category("System")
    @has_command_permission()  # Check if user has permission to use this command
    async def uptime(self, ctx):
        """Display the current uptime of the bot"""
        from utils.constants import get_uptime
        
        uptime_str = get_uptime()
        embed = discord.Embed(
            title="⏱️ Bot Uptime",
            description=f"Bot has been running for: **{uptime_str}**",
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed)

    @commands.command(name='invite', help='Get an invite link to add this bot to other servers.\nNo arguments required.\nExample: !invite')
    @commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
    @commands.is_owner()  # Only the bot owner can use this command
    @command_category("System")
    async def invite(self, ctx):
        """Generate an invite link for the bot"""
        # Calculate necessary permissions for the bot's functionality
        permissions = discord.Permissions(
            send_messages=True, 
            embed_links=True,
            attach_files=True,
            read_messages=True,
            read_message_history=True,
            manage_messages=False,
            add_reactions=True
        )
        
        # Generate the OAuth2 URL with proper permissions
        invite_url = discord.utils.oauth_url(str(self.bot.user.id), permissions=permissions)
        
        embed = discord.Embed(
            title="🔗 Invite Me to Your Server",
            description=f"Click the link below to add me to your Discord server:\n[Invite Link]({invite_url})",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Note: You need 'Manage Server' permission to add bots")
        
        await ctx.send(embed=embed)

    from core.bot import get_ocr_queue_stats

    @commands.command(name='status', help='Display bot status, uptime, and statistics.\nNo additional arguments required.\nExample: !status')
    @has_command_permission()
    @commands.bot_has_permissions(embed_links=True)
    @command_category("System")
    async def status(self, ctx):
        """Display current bot status and statistics"""
        # Get OCR stats
        try:
            ocr_stats = get_ocr_stats()
            avg_process_time = f"{ocr_stats.get('avg_time', 0):.2f} seconds"
            total_images = ocr_stats.get('total_processed', 0)
            
            # Get queue stats
            queue_stats = get_ocr_queue_stats(self.bot)
            queue_info = (
                f"**Queue Size:** {queue_stats['current_size']}/{queue_stats['max_size']} "
                f"({queue_stats['utilization_pct']:.1f}%)\n"
                f"**Queued Total:** {queue_stats['total_enqueued']}\n"
                f"**Processed:** {queue_stats['total_processed']}\n"
                f"**Rejected:** {queue_stats['total_rejected']}\n"
                f"**High Water Mark:** {queue_stats['high_watermark']}"
            )
            
            ocr_info = f"**Average Processing Time:** {avg_process_time}\n**Total Images Processed:** {total_images}"
        except Exception as e:
            logger.error(f"Could not get OCR stats: {str(e)}")
            ocr_info = "**OCR Stats:** Not available"
            queue_info = "**Queue Stats:** Not available"
        
        fields = []
        
        # Add bot uptime information
        uptime_str = get_uptime()
        fields.append({"name": "⏱️ Uptime", "value": uptime_str, "inline": False})
        
        # Add OCR stats
        fields.append(
            {"name": "🔍 OCR Performance", "value": ocr_info, "inline": False}
        )
        
        # Add queue stats
        fields.append(
            {"name": "📊 Queue Statistics", "value": queue_info, "inline": False}
        )
        
        # Add server count
        server_count = len(self.bot.guilds)
        user_count = sum(guild.member_count for guild in self.bot.guilds)
        
        fields.append(
            {"name": "🌐 Server Stats", "value": f"**Servers:** {server_count}\n**Users:** {user_count}", "inline": False}
        )
        
        # Create and send the embed
        await create_embed_response(
            ctx=ctx,
            title=f"{BOT_NAME} Status",
            description=f"Current status and statistics for {BOT_NAME} v{BOT_VERSION}",
            fields=fields,
            footer_text=f"{BOT_NAME} v{BOT_VERSION}"
        )

async def setup(bot):
    await bot.add_cog(SystemCommandsCog(bot))
