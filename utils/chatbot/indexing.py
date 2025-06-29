"""
Manages user, channel, and pinned message indexing.
"""

import os
import re
import time
import dataclasses
from dataclasses import asdict, fields
from typing import Any, Dict, List

import discord
from utils.chatbot.models import ChannelIndexEntry, PinnedMessage, UserIndexEntry
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

USER_INDEX_DIR = "data/user_index"
CHANNEL_INDEX_DIR = "data/channel_index"
PINNED_MESSAGES_DIR = "data/pins"

class IndexingManager:
    """Manages user, channel, and pinned message indexing."""

    def __init__(self, storage_manager: JsonStorageManager, bot_user_id: int = None):
        self.storage_manager = storage_manager
        self.bot_user_id = bot_user_id

    def set_bot_user_id(self, bot_id: int):
        self.bot_user_id = bot_id

    # User Indexing
    def get_user_index_file_path(self, guild_id: int) -> str:
        return os.path.join(USER_INDEX_DIR, f"guild_{guild_id}_users.json")

    def load_user_index(self, guild_id: int) -> Dict[int, UserIndexEntry]:
        """Load user index for a specific guild"""
        file_path = self.get_user_index_file_path(guild_id)
        try:
            data = self.storage_manager.read(file_path)
            if not data:
                return {}
            
            user_index = {}
            for user_id_str, user_data in data.get("users", {}).items():
                user_id = int(user_id_str)
                # Instantiate UserIndexEntry, handling potential missing fields with defaults
                user_entry_data = {k: user_data.get(k, None) for k in [f.name for f in fields(UserIndexEntry)]}
                entry = UserIndexEntry(**user_entry_data)
                # Fill in defaults for any missing fields from old data structure
                for field in fields(UserIndexEntry):
                    if getattr(entry, field.name) is None and field.default is not dataclasses.MISSING:
                        setattr(entry, field.name, field.default)
                user_index[user_id] = entry
            
            #logger.debug(f"Loaded {len(user_index)} users from index for guild {guild_id}")
            return user_index
        except Exception as e:
            logger.error(f"Error loading user index for guild {guild_id}: {e}", exc_info=True)
            return {}

    def save_user_index(self, guild_id: int, user_index: Dict[int, UserIndexEntry]) -> bool:
        """Save user index for a specific guild"""
        file_path = self.get_user_index_file_path(guild_id)
        try:
            data = {
                "users": {str(uid): asdict(u) for uid, u in user_index.items()},
                "last_updated": time.time(),
                "guild_id": guild_id
            }
            #logger.debug(f"Saved {len(user_index)} users to index for guild {guild_id}")
            return self.storage_manager.write(file_path, data)
        except Exception as e:
            logger.error(f"Error saving user index for guild {guild_id}: {e}", exc_info=True)
            return False

    def extract_user_data(self, user, guild_id: int = None) -> Dict[str, Any]:
        """Extract all available user data from a Discord user/member object
        
        This function extracts all available user data from different types of Discord objects
        (Member, User, Message.author, etc.) and returns a consistent dictionary of values.
        
        Args:
            user: Discord user object (Member, User, etc.)
            guild_id: Optional guild ID if not available from the user object
            
        Returns:
            Dictionary of extracted user data
        """
        try:
            current_time = time.time()
            user_data = {}
            
            # Basic user info that should be available on all user objects
            user_data["user_id"] = user.id
            user_data["username"] = user.name # This is the global Discord username
            user_data["display_name"] = getattr(user, "display_name", user.name) # This is nickname or global username
            user_data["is_bot"] = getattr(user, "bot", False)
            
            # Get avatar URL if available
            if hasattr(user, 'display_avatar') and user.display_avatar:
                user_data["avatar_url"] = str(user.display_avatar.url)
            elif hasattr(user, 'avatar') and user.avatar:
                user_data["avatar_url"] = str(user.avatar.url)
                
            # Get status if available
            if hasattr(user, 'status'):
                user_data["status"] = str(user.status)
                
            # Get guild information if available
            if hasattr(user, 'guild') and user.guild:
                user_data["guild_id"] = user.guild.id
                user_data["guild_name"] = user.guild.name
            elif guild_id:
                user_data["guild_id"] = guild_id
                
            # Get roles if available (for Member objects)
            if hasattr(user, 'roles'):
                user_data["roles"] = [role.name for role in user.roles if role.name != "@everyone"]                            
            else:
                user_data["roles"] = [] # Ensure roles is always a list
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error extracting user data for {getattr(user, 'id', 'Unknown')}: {e}", exc_info=True)
            # Return minimum required data to prevent errors
            return {
                "user_id": getattr(user, "id", 0),
                "username": getattr(user, "name", "Unknown"),
                "display_name": getattr(user, "display_name", "Unknown"),
                "is_bot": getattr(user, "bot", False),
                "guild_id": guild_id or 0,
                "guild_name": "Unknown",
                "roles": [],
                "avatar_url": None,
                "status": None
            }

    def update_user_index(self, guild_id: int, user, is_message_author: bool = False) -> bool:
        """Update user index with information from any Discord user object"""
        try:
            user_index = self.load_user_index(guild_id)
            user_id = user.id
            current_time = time.time()
            user_data = self.extract_user_data(user, guild_id)
            
            if user_id in user_index:
                entry = user_index[user_id]
                entry.last_seen = current_time
                entry.username = user_data.get("username", entry.username)
                entry.display_name = user_data.get("display_name", entry.display_name)
                if user_data.get("status"): entry.status = user_data["status"]
                if user_data.get("avatar_url"): entry.avatar_url = user_data["avatar_url"]
                if user_data.get("roles"): entry.roles = user_data["roles"]
                if user_data.get("guild_name"): entry.guild_name = user_data["guild_name"]
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
                logger.debug(f"Added new user {user_data.get('username')} to index for guild {guild_id}")
            
            return self.save_user_index(guild_id, user_index)
        except Exception as e:
            logger.error(f"Error updating user index for user {getattr(user, 'id', 'Unknown')}: {e}", exc_info=True)
            return False

    # Channel Indexing
    def get_channel_index_file_path(self, guild_id: int) -> str:
        return os.path.join(CHANNEL_INDEX_DIR, f"guild_{guild_id}_channels.json")

    def load_channel_index(self, guild_id: int) -> Dict[int, ChannelIndexEntry]:
        """Load channel index for a specific guild"""
        file_path = self.get_channel_index_file_path(guild_id)
        try:
            data = self.storage_manager.read(file_path)
            if not data:
                return {}
                
            channel_index = {}
            for channel_id_str, channel_data in data.get("channels", {}).items():
                channel_id = int(channel_id_str)
                channel_entry_data = {k: channel_data.get(k, None) for k in [f.name for f in fields(ChannelIndexEntry)]}
                entry = ChannelIndexEntry(**channel_entry_data)
                for field in fields(ChannelIndexEntry):
                    if getattr(entry, field.name) is None and field.default is not dataclasses.MISSING:
                        setattr(entry, field.name, field.default)
                channel_index[channel_id] = entry
            
            logger.debug(f"Loaded {len(channel_index)} channels from index for guild {guild_id}")
            return channel_index
        except Exception as e:
            logger.error(f"Error loading channel index for guild {guild_id}: {e}", exc_info=True)
            return {}

    def save_channel_index(self, guild_id: int, channel_index: Dict[int, ChannelIndexEntry]) -> bool:
        """Save channel index for a specific guild"""
        file_path = self.get_channel_index_file_path(guild_id)
        try:
            data = {
                "channels": {str(cid): asdict(c) for cid, c in channel_index.items()},
                "last_updated": time.time(),
                "guild_id": guild_id
            }
            logger.debug(f"Saved {len(channel_index)} channels to index for guild {guild_id}")
            return self.storage_manager.write(file_path, data)
        except Exception as e:
            logger.error(f"Error saving channel index for guild {guild_id}: {e}", exc_info=True)
            return False

    def index_channel(self, channel) -> ChannelIndexEntry:
        """Create a channel index entry from a Discord channel object"""
        try:
            return ChannelIndexEntry(
                channel_id=channel.id,
                guild_id=channel.guild.id,
                channel_name=channel.name,
                channel_type=str(channel.type).replace('channel_type.', ''),
                topic=getattr(channel, 'topic', None) or (channel.name if isinstance(channel, discord.Thread) else None),
                category_name=getattr(channel.category, 'name', None) if hasattr(channel, 'category') else (getattr(channel.parent.category, 'name', None) if isinstance(channel, discord.Thread) and hasattr(channel, 'parent') and hasattr(channel.parent, 'category') else None),
                is_nsfw=getattr(channel, 'nsfw', False) or (getattr(channel.parent, 'nsfw', False) if isinstance(channel, discord.Thread) and hasattr(channel, 'parent') else False),
                last_indexed=time.time(),
                message_count=0,
                guild_name=channel.guild.name,
                guild_description=channel.guild.description
            )
        except Exception as e:
            logger.error(f"Error indexing channel {getattr(channel, 'id', 'Unknown')}: {e}", exc_info=True)
            raise

    # Pinned Messages
    def get_pinned_messages_file_path(self, guild_id: int, channel_id: int) -> str:
        return os.path.join(PINNED_MESSAGES_DIR, f"guild_{guild_id}_channel_{channel_id}_pins.json")

    async def index_pinned_messages(self, guild_id: int, channel_id: int, channel: discord.abc.Messageable, is_valid_message_func, process_message_func) -> int:
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return 0

        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        current_pins = []
        indexed_count = 0

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleared old pinned messages file for channel {channel_id}")

            pins = await channel.pins()
            logger.debug(f"Fetched {len(pins)} pinned messages from #{channel.name}")

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
                    self.update_user_index(guild_id, message.author)
                    pin_entry = PinnedMessage(
                        user_id=message.author.id,
                        username=message.author.display_name,
                        content=cleaned_content,
                        timestamp=message.created_at.timestamp(),
                        message_id=message.id,
                        attachment_urls=image_urls,
                        embed_urls=embed_urls
                    )
                    current_pins.append(pin_entry)
                    indexed_count += 1
                else:
                    logger.debug(f"Skipped invalid pinned message {message.id} for indexing.")

            data_to_save = {
                "pins": [asdict(pin) for pin in current_pins],
                "last_indexed": time.time(),
                "guild_id": guild_id,
                "channel_id": channel_id
            }
            self.storage_manager.write(file_path, data_to_save)
            logger.info(f"Indexed {indexed_count} pinned messages for #{channel.name}")
            return indexed_count
        except discord.errors.Forbidden:
            logger.warning(f"Missing permissions to read pins in channel {channel.name}")
            return 0
        except Exception as e:
            logger.error(f"Error indexing pinned messages for channel {channel_id}: {e}", exc_info=True)
            return 0

    def load_pinned_messages(self, guild_id: int, channel_id: int) -> List[PinnedMessage]:
        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        data = self.storage_manager.read(file_path)
        return [PinnedMessage(**msg) for msg in data.get("pins", [])]

    def cleanup_stale_users(self, guild_id: int, cleanup_hours: int = 168) -> int:
        """Remove users from index if they haven't been seen recently."""
        try:
            cutoff_time = time.time() - (cleanup_hours * 3600)
            user_index = self.load_user_index(guild_id)
            if not user_index:
                return 0
            
            users_to_remove = [uid for uid, user in user_index.items() if user.last_seen < cutoff_time]
            
            if not users_to_remove:
                return 0
                
            for user_id in users_to_remove:
                del user_index[user_id]
                
            self.save_user_index(guild_id, user_index)
            logger.info(f"Cleaned up {len(users_to_remove)} stale users from guild {guild_id}")
            return len(users_to_remove)
        except Exception as e:
            logger.error(f"Error cleaning up stale users for guild {guild_id}: {e}", exc_info=True)
            return 0

    def cleanup_all_stale_users(self, bot_guilds, cleanup_hours: int = 168) -> int:
        """Clean up stale users across all guilds."""
        try:
            total_cleaned = 0
            for guild in bot_guilds:
                total_cleaned += self.cleanup_stale_users(guild.id, cleanup_hours)
            
            if total_cleaned > 0:
                logger.info(f"Cleaned up {total_cleaned} stale users across all guilds.")
            return total_cleaned
        except Exception as e:
            logger.error(f"Error during cleanup of all stale users: {e}", exc_info=True)
            return 0

    def update_contextual_user_index(self, guild_id: int, channel_id: int, conversation_manager) -> bool:
        """Update user index based on current conversation context."""
        try:
            messages = conversation_manager.load_conversation_history(guild_id, channel_id)
            if not messages:
                return True

            relevant_user_ids = set(msg.user_id for msg in messages if not msg.is_bot_response)
            
            mention_pattern = r'<@!?(\d+)>'
            for msg in messages:
                mentions = re.findall(mention_pattern, msg.content)
                for mention_id_str in mentions:
                    relevant_user_ids.add(int(mention_id_str))

            pinned_messages = self.load_pinned_messages(guild_id, channel_id)
            for pin in pinned_messages:
                relevant_user_ids.add(pin.user_id)
                mentions = re.findall(mention_pattern, pin.content)
                for mention_id_str in mentions:
                    relevant_user_ids.add(int(mention_id_str))
            
            user_index = self.load_user_index(guild_id)
            final_user_index = {uid: user_index[uid] for uid in relevant_user_ids if uid in user_index}
            
            if len(user_index) != len(final_user_index):
                logger.debug(f"Cleaned up user index for guild {guild_id}, removed {len(user_index) - len(final_user_index)} users.")
            
            return self.save_user_index(guild_id, final_user_index)
        except Exception as e:
            logger.error(f"Error updating contextual user index: {e}", exc_info=True)
            return False

    def cleanup_conversation_context(self, guild_id: int, channel_id: int, conversation_manager) -> int:
        """Clean up user index to only include users relevant to current conversation."""
        try:
            self.update_contextual_user_index(guild_id, channel_id, conversation_manager)
            user_index = self.load_user_index(guild_id)
            logger.info(f"Cleaned up user index for guild {guild_id}, {len(user_index)} users remain.")
            return len(user_index)
        except Exception as e:
            logger.error(f"Error cleaning up conversation context: {e}", exc_info=True)
            return 0

    def get_indexing_stats(self, guild_id: int) -> Dict[str, int]:
        """Get statistics about current indexing for a guild."""
        try:
            user_index = self.load_user_index(guild_id)
            channel_index = self.load_channel_index(guild_id)
            return {
                "users_indexed": len(user_index),
                "channels_indexed": len(channel_index),
                "total_user_messages": sum(user.message_count for user in user_index.values())
            }
        except Exception as e:
            logger.error(f"Error getting indexing stats for guild {guild_id}: {e}", exc_info=True)
            return {"users_indexed": 0, "channels_indexed": 0, "total_user_messages": 0}
