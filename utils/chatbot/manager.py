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

class ChatbotManager:
    """Orchestrates all chatbot functionality."""

    def __init__(self, bot_user_id: Optional[int] = None):
        self.storage_manager = JsonStorageManager()
        self.config_manager = ConfigManager(self.storage_manager)
        self.indexing_manager = IndexingManager(self.storage_manager, bot_user_id)
        self.conversation_manager = ConversationManager(self.storage_manager, self.config_manager, bot_user_id)
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
                    await self.index_pinned_messages(guild_id, channel_id, channel)
                logger.info(f"Indexed chatbot channel and pins for #{channel.name}")
            except Exception as e:
                logger.error(f"Error indexing channel on enable: {e}", exc_info=True)
        
        return self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

    def disable_chatbot(self, guild_id: int, channel_id: int) -> bool:
        """Disable chatbot mode."""
        channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
        channel_config.enabled = False
        return self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

    def clear_channel_data(self, guild_id: int, channel_id: int):
        """Clear all data for a specific channel."""
        self.conversation_manager.clear_conversation_history(guild_id, channel_id)
        self.indexing_manager.clear_pinned_messages(guild_id, channel_id)
        channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
        channel_config.last_cleared_timestamp = time.time()
        self.config_manager.set_channel_config(guild_id, channel_id, channel_config)

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
        """Index the specific channel where chatbot is enabled and fetch recent message history"""
        try:
            channel_index = self.indexing_manager.load_channel_index(guild_id)
            channel_entry = self.indexing_manager.index_channel(channel)
            channel_index[channel_id] = channel_entry
            self.indexing_manager.save_channel_index(guild_id, channel_index)

            config = self.config_manager.get_channel_config(guild_id, channel_id)
            max_messages_to_index = config.max_context_messages
            cutoff_time = time.time() - (config.context_window_hours * 3600)
            
            if config.last_cleared_timestamp and cutoff_time < config.last_cleared_timestamp:
                cutoff_time = config.last_cleared_timestamp

            logger.debug(f"Attempting to index up to {max_messages_to_index} qualifying messages from #{channel.name}")
            
            messages_indexed = 0
            messages_skipped = 0
            messages_failed = 0
            total_messages_fetched_from_discord = 0
            consecutive_old_messages = 0
            
            last_message_object = None
            while messages_indexed < max_messages_to_index:
                history_iterator = channel.history(limit=500, before=last_message_object, oldest_first=False)
                
                batch_fetched = 0
                async for message in history_iterator:
                    total_messages_fetched_from_discord += 1
                    batch_fetched += 1
                    last_message_object = message

                    if message.created_at.timestamp() < cutoff_time:
                        consecutive_old_messages += 1
                        if consecutive_old_messages >= 4:
                            logger.debug(f"Stopping fetch: {consecutive_old_messages} consecutive messages older than cutoff.")
                            break
                        continue
                    else:
                        consecutive_old_messages = 0

                    if message.type not in [discord.MessageType.default, discord.MessageType.reply]:
                        messages_skipped += 1
                        continue

                    if self.add_message_to_conversation(guild_id, channel_id, message):
                        messages_indexed += 1
                        for mentioned_user in message.mentions:
                            self.indexing_manager.update_user_index(guild_id, mentioned_user)
                        if message.reference and message.reference.resolved and hasattr(message.reference.resolved, 'author'):
                            self.indexing_manager.update_user_index(guild_id, message.reference.resolved.author)
                    else:
                        messages_failed += 1
                    
                    if messages_indexed >= max_messages_to_index:
                        break
                
                if batch_fetched == 0 or consecutive_old_messages >= 4:
                    logger.debug(f"Exiting fetch loop. Batch fetched: {batch_fetched}, Consecutive old: {consecutive_old_messages}")
                    break
                if messages_indexed >= max_messages_to_index:
                    break

            logger.info(f"Indexed chatbot channel #{channel.name}: {messages_indexed}/{max_messages_to_index} qualifying messages "
                       f"({messages_skipped} system skipped, {messages_failed} content/time filtered, {total_messages_fetched_from_discord} Discord messages fetched) for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Error indexing chatbot channel #{channel.name}: {e}", exc_info=True)
            return False

    async def index_pinned_messages(self, guild_id: int, channel_id: int, channel: discord.abc.Messageable):
        """Index pinned messages, passing the validation and processing functions from the conversation manager."""
        return await self.indexing_manager.index_pinned_messages(
            guild_id,
            channel_id,
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

    def add_message_to_conversation(self, guild_id: int, channel_id: int, message: discord.Message) -> bool:
        """Public method to add a message, handling dependencies internally."""
        return self.conversation_manager.add_message_to_conversation(
            guild_id,
            channel_id,
            message,
            self.indexing_manager.update_user_index
        )

    def __getattr__(self, name):
        """Delegate calls to the appropriate manager."""
        for manager in [self.config_manager, self.conversation_manager, self.indexing_manager, self.formatter]:
            if hasattr(manager, name):
                return getattr(manager, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

# Global instance
chatbot_manager = ChatbotManager()
