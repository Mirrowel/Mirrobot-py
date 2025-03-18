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
DEFAULT_PURGE_INTERVAL = 10  # minutes

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

        pattern = re.compile(r'^(\d+)([dhms])$')
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
        elif unit == 's':
            return value, True
        
        return 0, False

    def format_time(self, seconds: int) -> str:
        """Format seconds into a human-readable string"""
        seconds = int(seconds)  # Ensure seconds is an integer
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
        return " ".join(parts)

    def is_forum_channel(self, channel) -> bool:
        """Check if a channel is a forum channel"""
        return isinstance(channel, discord.ForumChannel)
    
    def can_have_threads(self, channel) -> bool:
        """Check if a channel can have threads"""
        return isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel))

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

    @commands.command(name='watch_forum', help='Add a channel to the watchlist for automatic thread purging.\nArguments: <channel> <time_period>\nTime format examples: 3d (3 days), 12h (12 hours), 30m (30 minutes)\nExample: !watch_forum #help-forum 7d')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def watch_forum(self, ctx, channel: discord.abc.GuildChannel, inactivity: str):
        """Add a channel to the watchlist"""
        
        # Check if the channel can have threads
        if not self.can_have_threads(channel):
            await ctx.send(f"Error: {channel.mention} cannot have threads. Only text channels, forum channels, and voice channels with threads can be watched.")
            return
        
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
            "added_at": datetime.datetime.now().isoformat(),
            "channel_type": channel.__class__.__name__
        }
        
        self.save_watchlist()
        
        await create_embed_response(
            ctx=ctx,
            title="Channel Added to Watchlist",
            description=f"Added {channel.mention} to the thread purge watchlist. Threads inactive for more than {self.format_time(seconds)} will be automatically purged.",
            color=discord.Color.green()
        )

    @commands.command(name='unwatch_forum', help='Remove a forum channel from the watchlist.\nArguments: <channel>\nExample: !unwatch_forum #help-forum')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def unwatch_forum(self, ctx, channel: discord.abc.GuildChannel):
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
        
        # Validate channels before processing - remove any that don't exist anymore
        channels_removed = await self.validate_watchlist_channels()
        if channels_removed > 0:
            logger.info(f"Removed {channels_removed} invalid or deleted channels from watchlist during validation")
        
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
    
    async def validate_watchlist_channels(self) -> int:
        """
        Validates all channels in the watchlist and removes entries for channels 
        that no longer exist or are invalid.
        
        Returns:
            int: Number of channels removed from the watchlist
        """
        removed_count = 0
        guilds_to_remove = []
        channels_to_remove = {}
        
        # First pass: collect all invalid channels
        for guild_id_str, channels in self.watchlist.items():
            try:
                guild = self.bot.get_guild(int(guild_id_str))
                
                # If guild doesn't exist anymore, mark all its channels for removal
                if not guild:
                    guilds_to_remove.append(guild_id_str)
                    removed_count += len(channels)
                    continue
                
                # Check each channel in this guild
                if guild_id_str not in channels_to_remove:
                    channels_to_remove[guild_id_str] = []
                    
                for channel_id_str, settings in channels.items():
                    try:
                        channel_id = int(channel_id_str)
                        channel = guild.get_channel(channel_id)
                        
                        # Mark for removal if:
                        # 1. Channel doesn't exist, or
                        # 2. Channel cannot have threads
                        if not channel or not self.can_have_threads(channel):
                            channels_to_remove[guild_id_str].append(channel_id_str)
                            removed_count += 1
                            logger.debug(f"Marking channel {channel_id_str} in guild {guild.name} for removal - " + 
                                       ("channel deleted" if not channel else "channel type cannot have threads"))
                    except Exception as e:
                        logger.error(f"Error validating channel {channel_id_str} in guild {guild_id_str}: {e}")
                        # Still mark it for removal if there was an error
                        channels_to_remove[guild_id_str].append(channel_id_str)
                        removed_count += 1
            except Exception as e:
                logger.error(f"Error validating guild {guild_id_str}: {e}")
                # If there's an error processing the guild, mark it for removal
                guilds_to_remove.append(guild_id_str)
                removed_count += len(channels)
        
        # Second pass: remove all collected invalid entries
        
        # Remove invalid guilds
        for guild_id_str in guilds_to_remove:
            if guild_id_str in self.watchlist:
                del self.watchlist[guild_id_str]
                logger.debug(f"Removed guild {guild_id_str} from watchlist - guild no longer exists")
        
        # Remove invalid channels
        for guild_id_str, channel_ids in channels_to_remove.items():
            if guild_id_str in self.watchlist:
                for channel_id_str in channel_ids:
                    if channel_id_str in self.watchlist[guild_id_str]:
                        del self.watchlist[guild_id_str][channel_id_str]
                        logger.debug(f"Removed channel {channel_id_str} from watchlist in guild {guild_id_str}")
                
                # If guild has no more channels, remove it too
                if not self.watchlist[guild_id_str]:
                    del self.watchlist[guild_id_str]
                    logger.debug(f"Removed empty guild {guild_id_str} from watchlist")
        
        # Save changes if we removed anything
        if removed_count > 0:
            self.save_watchlist()
        
        return removed_count

    # Same validation concept should be applied to ignored threads
    async def validate_ignored_threads(self) -> int:
        """
        Validates all threads in the ignore list and removes entries for threads
        that no longer exist.
        
        Returns:
            int: Number of threads removed from the ignore list
        """
        removed_count = 0
        guilds_to_remove = []
        threads_to_remove = {}
        
        # First pass: collect all invalid threads
        for guild_id_str, threads in self.ignore_list.items():
            try:
                guild = self.bot.get_guild(int(guild_id_str))
                
                # If guild doesn't exist anymore, mark all its threads for removal
                if not guild:
                    guilds_to_remove.append(guild_id_str)
                    removed_count += len(threads)
                    continue
                
                # Check each thread in this guild
                if guild_id_str not in threads_to_remove:
                    threads_to_remove[guild_id_str] = []
                    
                for thread_id_str, settings in threads.items():
                    try:
                        thread_id = int(thread_id_str)
                        thread = guild.get_thread(thread_id)
                        
                        # Mark for removal if thread doesn't exist
                        if not thread:
                            threads_to_remove[guild_id_str].append(thread_id_str)
                            removed_count += 1
                            thread_name = settings.get('thread_name', 'Unknown thread')
                            logger.debug(f"Marking thread {thread_name} ({thread_id_str}) in guild {guild.name} for removal - thread deleted")
                    except Exception as e:
                        logger.error(f"Error validating thread {thread_id_str} in guild {guild_id_str}: {e}")
                        # Still mark it for removal if there was an error
                        threads_to_remove[guild_id_str].append(thread_id_str)
                        removed_count += 1
            except Exception as e:
                logger.error(f"Error validating guild {guild_id_str} for ignored threads: {e}")
                guilds_to_remove.append(guild_id_str)
                removed_count += len(threads)
        
        # Second pass: remove all collected invalid entries
        
        # Remove invalid guilds
        for guild_id_str in guilds_to_remove:
            if guild_id_str in self.ignore_list:
                del self.ignore_list[guild_id_str]
                logger.debug(f"Removed guild {guild_id_str} from ignore list - guild no longer exists")
        
        # Remove invalid threads
        for guild_id_str, thread_ids in threads_to_remove.items():
            if guild_id_str in self.ignore_list:
                for thread_id_str in thread_ids:
                    if thread_id_str in self.ignore_list[guild_id_str]:
                        del self.ignore_list[guild_id_str][thread_id_str]
                        logger.debug(f"Removed thread {thread_id_str} from ignore list in guild {guild_id_str}")
                
                # If guild has no more threads, remove it too
                if not self.ignore_list[guild_id_str]:
                    del self.ignore_list[guild_id_str]
                    logger.debug(f"Removed empty guild {guild_id_str} from ignore list")
        
        # Save changes if we removed anything
        if removed_count > 0:
            self.save_ignore_list()
        
        return removed_count

    # Make our thread purge task call both validation methods
    @thread_purge_task.before_loop
    async def before_thread_purge(self):
        await self.bot.wait_until_ready()
        # Validate channels and threads when the bot starts up
        channels_removed = await self.validate_watchlist_channels()
        threads_removed = await self.validate_ignored_threads()
        if channels_removed > 0 or threads_removed > 0:
            logger.info(f"Initial validation: Removed {channels_removed} invalid channels and {threads_removed} invalid threads")
    
    async def purge_inactive_threads(self, guild, channel, max_inactivity):
        """Purge inactive threads in a specific channel"""
        now = datetime.datetime.now(datetime.timezone.utc)
        threads_purged = 0

        async def collect_threads(async_iterable):
            return [thread async for thread in async_iterable]
        
        # Get threads based on channel type
        all_threads = []
        
        # Get active threads
        if hasattr(channel, "threads"):
            all_threads.extend(channel.threads)
        try:    
            # Get archived threads if applicable
            if hasattr(channel, "archived_threads"):
                archived_threads = []
                async for thread in channel.archived_threads():
                    archived_threads.append(thread)
                all_threads.extend(archived_threads)
        except Exception as e:
            logger.error(f"Error collecting archived threads from channel {channel.id}: {e}")
            return
        
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
                    logger.debug(f"Deleting inactive thread: {thread.name} (ID: {thread.id}) in channel {channel.name}. Inactive for {self.format_time(inactivity_seconds)}, threshold: {self.format_time(max_inactivity)}")   
                    await thread.delete()
                    threads_purged += 1
            except Exception as e:
                logger.error(f"Error processing thread {thread.id}: {e}")
        if threads_purged > 0:
            logger.debug(f"Purged {threads_purged} threads from channel {channel.name} in {guild.name}")

    @commands.command(name='purge_threads', help='Manually purge inactive threads from a channel.\nArguments: <channel> <time_period>\nTime format examples: 3d (3 days), 12h (12 hours), 30m (30 minutes)\nExample: !purge_threads #help-forum 7d')
    @has_command_permission("manage_channels")
    @command_category("Moderation")
    async def purge_threads(self, ctx, channel: discord.abc.GuildChannel, inactivity: str):
        """Manually purge inactive threads from a channel"""
        
        # Check if the channel can have threads
        if not self.can_have_threads(channel):
            await ctx.send(f"Error: {channel.mention} cannot have threads. Only text channels, forum channels, and voice channels with threads can be purged.")
            return
        
        # Check if the user has manage_threads permission for the channel
        if not channel.permissions_for(ctx.author).manage_threads:
            await ctx.send(f"You need the Manage Threads permission in {channel.mention} to purge its threads.")
            return
            
        # Check if the bot has required permissions
        has_perms, missing_perms, _ = check_target_permissions(
            channel, 
            ["manage_threads", "view_channel", "read_message_history"], 
            ctx
        )
        if not has_perms:
            return
        
        # Parse the inactivity threshold
        seconds, success = self.parse_time(inactivity)
        if not success:
            await ctx.send("Error: Invalid time format. Use format like '7d', '24h', or '30m'.")
            return
        
        # Send an initial message
        initial_message = await ctx.send(f"🔍 Scanning {channel.mention} for inactive threads...")
        
        # Run the purge and get purged thread information
        purged_threads = await self.manual_purge_inactive_threads(ctx.guild, channel, seconds)
        
        if not purged_threads:
            await initial_message.edit(content=f"No inactive threads found in {channel.mention} that have been inactive for more than {self.format_time(seconds)}.")
            return
        
        # Create fields for the embed
        fields = []
        thread_list = []

        for i, thread in enumerate(purged_threads):
            thread_name, inactive_time, inactive_seconds = thread
            thread_list.append(f"• **{thread_name}** - Inactive for {inactive_time}")
            
        fields.append({
            "name": "Purged Threads",
            "value": "\n".join(thread_list),
            "inline": False
        })
        
        # Create and send the embed
        await create_embed_response(
            ctx=ctx,
            title=f"Thread Purge Results",
            description=f"Purged **{len(purged_threads)}** inactive threads from {channel.mention} that were inactive for more than {self.format_time(seconds)}.",
            fields=fields,
            color=discord.Color.green(),
            footer_text=f"Requested by {ctx.author.display_name}",
            field_unbroken=True
        )
        
        # Delete the initial message
        try:
            await initial_message.delete()
        except:
            pass

    async def manual_purge_inactive_threads(self, guild, channel, max_inactivity):
        """Purge inactive threads in a specific channel and return info about purged threads"""
        now = datetime.datetime.now(datetime.timezone.utc)
        purged_threads = []  # Will store tuples of (thread_name, inactive_time_formatted, inactive_seconds)
        
        # Get threads based on channel type
        all_threads = []
        
        # Get active threads
        if hasattr(channel, "threads"):
            all_threads.extend(channel.threads)
        try:    
            # Get archived threads if applicable
            if hasattr(channel, "archived_threads"):
                archived_threads = []
                async for thread in channel.archived_threads():
                    archived_threads.append(thread)
                all_threads.extend(archived_threads)
        except Exception as e:
            logger.error(f"Error collecting archived threads from channel {channel.id}: {e}")
            return purged_threads
        
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
                            #logger.debug(f"Skipping thread {thread.name} as it has ignored tag: {tag.name}")
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
                    thread_name = thread.name
                    inactive_time = self.format_time(int(inactivity_seconds))
                    
                    logger.debug(f"Deleting inactive thread: {thread_name} (ID: {thread.id}) in channel {channel.name}. Inactive for {inactive_time}")
                    
                    # Store information before deleting
                    purged_threads.append((thread_name, inactive_time, inactivity_seconds))
                    
                    # Delete the thread
                    await thread.delete()
            except Exception as e:
                logger.error(f"Error processing thread {thread.id}: {e}")
                
        # Sort purged threads by inactivity time (most inactive first)
        purged_threads.sort(key=lambda x: x[2], reverse=True)
        
        if purged_threads:
            logger.info(f"Manually purged {len(purged_threads)} threads from channel {channel.name} in {guild.name}")
            
        return purged_threads

async def setup(bot):
    await bot.add_cog(ModerationCommandsCog(bot))
