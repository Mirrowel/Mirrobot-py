"""
Main chatbot manager to orchestrate all chatbot-related functionality.
"""

from typing import Optional

import time
import discord
from utils.chatbot.config import ConfigManager
from utils.chatbot.conversation import ConversationManager
from utils.chatbot.formatting import LLMContextFormatter
from utils.chatbot.indexing import IndexingManager
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

DISCORD_EPOCH = 1420070400000
HISTORY_FETCH_LIMIT = 10

class ChatbotManager:
    """Orchestrates all chatbot functionality."""

    def __init__(self, bot_user_id: Optional[int] = None):
        self.storage_manager = JsonStorageManager()
        self.config_manager = ConfigManager(self.storage_manager)
        self.indexing_manager = IndexingManager(self.storage_manager, self.config_manager, bot_user_id)
        self.conversation_manager = ConversationManager(self.storage_manager, self.config_manager, self.indexing_manager, bot_user_id)
        self.formatter = LLMContextFormatter(self.config_manager, self.conversation_manager, self.indexing_manager)
        
        if bot_user_id:
            self.set_bot_user_id(bot_user_id)

    def set_bot_user_id(self, bot_id: int):
        """Set the bot's user ID for all relevant managers."""
        self.conversation_manager.set_bot_user_id(bot_id)
        self.indexing_manager.set_bot_user_id(bot_id)
        logger.debug(f"ChatbotManager bot_user_id set to {bot_id}")

    async def enable_chatbot(self, guild_id: int, channel_id: int, guild=None, channel=None) -> bool:
        """Enable chatbot mode and perform initial indexing."""
        channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
        channel_config.enabled = True
        
        if guild and channel:
            try:
                await self.index_chatbot_channel(guild_id, channel_id, channel)
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    await self.index_pinned_messages(channel)
                logger.info(f"Indexed chatbot channel and pins for #{channel.name}")
            except Exception as e:
                logger.error(f"Error indexing channel on enable: {e}", exc_info=True)
        
        return self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

    def disable_chatbot(self, guild_id: int, channel_id: int) -> bool:
        """Disable chatbot mode."""
        channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
        channel_config.enabled = False
        return self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

    async def clear_channel_data(self, guild_id: int, channel_id: int):
        """Clear all data for a specific channel."""
        await self.conversation_manager.clear_conversation_history(guild_id, channel_id)
        await self.indexing_manager.clear_pinned_messages(guild_id, channel_id)
        channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
        channel_config.last_cleared_timestamp = time.time()
        self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

    async def cleanup_guild_data(self, guild_id: int):
        """Remove all data associated with a guild."""
        logger.info(f"Cleaning up all data for guild {guild_id}.")
        await self.indexing_manager.remove_guild_indexes(guild_id)
        self.config_manager.remove_guild_config(guild_id)
        # Conversation histories are stored by guild/channel, so they will be removed
        # when the guild's directory is removed by the indexing manager.
        logger.info(f"Cleanup for guild {guild_id} complete.")

    async def cleanup_channel_data(self, guild_id: int, channel_id: int):
        """Remove all data associated with a channel."""
        logger.info(f"Cleaning up all data for channel {channel_id} in guild {guild_id}.")
        await self.conversation_manager.clear_conversation_history(guild_id, channel_id)
        await self.indexing_manager.clear_pinned_messages(guild_id, channel_id)
        self.config_manager.remove_channel_config(guild_id, channel_id)
        logger.info(f"Cleanup for channel {channel_id} complete.")

    def should_respond_to_message(self, guild_id: int, channel_id: int, message, bot_user_id: int) -> bool:
        """Determine if the bot should respond to a message in chatbot mode"""
        try:
            if not self.config_manager.is_chatbot_enabled(guild_id, channel_id):
                return False
            
            if message.author.bot and message.author.id != bot_user_id:
                return False
            
            config = self.config_manager.get_channel_config(guild_id, channel_id)
            
            if config.auto_respond_to_mentions and bot_user_id in [user.id for user in message.mentions]:
                logger.debug(f"Bot mentioned in message {message.id}, should respond")
                return True
            
            if config.auto_respond_to_replies and message.reference:
                try:
                    referenced_message = message.reference.resolved
                    if referenced_message and referenced_message.author and referenced_message.author.id == bot_user_id:
                        logger.debug(f"Message {message.id} is reply to bot, should respond")
                        return True
                except discord.NotFound:
                    logger.debug(f"Referenced message {message.reference.message_id} not found.")
                except Exception as e:
                    logger.debug(f"Error checking resolved referenced message: {e}", exc_info=True)
            
            return False
        except Exception as e:
            logger.error(f"Error determining if should respond: {e}", exc_info=True)
            return False

    async def index_chatbot_channel(self, guild_id: int, channel_id: int, channel) -> bool:
        """Index a channel incrementally or perform a full scan if needed."""
        try:
            await self.indexing_manager.update_channel_index(channel)

            config = self.config_manager.get_channel_config(guild_id, channel_id)
            existing_history = await self.conversation_manager.load_conversation_history(guild_id, channel_id)
            
            after_timestamp = config.last_cleared_timestamp or 0
            after_message_id = 0
            if existing_history:
                after_message_id = max(msg.message_id for msg in existing_history)

            # Determine the true 'after' point
            after_param = None
            if after_timestamp > 0:
                after_param = discord.Object(id=((int(after_timestamp * 1000) - DISCORD_EPOCH) << 22)) # Convert timestamp to snowflake
                if after_message_id > after_param.id:
                    after_param = discord.Object(id=after_message_id)
            elif after_message_id > 0:
                after_param = discord.Object(id=after_message_id)

            messages_to_add = []
            # Unified logic: Always fetch a limited number of recent messages, then filter.
            limit = config.max_context_messages
            logger.debug(f"Fetching up to {limit} recent messages for #{channel.name} to check against criteria.")

            # 1. Fetch the most recent N messages.
            # If after_param is set, it acts as a starting point for the fetch.
            # If not, it fetches the absolute most recent messages in the channel.
            history_iterator = channel.history(limit=limit, after=after_param)
            recent_messages = [msg async for msg in history_iterator if msg.type in [discord.MessageType.default, discord.MessageType.reply]]

            # 2. Filter these messages by the time window.
            # This is a secondary check to ensure we don't include messages from outside the window,
            # even if they are within the message limit.
            time_window_cutoff = time.time() - (config.context_window_hours * 3600)
            messages_to_add = [msg for msg in recent_messages if msg.created_at.timestamp() >= time_window_cutoff]

            # 3. Reverse to get chronological order for processing.
            messages_to_add.reverse()
            logger.debug(f"Fetched {len(recent_messages)} messages, {len(messages_to_add)} are within the final time window and limits.")

            if not messages_to_add:
                logger.info(f"No new messages to index for #{channel.name}.")
                return True

            added_count, users_to_index = await self.conversation_manager.bulk_add_messages_to_conversation(guild_id, channel_id, messages_to_add)
            
            # Also index users from mentions and replies in the fetched messages
            for msg in messages_to_add:
                users_to_index.extend(msg.mentions)
                if msg.reference and msg.reference.resolved and hasattr(msg.reference.resolved, 'author'):
                    users_to_index.append(msg.reference.resolved.author)

            if users_to_index:
                await self.indexing_manager.update_users_bulk(guild_id, list(set(users_to_index)), is_message_author=True)

            logger.info(f"Indexing for #{channel.name} complete. Added {added_count} new messages. Indexed {len(set(users_to_index))} users.")
            return True

        except Exception as e:
            logger.error(f"Error indexing chatbot channel #{channel.name}: {e}", exc_info=True)
            return False

    async def index_pinned_messages(self, channel: discord.abc.Messageable):
        """Index pinned messages, passing the validation and processing functions from the conversation manager."""
        return await self.indexing_manager.index_pinned_messages(
            channel,
            self.conversation_manager._is_valid_context_message,
            self.conversation_manager._process_discord_message_for_context
        )

    def get_all_chatbot_enabled_channels(self, guilds) -> list[tuple[int, int]]:
        """Get all chatbot-enabled channels across all guilds."""
        enabled_channels = []
        try:
            config = self.config_manager.config_cache
            channels_config = config.get("channels", {})
            
            for guild in guilds:
                guild_key = str(guild.id)
                if guild_key in channels_config:
                    for channel_key, channel_data in channels_config[guild_key].items():
                        if channel_data.get("enabled", False):
                            try:
                                channel_id = int(channel_key)
                                if guild.get_channel(channel_id):
                                    enabled_channels.append((guild.id, channel_id))
                            except (ValueError, AttributeError):
                                logger.warning(f"Invalid or deleted channel ID '{channel_key}' in config for guild {guild.name}")
                                continue
            return enabled_channels
        except Exception as e:
            logger.error(f"Error getting all chatbot enabled channels: {e}", exc_info=True)
            return []

    def cleanup_conversation_context(self, guild_id: int, channel_id: int) -> int:
        """Clean up user index, passing the conversation manager to the indexing manager."""
        return self.indexing_manager.cleanup_conversation_context(
            guild_id,
            channel_id,
            self.conversation_manager
        )

    async def add_message_to_conversation(self, guild_id: int, channel_id: int, message: discord.Message) -> bool:
        """Public method to add a message, handling dependencies internally."""
        success, users_to_index = await self.conversation_manager.add_message_to_conversation(guild_id, channel_id, message)
        if success and users_to_index:
            await self.indexing_manager.update_users_bulk(guild_id, users_to_index, is_message_author=True)
        return success

    def __getattr__(self, name):
        """Delegate calls to the appropriate manager."""
        for manager in [self.config_manager, self.conversation_manager, self.indexing_manager, self.formatter]:
            if hasattr(manager, name):
                return getattr(manager, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

# Global instance
chatbot_manager = ChatbotManager()
