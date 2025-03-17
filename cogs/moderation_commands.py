import asyncio
import discord
from discord.ext import commands, tasks
import json
import os
import datetime
import re
from typing import Dict, List, Optional, Union, Tuple
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category, check_target_permissions
from utils.embed_helper import create_embed_response

logger = get_logger()

# File paths for storing data
WATCHLIST_FILE = "data/thread_watchlist.json"
IGNORE_LIST_FILE = "data/thread_ignore_list.json"
TAG_IGNORE_FILE = "data/thread_tag_ignore_list.json"  # New file for ignored tags

# Default settings
DEFAULT_PURGE_INTERVAL = 2  # minutes

# Ensure data directory exists
os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)

class ModerationCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.watchlist = {}  # Guild ID -> Channel ID -> Settings
        self.ignore_list = {}  # Guild ID -> Thread ID -> Settings
        self.tag_ignore_list = {}  # Guild ID -> Tag Name -> Settings
        self.load_data()
        
        # Get purge interval from config or use default
        self.purge_interval = bot.config.get('thread_purge_interval_minutes', DEFAULT_PURGE_INTERVAL)
        logger.debug(f"Thread purge task will run every {self.purge_interval} minutes")
        
        # Start the purge task with the configured interval
        self.thread_purge_task.change_interval(minutes=self.purge_interval)
        self.thread_purge_task.start()

    def cog_unload(self):
        self.thread_purge_task.cancel()

    # ----- Data Management Functions -----

    def load_data(self):
        """Load watchlist and ignore list from disk"""
        # Load watchlist
        try:
            if os.path.exists(WATCHLIST_FILE):
                with open(WATCHLIST_FILE, 'r') as f:
                    self.watchlist = json.load(f)
            else:
                self.watchlist = {}
                self.save_watchlist()
        except Exception as e:
            logger.error(f"Error loading thread watchlist: {e}")
            self.watchlist = {}

        # Load ignore list
        try:
            if os.path.exists(IGNORE_LIST_FILE):
                with open(IGNORE_LIST_FILE, 'r') as f:
                    self.ignore_list = json.load(f)
            else:
                self.ignore_list = {}
                self.save_ignore_list()
        except Exception as e:
            logger.error(f"Error loading thread ignore list: {e}")
            self.ignore_list = {}
            
        # Load tag ignore list
        try:
            if os.path.exists(TAG_IGNORE_FILE):
                with open(TAG_IGNORE_FILE, 'r') as f:
                    self.tag_ignore_list = json.load(f)
            else:
                self.tag_ignore_list = {}
                self.save_tag_ignore_list()
        except Exception as e:
            logger.error(f"Error loading thread tag ignore list: {e}")
            self.tag_ignore_list = {}

    def save_watchlist(self):
        """Save watchlist to disk"""
        try:
            with open(WATCHLIST_FILE, 'w') as f:
                json.dump(self.watchlist, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving thread watchlist: {e}")

    def save_ignore_list(self):
        """Save ignore list to disk"""
        try:
            with open(IGNORE_LIST_FILE, 'w') as f:
                json.dump(self.ignore_list, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving thread ignore list: {e}")
            
    def save_tag_ignore_list(self):
        """Save tag ignore list to disk"""
        try:
            with open(TAG_IGNORE_FILE, 'w') as f:
                json.dump(self.tag_ignore_list, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving thread tag ignore list: {e}")

    # ----- Helper Functions -----

    def parse_time(self, time_str: str) -> Tuple[int, bool]:
        """
        Parse a time string like "2d", "3h", "30m" into seconds.
        Returns (seconds, success)
        """
        if not time_str:
            return 0, False

        pattern = re.compile(r'^(\d+)([dhm])$')
        match = pattern.match(time_str.lower())
        
        if not match:
            return 0, False
        
        value, unit = match.groups()
        value = int(value)
        
        if unit == 'd':
            return value * 24 * 60 * 60, True
        elif unit == 'h':
            return value * 60 * 60, True
        elif unit == 'm':
            return value * 60, True
        
        return 0, False

    def format_time(self, seconds: int) -> str:
        """Format seconds into a human-readable string"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            return f"{seconds // 3600} hours"
        else:
            return f"{seconds // 86400} days"

    def is_forum_channel(self, channel) -> bool:
        """Check if a channel is a forum channel"""
        return isinstance(channel, discord.ForumChannel)

    def is_thread_ignored(self, guild_id: int, thread_id: int) -> bool:
        """Check if a thread is in the ignore list"""
        guild_id_str = str(guild_id)
        thread_id_str = str(thread_id)
        
        return (guild_id_str in self.ignore_list and 
                thread_id_str in self.ignore_list[guild_id_str])
                
    def is_tag_ignored(self, guild_id: int, tag_name: str) -> bool:
        """Check if a tag is in the ignore list"""
        guild_id_str = str(guild_id)
        
        return (guild_id_str in self.tag_ignore_list and 
                tag_name in self.tag_ignore_list[guild_id_str])

    # ----- Commands -----

    @commands.command(name='watch_forum', help='Add a forum channel to the watchlist for automatic thread purging.\nArguments: <channel> <time_period>\nTime format examples: 3d (3 days), 12h (12 hours), 30m (30 minutes)\nExample: !watch_forum #help-forum 7d')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def watch_forum(self, ctx, channel: discord.TextChannel, inactivity: str):
        """Add a forum channel to the watchlist"""
        # Check if the user has manage_threads permission for the channel
        if not channel.permissions_for(ctx.author).manage_threads:
            await ctx.send(f"You need the Manage Threads permission in {channel.mention} to add it to the watchlist.")
            return
            
        # Check if the bot has required permissions
        has_perms, _, _ = check_target_permissions(
            channel, 
            ["manage_threads", "view_channel", "read_message_history"], 
            ctx
        )
        if not has_perms:
            return
            
        # Check if the channel is a forum channel
        if not self.is_forum_channel(channel):
            await ctx.send(f"Error: {channel.mention} is not a forum channel.")
            return
        
        # Parse the inactivity threshold
        seconds, success = self.parse_time(inactivity)
        if not success:
            await ctx.send("Error: Invalid time format. Use format like '7d', '24h', or '30m'.")
            return
        
        # Add to watchlist
        guild_id_str = str(ctx.guild.id)
        channel_id_str = str(channel.id)
        
        if guild_id_str not in self.watchlist:
            self.watchlist[guild_id_str] = {}
            
        self.watchlist[guild_id_str][channel_id_str] = {
            "max_inactivity_seconds": seconds,
            "max_inactivity_str": inactivity,
            "added_by": str(ctx.author.id),
            "added_at": datetime.datetime.now().isoformat()
        }
        
        self.save_watchlist()
        
        await create_embed_response(
            ctx=ctx,
            title="Forum Channel Added to Watchlist",
            description=f"Added {channel.mention} to the thread purge watchlist. Threads inactive for more than {self.format_time(seconds)} will be automatically purged.",
            color=discord.Color.green()
        )

    @commands.command(name='unwatch_forum', help='Remove a forum channel from the watchlist.\nArguments: <channel>\nExample: !unwatch_forum #help-forum')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def unwatch_forum(self, ctx, channel: discord.TextChannel):
        """Remove a forum channel from the watchlist"""
        # Check if the user has manage_threads permission for the channel
        if not channel.permissions_for(ctx.author).manage_threads:
            await ctx.send(f"You need the Manage Threads permission in {channel.mention} to remove it from the watchlist.")
            return
            
        # Check if the bot has required permissions
        has_perms, _, _ = check_target_permissions(channel, ["view_channel"], ctx)
        if not has_perms:
            return
            
        guild_id_str = str(ctx.guild.id)
        channel_id_str = str(channel.id)
        
        if (guild_id_str in self.watchlist and 
            channel_id_str in self.watchlist[guild_id_str]):
            
            del self.watchlist[guild_id_str][channel_id_str]
            
            # Clean up if the guild has no more watched channels
            if not self.watchlist[guild_id_str]:
                del self.watchlist[guild_id_str]
                
            self.save_watchlist()
            
            await create_embed_response(
                ctx=ctx,
                title="Forum Channel Removed from Watchlist",
                description=f"Removed {channel.mention} from the thread purge watchlist.",
                color=discord.Color.green()
            )
        else:
            await ctx.send(f"Error: {channel.mention} is not in the watchlist.")

    @commands.command(name='ignore_thread', help='Add a thread to the ignore list to prevent it from being purged.\nArguments: <thread>\nExample: !ignore_thread #important-thread')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def ignore_thread(self, ctx, thread: discord.Thread):
        """Add a thread to the ignore list"""
        # Check if the user has manage_threads permission for the thread's parent channel
        if hasattr(thread, "parent") and thread.parent and not thread.parent.permissions_for(ctx.author).manage_threads:
            await ctx.send(f"You need the Manage Threads permission in {thread.parent.mention} to manage threads.")
            return
            
        # Check if the bot has required permissions
        has_perms, _, _ = check_target_permissions(thread, ["manage_threads", "view_channel"], ctx)
        if not has_perms:
            return
            
        guild_id_str = str(ctx.guild.id)
        thread_id_str = str(thread.id)
        
        if guild_id_str not in self.ignore_list:
            self.ignore_list[guild_id_str] = {}
            
        # Check if already ignored
        if thread_id_str in self.ignore_list[guild_id_str]:
            await ctx.send(f"{thread.mention} is already in the ignore list.")
            return
            
        self.ignore_list[guild_id_str][thread_id_str] = {
            "added_by": str(ctx.author.id),
            "added_at": datetime.datetime.now().isoformat(),
            "thread_name": thread.name
        }
        
        self.save_ignore_list()
        
        await create_embed_response(
            ctx=ctx,
            title="Thread Added to Ignore List",
            description=f"Added {thread.mention} to the ignore list. This thread will not be purged automatically.",
            color=discord.Color.green()
        )

    @commands.command(name='unignore_thread', help='Remove a thread from the ignore list.\nArguments: <thread>\nExample: !unignore_thread #no-longer-important-thread')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def unignore_thread(self, ctx, thread: discord.Thread):
        """Remove a thread from the ignore list"""
        # Check if the user has manage_threads permission for the thread's parent channel
        if hasattr(thread, "parent") and thread.parent and not thread.parent.permissions_for(ctx.author).manage_threads:
            await ctx.send(f"You need the Manage Threads permission in {thread.parent.mention} to manage threads.")
            return
            
        # Check if the bot has required permissions
        has_perms, _, _ = check_target_permissions(thread, ["manage_threads", "view_channel"], ctx)
        if not has_perms:
            return
            
        guild_id_str = str(ctx.guild.id)
        thread_id_str = str(thread.id)
        
        if (guild_id_str in self.ignore_list and 
            thread_id_str in self.ignore_list[guild_id_str]):
            
            del self.ignore_list[guild_id_str][thread_id_str]
            
            # Clean up if the guild has no more ignored threads
            if not self.ignore_list[guild_id_str]:
                del self.ignore_list[guild_id_str]
                
            self.save_ignore_list()
            
            await create_embed_response(
                ctx=ctx,
                title="Thread Removed from Ignore List",
                description=f"Removed {thread.mention} from the ignore list. It may now be purged if inactive.",
                color=discord.Color.green()
            )
        else:
            await ctx.send(f"Error: {thread.mention} is not in the ignore list.")

    @commands.command(name='ignore_tag', help='Add a thread tag to the ignore list to prevent threads with that tag from being purged.\nArguments: <tag_name>\nExample: !ignore_tag important')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def ignore_tag(self, ctx, *, tag_name: str):
        """Add a thread tag to the ignore list"""
        if not tag_name:
            await ctx.send("Error: You must provide a tag name.")
            return
            
        # Clean the tag name (remove extra spaces, etc.)
        tag_name = tag_name.strip()
        
        guild_id_str = str(ctx.guild.id)
        
        if guild_id_str not in self.tag_ignore_list:
            self.tag_ignore_list[guild_id_str] = {}
            
        # Check if already ignored
        if tag_name in self.tag_ignore_list[guild_id_str]:
            await ctx.send(f"Tag '{tag_name}' is already in the ignore list.")
            return
            
        self.tag_ignore_list[guild_id_str][tag_name] = {
            "added_by": str(ctx.author.id),
            "added_at": datetime.datetime.now().isoformat()
        }
        
        self.save_tag_ignore_list()
        
        await create_embed_response(
            ctx=ctx,
            title="Tag Added to Ignore List",
            description=f"Added tag '{tag_name}' to the ignore list. Threads with this tag will not be purged automatically.",
            color=discord.Color.green()
        )

    @commands.command(name='unignore_tag', help='Remove a thread tag from the ignore list.\nArguments: <tag_name>\nExample: !unignore_tag important')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def unignore_tag(self, ctx, *, tag_name: str):
        """Remove a thread tag from the ignore list"""
        if not tag_name:
            await ctx.send("Error: You must provide a tag name.")
            return
            
        # Clean the tag name
        tag_name = tag_name.strip()
        
        guild_id_str = str(ctx.guild.id)
        
        if (guild_id_str in self.tag_ignore_list and 
            tag_name in self.tag_ignore_list[guild_id_str]):
            
            del self.tag_ignore_list[guild_id_str][tag_name]
            
            # Clean up if the guild has no more ignored tags
            if not self.tag_ignore_list[guild_id_str]:
                del self.tag_ignore_list[guild_id_str]
                
            self.save_tag_ignore_list()
            
            await create_embed_response(
                ctx=ctx,
                title="Tag Removed from Ignore List",
                description=f"Removed tag '{tag_name}' from the ignore list. Threads with this tag may now be purged if inactive.",
                color=discord.Color.green()
            )
        else:
            await ctx.send(f"Error: Tag '{tag_name}' is not in the ignore list.")

    @commands.command(name='list_thread_settings', help='List thread management settings for this server.\nArguments: [type] - Optional filter: "watched", "ignored", or "tags" (default: all)\nExample: !list_thread_settings or !list_thread_settings tags')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def list_thread_settings(self, ctx, setting_type: str = "all"):
        """List thread management settings for this server - both watched channels and ignored threads"""
        # Bot needs to be able to read channels to list them
        has_perms, _, _ = check_target_permissions(
            ctx.channel, 
            ["view_channel", "read_message_history"], 
            ctx
        )
        if not has_perms:
            return
            
        guild_id_str = str(ctx.guild.id)
        setting_type = setting_type.lower()
        
        # Validate setting type
        if setting_type not in ["all", "watched", "ignored", "tags"]:
            await ctx.send("Invalid setting type. Please use 'watched', 'ignored', 'tags', or omit for all settings.")
            return
        
        fields = []
        
        # Add watched channels section if requested
        if setting_type in ["all", "watched"]:
            watched_fields = self._get_watched_fields(ctx.guild, guild_id_str)
            fields.extend(watched_fields)
        
        # Add ignored threads section if requested
        if setting_type in ["all", "ignored"]:
            ignored_fields = self._get_ignored_fields(ctx.guild, guild_id_str)
            fields.extend(ignored_fields)
            
        # Add ignored tags section if requested
        if setting_type in ["all", "tags"]:
            tag_fields = self._get_ignored_tag_fields(ctx.guild, guild_id_str)
            fields.extend(tag_fields)
        
        # If no fields were added, there's nothing to show
        if not fields:
            sections = []
            if setting_type in ["all", "watched"]:
                sections.append("watched channels")
            if setting_type in ["all", "ignored"]:
                sections.append("ignored threads")
            if setting_type in ["all", "tags"]:
                sections.append("ignored tags")
                
            await ctx.send(f"No {' or '.join(sections)} found for this server.")
            return
        
        # Create title and description based on what's being shown
        if setting_type == "all":
            title = "Thread Management Settings"
            description = "Current thread management configuration for this server."
        elif setting_type == "watched":
            title = "Watched Forum Channels"
            description = "List of forum channels being watched for thread purging."
        elif setting_type == "ignored":
            title = "Ignored Threads"
            description = "List of threads that will not be automatically purged."
        else:  # tags
            title = "Ignored Tags"
            description = "List of thread tags that will prevent threads from being automatically purged."
        
        # Create and send the embed response
        await create_embed_response(
            ctx=ctx,
            title=title,
            description=description,
            fields=fields,
            color=discord.Color.blue()
        )
    
    def _get_watched_fields(self, guild, guild_id_str):
        """Helper method to get fields for watched channels"""
        fields = []
        
        # Add section header if we have watched channels
        if guild_id_str in self.watchlist and self.watchlist[guild_id_str]:
            fields.append({
                "name": "📋 WATCHED FORUM CHANNELS",
                "value": "Channels that have automatic thread purging enabled.",
                "inline": False
            })
            
            # Add each watched channel as a field
            for channel_id_str, settings in self.watchlist[guild_id_str].items():
                try:
                    channel = guild.get_channel(int(channel_id_str))
                    channel_name = channel.mention if channel else f"Unknown Channel ({channel_id_str})"
                    inactivity = settings.get("max_inactivity_str", "Unknown")
                    
                    fields.append({
                        "name": channel_name,
                        "value": f"**Inactivity Threshold:** {inactivity}\n" +
                                f"**Added:** {settings.get('added_at', 'Unknown').split('T')[0]}",
                        "inline": True
                    })
                except Exception as e:
                    logger.error(f"Error getting channel info: {e}")
        
        return fields
    
    def _get_ignored_fields(self, guild, guild_id_str):
        """Helper method to get fields for ignored threads"""
        fields = []
        
        # Add section header if we have ignored threads
        if guild_id_str in self.ignore_list and self.ignore_list[guild_id_str]:
            fields.append({
                "name": "🔕 IGNORED THREADS",
                "value": "Threads that will not be automatically purged.",
                "inline": False
            })
            
            # Add each ignored thread as a field
            for thread_id_str, settings in self.ignore_list[guild_id_str].items():
                try:
                    thread = guild.get_thread(int(thread_id_str))
                    thread_name = thread.mention if thread else settings.get("thread_name", f"Unknown Thread ({thread_id_str})")
                    
                    fields.append({
                        "name": thread_name,
                        "value": f"**Added:** {settings.get('added_at', 'Unknown').split('T')[0]}",
                        "inline": True
                    })
                except Exception as e:
                    logger.error(f"Error getting thread info: {e}")
        
        return fields
        
    def _get_ignored_tag_fields(self, guild, guild_id_str):
        """Helper method to get fields for ignored tags"""
        fields = []
        
        # Add section header if we have ignored tags
        if guild_id_str in self.tag_ignore_list and self.tag_ignore_list[guild_id_str]:
            fields.append({
                "name": "🏷️ IGNORED TAGS",
                "value": "Thread tags that will prevent threads from being automatically purged.",
                "inline": False
            })
            
            # Create a single field with all tags
            tag_list = []
            for tag_name, settings in self.tag_ignore_list[guild_id_str].items():
                added_date = settings.get('added_at', 'Unknown').split('T')[0]
                tag_list.append(f"`{tag_name}` (added: {added_date})")
            
            # Split into smaller chunks if we have many tags
            if tag_list:
                tag_chunks = [tag_list[i:i+10] for i in range(0, len(tag_list), 10)]
                for i, chunk in enumerate(tag_chunks):
                    fields.append({
                        "name": f"Ignored Tags {i+1}" if i > 0 else "Ignored Tags",
                        "value": "\n".join(chunk),
                        "inline": False
                    })
        
        return fields

    # ----- Background Task -----

    @tasks.loop(minutes=DEFAULT_PURGE_INTERVAL)  # Default interval that will be overridden
    async def thread_purge_task(self):
        """Background task that purges inactive threads in watched channels"""
        logger.info(f"Running thread purge task (interval: {self.purge_interval} minutes)")
        
        for guild_id_str, channels in self.watchlist.items():
            try:
                # Get guild object
                guild = self.bot.get_guild(int(guild_id_str))
                if not guild:
                    continue
                
                for channel_id_str, settings in channels.items():
                    try:
                        # Get channel object
                        channel = guild.get_channel(int(channel_id_str))
                        if not channel or not self.is_forum_channel(channel):
                            continue
                        
                        # Check if the bot has required permissions in this channel
                        has_perms, missing, _ = check_target_permissions(
                            channel, 
                            ["manage_threads", "view_channel", "read_message_history"]
                        )
                        if not has_perms:
                            missing_perms = ", ".join(missing)
                            logger.warning(f"Skipping thread purge in channel {channel.name} (ID: {channel_id_str}) - missing permissions: {missing_perms}")
                            continue
                        
                        # Get max inactivity threshold
                        max_inactivity = settings.get("max_inactivity_seconds")
                        if not max_inactivity:
                            continue
                        
                        # Process all threads in this channel
                        await self.purge_inactive_threads(guild, channel, max_inactivity)
                    except Exception as e:
                        logger.error(f"Error processing channel {channel_id_str}: {e}")
            except Exception as e:
                logger.error(f"Error processing guild {guild_id_str}: {e}")
    
    @thread_purge_task.before_loop
    async def before_thread_purge(self):
        await self.bot.wait_until_ready()
    
    async def purge_inactive_threads(self, guild, channel, max_inactivity):
        """Purge inactive threads in a specific channel"""
        now = datetime.datetime.now(datetime.timezone.utc)
        threads_purged = 0

        async def collect_threads(async_iterable):
            return [thread async for thread in async_iterable]
        
        # Gather active and archived threads concurrently
        active_threads_task = asyncio.create_task(collect_threads(channel.threads()))
        archived_threads_task = asyncio.create_task(collect_threads(channel.archived_threads()))
        active_threads, archived_threads = await asyncio.gather(active_threads_task, archived_threads_task)
        
        # Combine all threads into a single list
        all_threads = active_threads + archived_threads
        guild_id_str = str(guild.id)
        
        for thread in all_threads:
            try:
                # Skip if pinned
                if thread.flags.pinned:
                    continue
                
                # Skip if in ignore list
                if self.is_thread_ignored(guild.id, thread.id):
                    continue
                
                # Skip if thread has an ignored tag
                has_ignored_tag = False
                if hasattr(thread, "applied_tags") and thread.applied_tags:
                    for tag in thread.applied_tags:
                        if guild_id_str in self.tag_ignore_list and tag.name in self.tag_ignore_list[guild_id_str]:
                            logger.info(f"Skipping thread {thread.name} as it has ignored tag: {tag.name}")
                            has_ignored_tag = True
                            break
                
                if has_ignored_tag:
                    continue
                
                # Check if the bot has permission to delete this thread
                has_perms, missing, _ = check_target_permissions(thread, ["manage_threads"])
                if not has_perms:
                    logger.warning(f"Skipping thread {thread.name} (ID: {thread.id}) - missing permissions: {', '.join(missing)}")
                    continue
                
                # Check last activity
                last_message_time = thread.last_message_id
                if last_message_time:
                    # Get last message timestamp using snowflake ID
                    last_message_time = discord.utils.snowflake_time(last_message_time)
                else:
                    # If no messages, use creation time
                    last_message_time = thread.created_at
                
                # Calculate inactivity duration
                inactivity_duration = now - last_message_time
                inactivity_seconds = inactivity_duration.total_seconds()
                
                # Delete if inactive longer than threshold
                if inactivity_seconds > max_inactivity:
                    logger.info(f"Deleting inactive thread: {thread.name} (ID: {thread.id}) in channel {channel.name}")
                    await thread.delete()
                    threads_purged += 1
            except Exception as e:
                logger.error(f"Error processing thread {thread.id}: {e}")
        
        logger.info(f"Purged {threads_purged} threads from channel {channel.name} in {guild.name}")

async def setup(bot):
    await bot.add_cog(ModerationCommandsCog(bot))
