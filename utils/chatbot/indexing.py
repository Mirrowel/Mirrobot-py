"""
Manages user, channel, and pinned message indexing with in-memory caching,
asynchronous file I/O, and concurrency control to prevent race conditions.
"""

import os
import re
import time
import asyncio
import dataclasses
from dataclasses import asdict, fields
from typing import Any, Dict, List, Set, Union
from collections import defaultdict

import discord
from utils.chatbot.models import ChannelIndexEntry, PinnedMessage, UserIndexEntry
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

DATA_FORMAT_VERSION = 1
USER_INDEX_DIR = "data/user_index"
CHANNEL_INDEX_DIR = "data/channel_index"
PINNED_MESSAGES_DIR = "data/pins"
SAVE_INTERVAL_SECONDS = 30  # Save dirty indexes every 30 seconds
CACHE_INACTIVITY_THRESHOLD_SECONDS = 900  # 15 minutes
CACHE_CLEANUP_INTERVAL_SECONDS = 150  # 2.5 minutes


class IndexingManager:
    """
    A stateful service that manages user, channel, and pinned message indexing.
    It uses in-memory caches, asynchronous locks, and a periodic saving mechanism
    to ensure high performance and data integrity.
    """

    def __init__(self, storage_manager: JsonStorageManager, bot_user_id: int = None):
        self.storage_manager = storage_manager
        self.bot_user_id = bot_user_id

        self._user_indexes: Dict[int, Dict[int, UserIndexEntry]] = {}
        self._channel_indexes: Dict[int, Dict[int, ChannelIndexEntry]] = {}
        self._last_access_time: Dict[int, float] = {}
        self._guild_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._dirty_guilds: Set[int] = set()
        self._save_task: asyncio.Task = None
        self._cleanup_task: asyncio.Task = None

    def set_bot_user_id(self, bot_id: int):
        self.bot_user_id = bot_id

    async def start(self):
        """Starts the periodic save and cache cleanup background tasks."""
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._periodic_save())
            logger.info("IndexingManager background save task started.")
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cache_cleanup())
            logger.info("IndexingManager background cache cleanup task started.")

    async def shutdown(self):
        """Stops background tasks and performs a final save."""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                logger.info("IndexingManager background save task cancelled.")
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.info("IndexingManager background cache cleanup task cancelled.")

        logger.info("Performing final save of all dirty indexes...")
        await self._save_all_dirty_indexes()
        logger.info("Final save complete.")

    async def _periodic_save(self):
        while True:
            try:
                await asyncio.sleep(SAVE_INTERVAL_SECONDS)
                await self._save_all_dirty_indexes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic save task: {e}", exc_info=True)

    async def _periodic_cache_cleanup(self):
        while True:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL_SECONDS)
                await self._evict_inactive_guilds()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cache cleanup task: {e}", exc_info=True)

    async def _evict_inactive_guilds(self):
        now = time.time()
        inactive_threshold = now - CACHE_INACTIVITY_THRESHOLD_SECONDS
        
        # Iterate over a copy of keys to allow modification during iteration
        guild_ids = list(self._user_indexes.keys())
        if not guild_ids:
            return

        logger.debug(f"Running cache cleanup. Checking {len(guild_ids)} guilds.")
        evicted_count = 0

        for guild_id in guild_ids:
            last_access = self._last_access_time.get(guild_id)
            if last_access and last_access < inactive_threshold:
                logger.info(f"Guild {guild_id} is inactive. Evicting from cache.")
                async with self._guild_locks[guild_id]:
                    try:
                        # If guild is dirty, save it before evicting to prevent data loss
                        if guild_id in self._dirty_guilds:
                            logger.debug(f"Guild {guild_id} is dirty. Saving before eviction.")
                            if guild_id in self._user_indexes:
                                await self._save_user_index_to_disk(guild_id, self._user_indexes[guild_id])
                            if guild_id in self._channel_indexes:
                                await self._save_channel_index_to_disk(guild_id, self._channel_indexes[guild_id])
                            self._dirty_guilds.remove(guild_id)

                        # Evict from all caches
                        self._user_indexes.pop(guild_id, None)
                        self._channel_indexes.pop(guild_id, None)
                        self._last_access_time.pop(guild_id, None)
                        evicted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to evict guild {guild_id}: {e}", exc_info=True)
        
        if evicted_count > 0:
            logger.info(f"Evicted {evicted_count} inactive guilds from the cache.")

    async def _save_all_dirty_indexes(self):
        if not self._dirty_guilds:
            return

        dirty_guilds_copy = list(self._dirty_guilds)
        logger.debug(f"Saving dirty indexes for {len(dirty_guilds_copy)} guilds: {dirty_guilds_copy}")
        
        for guild_id in dirty_guilds_copy:
            # Do not acquire lock here, as called methods will do it.
            # This check is crucial because an eviction might happen between the copy and here.
            if guild_id not in self._user_indexes and guild_id not in self._channel_indexes:
                logger.warning(f"Skipping save for guild {guild_id}; it was evicted from cache.")
                self._dirty_guilds.discard(guild_id)
                continue

            async with self._guild_locks[guild_id]:
                try:
                    # Re-check dirty status inside lock
                    if guild_id not in self._dirty_guilds:
                        continue
                    if guild_id in self._user_indexes:
                        await self._save_user_index_to_disk(guild_id, self._user_indexes[guild_id])
                    if guild_id in self._channel_indexes:
                        await self._save_channel_index_to_disk(guild_id, self._channel_indexes[guild_id])
                    
                    # Only remove from dirty set if save was successful
                    self._dirty_guilds.discard(guild_id)
                except Exception as e:
                    logger.error(f"Failed to save index for guild {guild_id} during periodic save: {e}", exc_info=True)

    def _touch_guild_cache(self, guild_id: int):
        """Updates the last access time for a guild's cache."""
        self._last_access_time[guild_id] = time.time()
        logger.debug(f"Cache touched for guild {guild_id}")

    async def _initialize_guild_cache(self, guild_id: int):
        """Loads indexes for a guild into the cache if not already present."""
        if guild_id not in self._user_indexes or guild_id not in self._channel_indexes:
            if guild_id not in self._user_indexes:
                self._user_indexes[guild_id] = await self._load_user_index_from_disk(guild_id)
            if guild_id not in self._channel_indexes:
                self._channel_indexes[guild_id] = await self._load_channel_index_from_disk(guild_id)
        self._touch_guild_cache(guild_id)


    # --- User Indexing ---
    def get_user_index_file_path(self, guild_id: int) -> str:
        return os.path.join(USER_INDEX_DIR, f"guild_{guild_id}_users.json")

    async def _load_user_index_from_disk(self, guild_id: int) -> Dict[int, UserIndexEntry]:
        file_path = self.get_user_index_file_path(guild_id)
        try:
            data = await asyncio.to_thread(self.storage_manager.read, file_path)
            if not data: return {}

            version = data.get("version", 0)
            if version < DATA_FORMAT_VERSION:
                logger.debug(f"Loading old user index data format (version {version}) for guild {guild_id}. It will be updated on next save.")

            user_index = {}
            for user_id_str, user_data in data.get("users", {}).items():
                user_id = int(user_id_str)
                user_entry_data = {k: user_data.get(k) for k in [f.name for f in fields(UserIndexEntry)]}
                entry = UserIndexEntry(**{k: v for k, v in user_entry_data.items() if v is not None})
                user_index[user_id] = entry
            logger.debug(f"Loaded {len(user_index)} users from disk for guild {guild_id}")
            return user_index
        except Exception as e:
            logger.error(f"Error loading user index from disk for guild {guild_id}: {e}", exc_info=True)
            return {}

    async def _save_user_index_to_disk(self, guild_id: int, user_index: Dict[int, UserIndexEntry]):
        file_path = self.get_user_index_file_path(guild_id)
        data = {
            "version": DATA_FORMAT_VERSION,
            "users": {str(uid): asdict(u) for uid, u in user_index.items()},
            "last_updated": time.time(),
            "guild_id": guild_id
        }
        await asyncio.to_thread(self.storage_manager.write, file_path, data)
        logger.debug(f"Saved {len(user_index)} users to disk for guild {guild_id}")

    async def load_user_index(self, guild_id: int) -> Dict[int, UserIndexEntry]:
        """Loads user index for a guild from the in-memory cache."""
        async with self._guild_locks[guild_id]:
            await self._initialize_guild_cache(guild_id)
            return self._user_indexes.get(guild_id, {})

    async def update_users_bulk(self, guild_id: int, users: List[Union[discord.Member, discord.User]], is_message_author: bool = False):
        """Atomically updates multiple users in the index for a guild."""
        if not users:
            return

        async with self._guild_locks[guild_id]:
            await self._initialize_guild_cache(guild_id)
            user_index = self._user_indexes[guild_id]
            current_time = time.time()
            
            for user in users:
                user_data = self.extract_user_data(user, guild_id)
                user_id = user.id
                
                if user_id in user_index:
                    entry = user_index[user_id]
                    entry.last_seen = current_time
                    entry.username = user_data.get("username", entry.username)
                    entry.display_name = user_data.get("display_name", entry.display_name)
                    if user_data.get("status"): entry.status = user_data["status"]
                    if user_data.get("avatar_url"): entry.avatar_url = user_data["avatar_url"]
                    if user_data.get("roles"): entry.roles = user_data["roles"]
                    if is_message_author:
                        entry.message_count += 1
                else:
                    user_index[user_id] = UserIndexEntry(
                        user_id=user_id,
                        username=user_data.get("username", "Unknown"),
                        display_name=user_data.get("display_name", "Unknown"),
                        guild_id=guild_id,
                        guild_name=user_data.get("guild_name", "Unknown"),
                        roles=user_data.get("roles", []),
                        avatar_url=user_data.get("avatar_url"),
                        status=user_data.get("status"),
                        first_seen=current_time,
                        last_seen=current_time,
                        message_count=1 if is_message_author else 0,
                        is_bot=user_data.get("is_bot", False)
                    )
            
            self._dirty_guilds.add(guild_id)
        logger.debug(f"Bulk updated {len(users)} users in memory for guild {guild_id}.")

    # --- Channel Indexing ---
    def get_channel_index_file_path(self, guild_id: int) -> str:
        return os.path.join(CHANNEL_INDEX_DIR, f"guild_{guild_id}_channels.json")

    async def _load_channel_index_from_disk(self, guild_id: int) -> Dict[int, ChannelIndexEntry]:
        file_path = self.get_channel_index_file_path(guild_id)
        try:
            data = await asyncio.to_thread(self.storage_manager.read, file_path)
            if not data: return {}

            version = data.get("version", 0)
            if version < DATA_FORMAT_VERSION:
                logger.debug(f"Loading old channel index data format (version {version}) for guild {guild_id}. It will be updated on next save.")
            
            channel_index = {}
            for ch_id_str, ch_data in data.get("channels", {}).items():
                ch_id = int(ch_id_str)
                ch_entry_data = {k: ch_data.get(k) for k in [f.name for f in fields(ChannelIndexEntry)]}
                entry = ChannelIndexEntry(**{k: v for k, v in ch_entry_data.items() if v is not None})
                channel_index[ch_id] = entry
            logger.debug(f"Loaded {len(channel_index)} channels from disk for guild {guild_id}")
            return channel_index
        except Exception as e:
            logger.error(f"Error loading channel index from disk for guild {guild_id}: {e}", exc_info=True)
            return {}

    async def _save_channel_index_to_disk(self, guild_id: int, channel_index: Dict[int, ChannelIndexEntry]):
        file_path = self.get_channel_index_file_path(guild_id)
        data = {
            "version": DATA_FORMAT_VERSION,
            "channels": {str(cid): asdict(c) for cid, c in channel_index.items()},
            "last_updated": time.time(),
            "guild_id": guild_id
        }
        await asyncio.to_thread(self.storage_manager.write, file_path, data)
        logger.debug(f"Saved {len(channel_index)} channels to disk for guild {guild_id}")

    async def load_channel_index(self, guild_id: int) -> Dict[int, ChannelIndexEntry]:
        """Loads channel index for a guild from the in-memory cache."""
        async with self._guild_locks[guild_id]:
            await self._initialize_guild_cache(guild_id)
            return self._channel_indexes.get(guild_id, {})

    async def update_channel_index(self, channel: Union[discord.TextChannel, discord.Thread]):
        """Atomically updates a channel in the index."""
        guild_id = channel.guild.id
        async with self._guild_locks[guild_id]:
            await self._initialize_guild_cache(guild_id)
            channel_index = self._channel_indexes[guild_id]
            
            new_entry = self.index_channel(channel)
            if channel.id in channel_index:
                new_entry.message_count = channel_index[channel.id].message_count
            
            channel_index[channel.id] = new_entry
            self._dirty_guilds.add(guild_id)
        logger.debug(f"Updated channel {channel.name} in memory for guild {guild_id}.")

    # --- Pinned Messages & Helpers (largely unchanged, but made async where needed) ---
    def get_pinned_messages_file_path(self, guild_id: int, channel_id: int) -> str:
        return os.path.join(PINNED_MESSAGES_DIR, f"guild_{guild_id}_channel_{channel_id}_pins.json")

    async def index_pinned_messages(self, channel: discord.abc.Messageable, is_valid_message_func, process_message_func) -> int:
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return 0

        guild_id = channel.guild.id
        self._touch_guild_cache(guild_id)
        file_path = self.get_pinned_messages_file_path(guild_id, channel.id)
        current_pins = []
        indexed_count = 0

        try:
            pins = await channel.pins()
            logger.debug(f"Fetched {len(pins)} pinned messages from #{channel.name}")

            users_to_update = []
            for message in pins:
                if message.author.bot and message.author.id != self.bot_user_id:
                    continue
                
                cleaned_content, image_urls, embed_urls = process_message_func(message)
                
                from utils.chatbot.models import ConversationMessage
                temp_conv_message = ConversationMessage(
                    user_id=message.author.id, username=message.author.display_name,
                    content=cleaned_content, timestamp=message.created_at.timestamp(),
                    message_id=message.id, is_bot_response=message.author.bot,
                    is_self_bot_response=(message.author.id == self.bot_user_id),
                    attachment_urls=image_urls, embed_urls=embed_urls
                )
                is_valid, _ = is_valid_message_func(temp_conv_message)

                if is_valid:
                    users_to_update.append(message.author)
                    pin_entry = PinnedMessage(
                        user_id=message.author.id, username=message.author.display_name,
                        content=cleaned_content, timestamp=message.created_at.timestamp(),
                        message_id=message.id, attachment_urls=image_urls, embed_urls=embed_urls
                    )
                    current_pins.append(pin_entry)
                    indexed_count += 1

            if users_to_update:
                await self.update_users_bulk(guild_id, list(set(users_to_update)))

            data_to_save = {
                "pins": [asdict(pin) for pin in current_pins],
                "last_indexed": time.time(),
                "guild_id": guild_id, "channel_id": channel.id
            }
            await asyncio.to_thread(self.storage_manager.write, file_path, data_to_save)
            logger.info(f"Indexed {indexed_count} pinned messages for #{channel.name}")
            return indexed_count
        except discord.errors.Forbidden:
            logger.warning(f"Missing permissions to read pins in channel {channel.name}")
            return 0
        except Exception as e:
            logger.error(f"Error indexing pinned messages for channel {channel.id}: {e}", exc_info=True)
            return 0

    def load_pinned_messages(self, guild_id: int, channel_id: int) -> List[PinnedMessage]:
        """This remains synchronous as it's a simple file read, no cache needed."""
        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        data = self.storage_manager.read(file_path)
        return [PinnedMessage(**msg) for msg in data.get("pins", [])]

    async def clear_pinned_messages(self, guild_id: int, channel_id: int):
        """Asynchronously clear pinned messages for a specific channel."""
        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        if os.path.exists(file_path):
            await asyncio.to_thread(os.remove, file_path)
            logger.debug(f"Cleared pinned messages file for channel {channel_id}")

    # --- Maintenance and Stats ---
    async def cleanup_stale_users(self, guild_id: int, cleanup_hours: int = 168) -> int:
        """Asynchronously remove users from index if they haven't been seen recently."""
        cutoff_time = time.time() - (cleanup_hours * 3600)
        removed_count = 0
        async with self._guild_locks[guild_id]:
            await self._initialize_guild_cache(guild_id)
            user_index = self._user_indexes.get(guild_id, {})
            if not user_index:
                return 0
            self._touch_guild_cache(guild_id)
            
            users_to_remove = [uid for uid, user in user_index.items() if user.last_seen < cutoff_time]
            
            if not users_to_remove:
                return 0
                
            for user_id in users_to_remove:
                del user_index[user_id]
            
            removed_count = len(users_to_remove)
            self._dirty_guilds.add(guild_id)

        logger.info(f"Cleaned up {removed_count} stale users from memory for guild {guild_id}. Changes will be saved.")
        return removed_count

    async def cleanup_all_stale_users(self, bot_guilds, cleanup_hours: int = 168) -> int:
        """Clean up stale users across all guilds."""
        total_cleaned = 0
        for guild in bot_guilds:
            total_cleaned += await self.cleanup_stale_users(guild.id, cleanup_hours)
        
        if total_cleaned > 0:
            logger.info(f"Cleaned up a total of {total_cleaned} stale users across all guilds.")
            return total_cleaned
    
        async def remove_guild_indexes(self, guild_id: int):
            """Completely remove all index files and caches for a guild."""
            async with self._guild_locks[guild_id]:
                # Remove from cache
                self._user_indexes.pop(guild_id, None)
                self._channel_indexes.pop(guild_id, None)
                self._last_access_time.pop(guild_id, None)
                self._dirty_guilds.discard(guild_id)
    
                # Delete files from disk
                user_file = self.get_user_index_file_path(guild_id)
                channel_file = self.get_channel_index_file_path(guild_id)
                
                if os.path.exists(user_file):
                    await asyncio.to_thread(os.remove, user_file)
                if os.path.exists(channel_file):
                    await asyncio.to_thread(os.remove, channel_file)
                
                # Also remove pinned messages for all channels in that guild
                pins_dir = PINNED_MESSAGES_DIR
                if os.path.exists(pins_dir):
                    for filename in os.listdir(pins_dir):
                        if filename.startswith(f"guild_{guild_id}_"):
                            await asyncio.to_thread(os.remove, os.path.join(pins_dir, filename))
    
            logger.info(f"Removed all index data for guild {guild_id}.")
    
        async def get_indexing_stats(self, guild_id: int) -> Dict[str, int]:
            """Get statistics about current indexing for a guild from the in-memory cache."""
            async with self._guild_locks[guild_id]:
                await self._initialize_guild_cache(guild_id)
                user_index = self._user_indexes.get(guild_id, {})
                channel_index = self._channel_indexes.get(guild_id, {})
                return {
                    "users_indexed": len(user_index),
                    "channels_indexed": len(channel_index),
                    "total_user_messages": sum(user.message_count for user in user_index.values())
                }

    # --- Helper methods (unchanged) ---
    def extract_user_data(self, user, guild_id: int = None) -> Dict[str, Any]:
        try:
            user_data = {
                "user_id": user.id,
                "username": user.name,
                "display_name": getattr(user, "display_name", user.name),
                "is_bot": getattr(user, "bot", False),
                "roles": [role.name for role in getattr(user, 'roles', []) if role.name != "@everyone"],
                "status": str(getattr(user, 'status', 'offline')),
                "avatar_url": str(user.display_avatar.url) if hasattr(user, 'display_avatar') else None,
                "guild_id": getattr(user, 'guild', None) and user.guild.id or guild_id,
                "guild_name": getattr(user, 'guild', None) and user.guild.name or "Unknown"
            }
            return user_data
        except Exception as e:
            logger.error(f"Error extracting user data for {getattr(user, 'id', 'Unknown')}: {e}", exc_info=True)
            return {"user_id": getattr(user, "id", 0), "username": "Unknown", "display_name": "Unknown"}

    def index_channel(self, channel) -> ChannelIndexEntry:
        return ChannelIndexEntry(
            channel_id=channel.id,
            guild_id=channel.guild.id,
            channel_name=channel.name,
            channel_type=str(channel.type).replace('channel_type.', ''),
            topic=getattr(channel, 'topic', None) or (channel.name if isinstance(channel, discord.Thread) else None),
            category_name=getattr(channel.category, 'name', None) if hasattr(channel, 'category') else None,
            last_indexed=time.time(),
            message_count=0,
            guild_name=channel.guild.name,
            guild_description=channel.guild.description
        )
