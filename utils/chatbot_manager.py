"""
Chatbot management utilities for persistent conversation mode.

This module handles the chatbot functionality including:
- Channel-based chatbot configuration
- Conversation context storage and management
- Message history tracking
- Context prioritization and pruning
"""

import dataclasses
import json
import os
import time
import re # Import re for regex operations
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, fields

import discord
from utils.logging_setup import get_logger

logger = get_logger()

# File paths for storing chatbot data
CHATBOT_CONFIG_FILE = "data/chatbot_config.json"
CONVERSATION_DATA_DIR = "data/conversations"
USER_INDEX_DIR = "data/user_index"
CHANNEL_INDEX_DIR = "data/channel_index"
PINNED_MESSAGES_DIR = "data/pins" # NEW: Directory for pinned messages

# Default configuration
DEFAULT_CHATBOT_CONFIG = {
    "max_context_messages": 100,
    "max_user_context_messages": 20,
    "context_window_hours": 6,
    "response_delay_seconds": 1,
    "max_response_length": 2000,
    "auto_prune_enabled": True,
    "prune_interval_hours": 6,
    "user_index_cleanup_hours": 168,  # 7 days
    "auto_index_on_restart": True,
    "auto_index_on_enable": True
    # Note: LLM-specific settings like "llm_provider", "google_ai_api_key", etc.
    # have been moved to the dedicated LLM config in config/llm_config_manager.py
}

# Ensure data directories exist
os.makedirs(os.path.dirname(CHATBOT_CONFIG_FILE), exist_ok=True)
os.makedirs(CONVERSATION_DATA_DIR, exist_ok=True)
os.makedirs(USER_INDEX_DIR, exist_ok=True)
os.makedirs(CHANNEL_INDEX_DIR, exist_ok=True)
os.makedirs(PINNED_MESSAGES_DIR, exist_ok=True) # NEW: Ensure pinned messages directory exists

@dataclass
class ConversationMessage:
    """Represents a message in a conversation"""
    user_id: int
    username: str
    content: str
    timestamp: float
    message_id: int
    is_bot_response: bool = False
    is_self_bot_response: bool = False # NEW: Is this bot's own response
    referenced_message_id: Optional[int] = None
    attachment_urls: List[str] = dataclasses.field(default_factory=list)
    embed_urls: List[str] = dataclasses.field(default_factory=list) # Though primarily focusing on attachment_urls for visual context

@dataclass
class PinnedMessage: # NEW DATACLASS
    """Represents a pinned message in a channel"""
    user_id: int
    username: str
    content: str
    timestamp: float
    message_id: int
    attachment_urls: List[str] = dataclasses.field(default_factory=list)
    embed_urls: List[str] = dataclasses.field(default_factory=list)

@dataclass
class UserIndexEntry:
    """Represents a user in the index"""
    user_id: int
    username: str
    display_name: str
    guild_id: int
    guild_name: str
    roles: List[str]  # List of role names
    avatar_url: Optional[str] = None
    status: Optional[str] = None
    first_seen: float = 0.0
    last_seen: float = 0.0
    message_count: int = 0
    is_bot: bool = False

@dataclass
class ChannelIndexEntry:
    """Represents a channel in the index"""
    channel_id: int
    guild_id: int
    channel_name: str
    channel_type: str
    guild_name: Optional[str] = None
    guild_description: Optional[str] = None
    topic: Optional[str] = None
    category_name: Optional[str] = None
    is_nsfw: bool = False
    last_indexed: float = 0.0
    message_count: int = 0

@dataclass
class ChannelChatbotConfig:
    """Configuration for chatbot mode in a specific channel"""
    enabled: bool = False
    max_context_messages: int = 100
    max_user_context_messages: int = 20
    context_window_hours: int = 6
    response_delay_seconds: int = 1
    max_response_length: int = 2000
    auto_prune_enabled: bool = True
    prune_interval_hours: int = 6
    auto_respond_to_mentions: bool = True
    auto_respond_to_replies: bool = True
    
    def __post_init__(self):
        # Handle cases where config might have old values or missing fields
        # Ensure numerical values are within bounds
        self.max_context_messages = max(10, min(self.max_context_messages, 200))
        self.max_user_context_messages = max(5, min(self.max_user_context_messages, 50))
        self.context_window_hours = max(1, min(self.context_window_hours, 168))
        self.response_delay_seconds = max(0, min(self.response_delay_seconds, 10))
        self.max_response_length = max(100, min(self.max_response_length, 4000))
        self.prune_interval_hours = max(1, min(self.prune_interval_hours, 48))
        
        # Ensure boolean values are actually booleans
        self.enabled = bool(self.enabled)
        self.auto_prune_enabled = bool(self.auto_prune_enabled)
        self.auto_respond_to_mentions = bool(self.auto_respond_to_mentions)
        self.auto_respond_to_replies = bool(self.auto_respond_to_replies)

class ChatbotManager:
    """Manages chatbot configuration and conversation context"""
    
    def __init__(self, bot_user_id: Optional[int] = None):
        self.config_cache = {}
        self.conversation_cache = {}
        self.load_config()
        self.bot_user_id: Optional[int] = bot_user_id # Bot's own user ID, crucial for self-bot responses
    
    def load_config(self) -> Dict[str, Any]:
        """Load chatbot configuration from file"""
        try:
            if os.path.exists(CHATBOT_CONFIG_FILE):
                with open(CHATBOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.config_cache = config
                    logger.debug("Loaded chatbot configuration from file")
                    return config
            else:
                # Create default config file
                default_config = {"channels": {}, "global": DEFAULT_CHATBOT_CONFIG}
                self.save_config(default_config)
                self.config_cache = default_config
                return default_config
        except Exception as e:
            logger.error(f"Error loading chatbot config: {e}", exc_info=True)
            return {"channels": {}, "global": DEFAULT_CHATBOT_CONFIG}
    
    def set_bot_user_id(self, bot_id: int):
        """Set the bot's user ID for internal context processing."""
        self.bot_user_id = bot_id
        logger.debug(f"ChatbotManager bot_user_id set to {self.bot_user_id}")

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """Save chatbot configuration to file"""
        try:
            config_to_save = config if config is not None else self.config_cache
            with open(CHATBOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
            self.config_cache = config_to_save
            logger.debug("Saved chatbot configuration to file")
            return True
        except Exception as e:
            logger.error(f"Error saving chatbot config: {e}", exc_info=True)
            return False
    
    def get_channel_config(self, guild_id: int, channel_id: int) -> "ChannelChatbotConfig":
        """Get chatbot configuration for a specific channel"""
        config = self.config_cache
        guild_key = str(guild_id)
        channel_key = str(channel_id)
        
        channel_data = config.get("channels", {}).get(guild_key, {}).get(channel_key, {})
        
        # Merge with global defaults
        global_config = config.get("global", DEFAULT_CHATBOT_CONFIG)
        merged_config = {**global_config, **channel_data}
        
        # Filter out config keys that aren't fields in ChannelChatbotConfig and instantiate
        # This will ensure default values for any missing fields are applied by the dataclass,
        # and __post_init__ will validate types/ranges.
        return ChannelChatbotConfig(**{k: v for k, v in merged_config.items() if k in {f.name for f in fields(ChannelChatbotConfig)}}) # type: ignore
    
    def set_channel_config(self, guild_id: int, channel_id: int, channel_config: ChannelChatbotConfig) -> bool:
        """Set chatbot configuration for a specific channel"""
        try:
            config = self.config_cache
            guild_key = str(guild_id)
            channel_key = str(channel_id)
            
            if "channels" not in config:
                config["channels"] = {}
            if guild_key not in config["channels"]:
                config["channels"][guild_key] = {}
            
            # Use asdict to convert dataclass back to dict for saving
            config["channels"][guild_key][channel_key] = asdict(channel_config)
            
            return self.save_config(config)
        except Exception as e:
            logger.error(f"Error setting channel config: {e}", exc_info=True)
            return False
    
    def is_chatbot_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if chatbot mode is enabled for a specific channel"""
        channel_config = self.get_channel_config(guild_id, channel_id)
        return channel_config.enabled
    
    async def enable_chatbot(self, guild_id: int, channel_id: int, guild=None, channel=None) -> bool:
        """Enable chatbot mode for a specific channel"""
        channel_config = self.get_channel_config(guild_id, channel_id)
        channel_config.enabled = True
        
        # Index only the current channel if guild and channel objects are provided
        if guild and channel:
            try:
                # The 'channel' parameter here is already the discord.TextChannel or discord.Thread object
                await self.index_chatbot_channel(guild_id, channel_id, channel)
                # NEW: Also index pinned messages when enabling chatbot
                if isinstance(channel, (discord.TextChannel, discord.Thread)): # Pinned messages only exist on TextChannels
                    await self.index_pinned_messages(guild_id, channel_id, channel)
                logger.info(f"Indexed chatbot channel and pins (if applicable) #{channel.name} for guild {guild.name}")
            except Exception as e:
                logger.error(f"Error indexing channel on enable: {e}", exc_info=True)
        
        return self.set_channel_config(guild_id, channel_id, channel_config)
    
    def disable_chatbot(self, guild_id: int, channel_id: int) -> bool:
        """Disable chatbot mode for a specific channel"""
        channel_config = self.get_channel_config(guild_id, channel_id)
        channel_config.enabled = False
        return self.set_channel_config(guild_id, channel_id, channel_config)
    
    def get_conversation_file_path(self, guild_id: int, channel_id: int) -> str:
        """Get the file path for conversation data"""
        return os.path.join(CONVERSATION_DATA_DIR, f"guild_{guild_id}", f"channel_{channel_id}.json")
    
    def _process_discord_message_for_context(self, message: discord.Message) -> Tuple[str, List[str], List[str]]:
        """
        Processes a discord.Message to extract content, filter media, and prepare for context.
        Returns (cleaned_content, image_urls, video_urls).
        
        - Filters out video/GIF URLs from content.
        - Retains image URLs from attachments.
        """
        cleaned_content = message.content
        image_urls = []
        video_urls = []
        embed_urls = [] # For other embeds, not necessarily images or videos

        # Process attachments
        for attachment in message.attachments:
            if attachment.content_type.startswith('image/'):
                image_urls.append(attachment.url)
                # If content is just the attachment URL, remove it as we'll represent it separately
                if attachment.url in cleaned_content:
                    cleaned_content = cleaned_content.replace(attachment.url, '').strip()
            elif attachment.content_type.startswith(('video/', 'image/gif')): # Include GIFs here
                video_urls.append(attachment.url)
                # Remove video/gif URLs from content as requested
                if attachment.url in cleaned_content:
                    cleaned_content = cleaned_content.replace(attachment.url, '').strip()
                logger.debug(f"Filtered out video/gif attachment URL: {attachment.url}")
            # Application specific attachments (like discord uploads of mp4/mov)
            elif attachment.content_type in ['application/x-discord-application', 'application/octet-stream'] and \
                 (attachment.filename.lower().endswith(('.mp4', '.mov', '.webm', '.gif'))):
                video_urls.append(attachment.url)
                if attachment.url in cleaned_content:
                    cleaned_content = cleaned_content.replace(attachment.url, '').strip()
                logger.debug(f"Filtered out video/gif attachment URL (app type): {attachment.url}")

        # Process embeds (e.g., Tenor, Giphy, direct video links from other sources)
        # This is a bit tricky as embeds might not always have direct URLs matching content.
        # Focus on embeds that explicitly represent images/videos.
        for embed in message.embeds:
            if embed.type == 'image' and embed.url:
                # Only add if it's a direct image embed, not just a thumbnail for something else
                if embed.url.startswith(('http://', 'https://')) and any(ext in embed.url.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    image_urls.append(embed.url)
                    # Remove from content if it's there
                    if embed.url in cleaned_content:
                        cleaned_content = cleaned_content.replace(embed.url, '').strip()
            elif embed.type in ['video', 'gifv'] and (embed.url or (embed.video and embed.video.url)):
                # Filter video/gif embeds
                url_to_filter = embed.url or (embed.video.url if embed.video else None)
                if url_to_filter:
                    video_urls.append(url_to_filter)
                    if url_to_filter in cleaned_content:
                        cleaned_content = cleaned_content.replace(url_to_filter, '').strip()
                    logger.debug(f"Filtered out video/gif embed URL: {url_to_filter}")
            elif embed.url: # Capture other embed URLs generally
                embed_urls.append(embed.url)
        
        # Clean up any residual whitespace after URL removal
        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()

        return cleaned_content, image_urls, embed_urls # Returning embed_urls for future use

    def _is_valid_context_message(self, msg: ConversationMessage, debug_mode: bool = False) -> tuple[bool, list[str]]:
        """Check if a message is valid for context inclusion
        
        Args:
            msg: The conversation message to validate
            debug_mode: If True, returns detailed analysis steps
            
        Returns:
            tuple: (is_valid, debug_steps) where debug_steps is a list of analysis steps
        
        Filters out:
        - Empty messages (unless they contain images)
        - Bot commands (messages starting with common prefixes)
        - Messages with only whitespace/special characters
        """
        debug_steps = []
        try:
            content = msg.content.strip()
            message_preview = content[:50] + "..." if len(content) > 50 else content
            
            if debug_mode:
                debug_steps.append(f"📝 **Original Message:** `{content}`")
                debug_steps.append(f"👤 **From User:** {msg.username} (ID: {msg.user_id})")
                debug_steps.append(f"🖼️ **Attachment URLs:** {msg.attachment_urls}")
            
            # Skip empty messages UNLESS they contain attachment URLs (images)
            if not content and not msg.attachment_urls:
                if debug_mode:
                    debug_steps.append("❌ **Filter Result:** Empty message and no attachments - FILTERED")
                return False, debug_steps
            
            # Extract mentions and emojis from the content first
            mention_pattern = r'<@!?(\d+)>'
            emoji_pattern = r'<a?:\w+:\d+>'  # Custom Discord emojis
            
            mentions = re.findall(mention_pattern, content)
            emojis = re.findall(emoji_pattern, content)
            
            # Remove mentions and emojis from content for command analysis
            content_without_mentions = re.sub(mention_pattern, '', content).strip()
            content_for_analysis = re.sub(emoji_pattern, '', content_without_mentions).strip()
            
            if debug_mode:
                debug_steps.append(f"👥 **Mentions Found:** {len(mentions)} - {mentions if mentions else 'None'}")
                debug_steps.append(f"😀 **Emojis Found:** {len(emojis)} - {emojis if emojis else 'None'}")
                debug_steps.append(f"🔄 **Content without Mentions:** `{content_without_mentions}`")
                debug_steps.append(f"🔍 **Content for Analysis:** `{content_for_analysis}`")
            
            # If after removing mentions and emojis the message is empty, keep it if it had mentions, emojis, or attachments
            if not content_for_analysis:
                keep_message = len(mentions) > 0 or len(emojis) > 0 or len(msg.attachment_urls) > 0
                if debug_mode:
                    if keep_message:
                        debug_steps.append("✅ **Filter Result:** Message is just mentions/emojis/attachments - KEPT")
                    else:
                        debug_steps.append("❌ **Filter Result:** Message became empty after cleaning - FILTERED")
                return keep_message, debug_steps
            
            # Skip messages that are only whitespace or special characters (after removing mentions/emojis)
            if not any(c.isalnum() for c in content_for_analysis):
                if debug_mode:
                    debug_steps.append(f"❌ **Filter Result:** No alphanumeric characters in `{content_for_analysis}` - FILTERED")
                return False, debug_steps
            
            # Check for bot commands (common prefixes) - but only at the very start
            command_prefixes = ['!', '/', '$', '?', '.', '-', '+', '>', '<', '=', '~', '`']
            if content_for_analysis.startswith(tuple(command_prefixes)):
                if debug_mode:
                    debug_steps.append(f"❌ **Filter Result:** Command prefix detected in `{content_for_analysis}` - FILTERED")
                return False, debug_steps
            
            # Check for bot command patterns like "p!", "ocr!", etc.
            # Pattern: optional letters/numbers followed by exclamation mark at start
            command_pattern = r'^[a-zA-Z0-9]{1,5}!'
            if re.match(command_pattern, content_for_analysis):
                if debug_mode:
                    debug_steps.append(f"❌ **Filter Result:** Command pattern (letters/numbers!) detected in `{content_for_analysis}` - FILTERED")
                return False, debug_steps
            
            # More conservative check for command-like patterns
            words = content_for_analysis.split()
            if len(words) >= 2:
                first_word = words[0].lower()
                
                # Only filter if first word starts with command prefix
                if first_word.startswith(tuple(command_prefixes)):
                    if debug_mode:
                        debug_steps.append(f"❌ **Filter Result:** First word `{first_word}` starts with command prefix - FILTERED")
                    return False, debug_steps
            
            
            if debug_mode:
                debug_steps.append(f"✅ **Filter Result:** Message `{message_preview}` passed all filters - KEPT")
            return True, debug_steps
            
        except Exception as e:
            if debug_mode:
                debug_steps.append(f"⚠️ **Error during validation:** {str(e)} - defaulting to KEEP")
            logger.error(f"Error validating context message from {msg.username}: {e}", exc_info=True)
            return True, debug_steps# Default to including the message if validation fails

    def load_conversation_history(self, guild_id: int, channel_id: int) -> List[ConversationMessage]:
        """Load conversation history for a specific channel"""
        file_path = self.get_conversation_file_path(guild_id, channel_id)
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f) # type: dict
                    messages = [ConversationMessage(**msg) for msg in data.get("messages", [])]
                    
                    # Filter messages within the context window
                    channel_config = self.get_channel_config(guild_id, channel_id)
                    cutoff_time = time.time() - (channel_config.context_window_hours * 3600)
                    # Filter out empty messages, bot commands, and messages outside time window
                    filtered_messages = []
                    total_loaded = len(messages)
                    time_filtered = 0
                    content_filtered = 0
                    
                    for msg in messages:
                        if msg.timestamp < cutoff_time:
                            time_filtered += 1
                            continue
                        is_valid, _ = self._is_valid_context_message(msg, debug_mode=False)
                        if is_valid:
                            filtered_messages.append(msg)
                        else:
                            content_filtered += 1
                    
                    #logger.debug(f"Conversation history filtering for guild {guild_id}, channel {channel_id}:")
                    #logger.debug(f"  Total messages loaded: {total_loaded}")
                    #logger.debug(f"  Filtered by time window: {time_filtered}")
                    #logger.debug(f"  Filtered by content: {content_filtered}")
                    #logger.debug(f"  Final valid messages: {len(filtered_messages)}")
                    return filtered_messages
            else:
                return []
        except Exception as e:
            logger.error(f"Error loading conversation history: {e}", exc_info=True)
            return []
    
    def save_conversation_history(self, guild_id: int, channel_id: int, messages: List[ConversationMessage]) -> bool:
        """Save conversation history for a specific channel"""
        file_path = self.get_conversation_file_path(guild_id, channel_id)
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert messages to dict format
            data = {
                "messages": [asdict(msg) for msg in messages],
                "last_updated": time.time()
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            #logger.debug(f"Saved {len(messages)} messages to conversation history")
            return True
        except Exception as e:
            logger.error(f"Error saving conversation history: {e}", exc_info=True)
            return False
    
    def add_message_to_conversation(self, guild_id: int, channel_id: int, message: discord.Message, bot_user_id: int) -> bool:
        """Add a message to the conversation history"""
        try:
            # First check if this message has already been added to avoid duplicates
            if self.check_duplicate_message(guild_id, channel_id, message.id):
                # Message already exists in history, consider this a success
                return True
                
            # Process message content and media
            cleaned_content, image_urls, embed_urls = self._process_discord_message_for_context(message)
            
            # If after processing, the message content is empty and there are no images, then skip it
            # This handles messages that are *only* filtered videos/gifs
            if not cleaned_content and not image_urls:
                logger.debug(f"Skipping message {message.id} as content became empty after media filtering and no images are present.")
                return True # Treat as success, as it means we correctly handled the message

            # Update user index from message (message-based user discovery)
            self.update_user_index(guild_id, message.author, is_message_author=True)
            
            # Load existing conversation
            messages = self.load_conversation_history(guild_id, channel_id)
            
            # Ensure bot_user_id is available
            if self.bot_user_id is None:
                self.set_bot_user_id(bot_user_id) # Set it if not already set
            
            # Create conversation message
            conv_message = ConversationMessage( # type: ignore
                user_id=message.author.id,
                username=message.author.display_name, # This is Discord's display_name (nickname)
                content=cleaned_content, # Use cleaned content
                timestamp=message.created_at.timestamp(),
                message_id=message.id,
                is_bot_response=message.author.bot, # True if any bot, including self
                is_self_bot_response=(message.author.id == self.bot_user_id), # True only if *this* bot
                referenced_message_id=getattr(message.reference, 'message_id', None) if message.reference else None,
                attachment_urls=image_urls, # Only store image URLs here for now
                embed_urls=embed_urls # Store embed URLs
            )
            
            # Add to messages
            messages.append(conv_message)
            
            # Apply message limit
            channel_config = self.get_channel_config(guild_id, channel_id)
            if len(messages) > channel_config.max_context_messages:
                messages = messages[-channel_config.max_context_messages:]
            
            # Save updated conversation
            return self.save_conversation_history(guild_id, channel_id, messages)
        except Exception as e:
            logger.error(f"Error adding message to conversation: {e}", exc_info=True)
            return False    
    
    def edit_message_in_conversation(self, guild_id: int, channel_id: int, message_id: int, new_content: str) -> bool:
        """Update the content of an existing message in conversation history
        
        Args:
            guild_id: ID of the guild
            channel_id: ID of the channel
            message_id: ID of the message to edit
            new_content: New message content
            
        Returns:
            True if message was found and updated, False otherwise
        """
        try:
            # Load existing messages
            messages = self.load_conversation_history(guild_id, channel_id)
            if not messages:
                return False
            
            # Find the message to update
            message_found = False
            for msg in messages:
                if msg.message_id == message_id:
                    # Note: We're not re-running _process_discord_message_for_context here
                    # as a raw edit payload only gives new_content, not attachments/embeds.
                    # This means attachments/embeds for an edited message might become stale.
                    # For simplicity, we update only content. A full solution would require fetching the message.
                    msg.content = new_content
                    message_found = True
                    logger.debug(f"Updated message {message_id} in conversation history")
                    break
            
            if message_found:
                # Save the updated messages back to the conversation history
                return self.save_conversation_history(guild_id, channel_id, messages)
            else:
                logger.debug(f"Message {message_id} not found in conversation history for editing")
                return False
        except Exception as e:
            logger.error(f"Error editing message in conversation: {e}", exc_info=True)
            return False
    
    def delete_message_from_conversation(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Remove a message from conversation history
        
        Args:
            guild_id: ID of the guild
            channel_id: ID of the channel
            message_id: ID of the message to delete
            
        Returns:
            True if message was found and deleted, False otherwise
        """
        try:
            # Debug logging
            logger.debug(f"Delete request: message_id={message_id} ({type(message_id)})")
            
            # Load existing messages
            messages = self.load_conversation_history(guild_id, channel_id)
            if not messages:
                logger.debug(f"No conversation history found")
                return False
            
            # Debug: Check message ID types in the history
            if messages:
                sample_msg = messages[0]
                logger.debug(f"Sample message from history: ID={sample_msg.message_id} ({type(sample_msg.message_id)})")
            
            # Find and remove the message
            original_length = len(messages)
            messages = [msg for msg in messages if msg.message_id != message_id]
            
            if len(messages) < original_length:
                # Message was found and removed
                logger.debug(f"Removed message {message_id} from conversation history")
                return self.save_conversation_history(guild_id, channel_id, messages)
            else:
                logger.debug(f"Message {message_id} not found in conversation history")
                return False
        except Exception as e:
            logger.error(f"Error deleting message from conversation: {e}", exc_info=True)
            return False
    
    def get_prioritized_context(self, guild_id: int, channel_id: int, requesting_user_id: int) -> List[ConversationMessage]:
        """Get conversation context prioritized for the requesting user"""
        try:
            # Load ALL messages first (this already filters out invalid messages and by time window)
            all_messages = self.load_conversation_history(guild_id, channel_id)
            channel_config = self.get_channel_config(guild_id, channel_id)
            
            if not all_messages:
                return []
            
            # Sort all messages by timestamp to ensure we work with chronologically ordered data
            all_messages.sort(key=lambda x: x.timestamp)
            
            
            # Get the most recent messages up to max_context_messages (after initial filtering)
            recent_messages = all_messages[-channel_config.max_context_messages:]
            
            # Separate messages by user from the recent valid messages
            requesting_user_messages = [msg for msg in recent_messages if msg.user_id == requesting_user_id]
            other_messages = [msg for msg in recent_messages if msg.user_id != requesting_user_id]
            
            # Strategy: Guarantee max_user_context_messages from requesting user, then fill remaining space
            # with other messages, keeping chronological order.
            
            # Prioritize messages from the requesting user (most recent first)
            prioritized_messages = []
            
            # Add up to max_user_context_messages from the requesting user
            prioritized_messages.extend(requesting_user_messages[-channel_config.max_user_context_messages:])
            
            # Add other messages, ensuring overall limit is not exceeded and maintaining chronological order
            remaining_space = channel_config.max_context_messages - len(prioritized_messages)
            
            if remaining_space > 0:
                # Get other messages that are not already included (none from requesting_user_messages are yet)
                # Ensure chronological order is maintained
                additional_messages_to_add = sorted(other_messages + requesting_user_messages[:-len(prioritized_messages)], key=lambda x: x.timestamp)
                
                # Add the most recent of these remaining messages that fit
                prioritized_messages.extend(additional_messages_to_add[-remaining_space:])
            
            # Final sort by timestamp to ensure chronological order for the LLM
            prioritized_messages.sort(key=lambda x: x.timestamp)
            
            # Final clip to max_context_messages if, by some chance, more were added
            if len(prioritized_messages) > channel_config.max_context_messages:
                prioritized_messages = prioritized_messages[-channel_config.max_context_messages:]
            
            user_msg_count = len([msg for msg in prioritized_messages if msg.user_id == requesting_user_id])
            other_msg_count = len([msg for msg in prioritized_messages if msg.user_id != requesting_user_id])
            
            logger.debug(f"Generated prioritized context with {len(prioritized_messages)} messages for user {requesting_user_id} ({user_msg_count} user messages, {other_msg_count} other messages)")
            return prioritized_messages
        except Exception as e:
            logger.error(f"Error getting prioritized context: {e}", exc_info=True)
            return []
    
    def _convert_discord_format_to_llm_readable(self, content: str, guild_id: int) -> str:
        """
        Converts Discord-specific formats (mentions, emotes) to LLM-readable text.
        Converts mentions to `@Username` (Discord global username).
        Converts custom Discord emotes to `(emote_name emoji)`.
        Filters out stray numerical IDs near emotes.
        """
        processed_content = content
        user_index = self.load_user_index(guild_id)
        
        # 1. Convert Discord mentions (<@!id>) to @Username (user.name)
        def replace_mention(match):
            user_id = int(match.group(1))
            user_entry = user_index.get(user_id)
            if user_entry:
                # Use the actual Discord username (user.name) as requested
                return f"@{user_entry.username}"
            return match.group(0) # Return original mention if user not found

        processed_content = re.sub(r'<@!?(\d+)>', replace_mention, processed_content)
        
        # 2. Convert custom Discord emotes (<a?:name:id>) to (emote_name emoji)
        def replace_emote(match):
            name = match.group(1) # This is the name part of the emote
            return f"({name} emoji)"
        
        # Regex explanation:
        # <a?       - Matches '<' optionally followed by 'a' (for animated emotes)
        # :(\w+)    - Captures the emote name (one or more word characters)
        # :(\d+)>   - Captures the emote ID (one or more digits) followed by '>'
        processed_content = re.sub(r'<a?:(\w+):(\d+)>', replace_emote, processed_content)
        
        # 3. Filter out stray numerical IDs that might remain next to emotes or punctuation
        # This regex attempts to target leftover IDs, potentially from partial emote matches or similar.
        # It looks for a sequence of digits that might be followed by a period, optionally at the end of a line.
        # It's made more robust to avoid removing valid numbers within sentences.
        # Targets patterns like ":123456789.", ":123456789", " 123456789" (if it's not a standalone meaningful number)
        # We also want to avoid removing numbers that are part of actual text.
        
        # This regex removes numerical IDs at the end of lines or words, especially if they look like Discord IDs.
        # It avoids removing numbers that are part of other words (e.g., "word123").
        processed_content = re.sub(r'\b\d{10,20}\b', '', processed_content) # Remove large numbers typical of Discord IDs
        processed_content = re.sub(r'(?<=\s):(\d+\.?)\s*$', '', processed_content, flags=re.MULTILINE) # Remove :ID. at end of line
        processed_content = re.sub(r'\s+', ' ', processed_content).strip() # Consolidate multiple spaces
        processed_content = re.sub(r'\s+([.,!?:;])', r'\1', processed_content)  # Fix spacing before punctuation

        return processed_content

    def _convert_emote_to_image_url(self, emote_id: int, is_animated: bool = False) -> Optional[str]:
        """
        Placeholder: Converts Discord custom emote ID to a direct image URL.
        Needs to be integrated into content processing if desired later.
        For now, this function is defined but not called.
        """
        # This functionality should ideally be tied to a Discord.py client to query emote details.
        # For a full implementation, the bot would need to know if the emote is animated.
        # Example: return f"https://cdn.discordapp.com/emojis/{emote_id}.{'gif' if is_animated else 'png'}"
        logger.debug(f"Placeholder for emote ID {emote_id} conversion to URL (not currently used)")
        return None

    def format_context_for_llm(self, messages: List[ConversationMessage], guild_id: int = None, channel_id: int = None) -> str:
        """Format conversation messages for LLM context with enhanced user and channel info"""
        try:
            if not messages:
                return ""
            
            context_lines = []
            
            # Add channel context if available
            if guild_id and channel_id:
                channel_context = self.get_channel_context_for_llm(guild_id, channel_id)
                if channel_context:
                    context_lines.append(channel_context)
            
            # Add user context if available (for all unique users in the conversation)
            if guild_id and messages:
                # Collect all unique user IDs from the conversation (excluding bot responses)
                unique_user_ids = list(set(msg.user_id for msg in messages if not msg.is_bot_response))
                
                if unique_user_ids:
                    user_context = self.get_user_context_for_llm(guild_id, unique_user_ids)
                    if user_context:
                        context_lines.append(user_context)

            # NEW: Add pinned messages context
            if guild_id and channel_id:
                pinned_context = self.get_pinned_context_for_llm(guild_id, channel_id)
                if pinned_context:
                    context_lines.append(pinned_context)
            
            # Add conversation history section
            context_lines.append("=== Recent Conversation History ===")
            
            user_index = self.load_user_index(guild_id) # Load user index once for efficiency

            for msg in messages:
                # Determine role/speaker label
                role_label = ""
                if msg.is_self_bot_response:
                    role_label = "Mirrobot" # Use the bot's own name
                elif msg.is_bot_response:
                    role_label = "Other Bot" # Distinguish from self-bot
                else:
                    # For human users, use their actual Discord username (user.name) from index
                    user_entry = user_index.get(msg.user_id)
                    if user_entry and user_entry.username:
                        role_label = user_entry.username # Use user.name as requested
                    else:
                        role_label = msg.username # Fallback to stored display_name if not found in index

                # Convert message content for LLM (mentions, emotes, numeric IDs)
                llm_readable_content = self._convert_discord_format_to_llm_readable(msg.content, guild_id)
                
                # Add image URLs to the content for LLM if present
                if msg.attachment_urls:
                    # Indicate image presence to LLM, can be improved later for multimodal input
                    image_info = f" (Image: {', '.join(msg.attachment_urls)})"
                    llm_readable_content = f"{llm_readable_content}{image_info}".strip()

                context_lines.append(f"{role_label}: {llm_readable_content}")
            
            context_lines.append("=== End of Conversation History ===")
            context_lines.append("")
            
            return "\n".join(context_lines)
        except Exception as e:
            logger.error(f"Error formatting context for LLM: {e}", exc_info=True)
            return "" # Return empty string on error
    
    def should_respond_to_message(self, guild_id: int, channel_id: int, message, bot_user_id: int) -> bool:
        """Determine if the bot should respond to a message in chatbot mode"""
        try:
            # Check if chatbot is enabled for this channel
            if not self.is_chatbot_enabled(guild_id, channel_id):
                return False
            
            # Don't respond to messages from bots (unless it's itself, which should be handled by LLM if needed)
            if message.author.bot and message.author.id != bot_user_id: # Only respond to self-bot's own message if explicitly allowed (not here)
                return False
            
            channel_config = self.get_channel_config(guild_id, channel_id)
            
            # Check for direct mentions of the bot
            if channel_config.auto_respond_to_mentions and bot_user_id in [user.id for user in message.mentions]:
                logger.debug(f"Bot mentioned in message {message.id}, should respond")
                return True
            
            # Check for replies to bot messages
            if channel_config.auto_respond_to_replies and message.reference:
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
            logger.error(f"Error determining if should respond to message: {e}", exc_info=True)
            return False
    
    def prune_old_conversations(self) -> int:
        """Prune old conversation data to save space"""
        pruned_count = 0
        try:
            if not os.path.exists(CONVERSATION_DATA_DIR):
                return 0
            
                        # Iterate through all configured channels to get their specific context window hours
            for guild_key, guild_channels in self.config_cache.get("channels", {}).items():
                guild_id = int(guild_key)
                guild_path = os.path.join(CONVERSATION_DATA_DIR, f"guild_{guild_id}")
                
                if not os.path.isdir(guild_path):
                    continue

                for channel_key, channel_data in guild_channels.items():
                    channel_id = int(channel_key)
                    channel_config = self.get_channel_config(guild_id, channel_id) # Get specific config
                    
                    if not channel_config.auto_prune_enabled:
                        continue # Skip pruning if disabled for this channel

                    file_path = os.path.join(guild_path, f"channel_{channel_id}.json")
                    
                    if not os.path.exists(file_path):
                        continue # No conversation file for this channel

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        messages = data.get("messages", [])
                        
                        # Apply context window filter
                        cutoff_time_window = time.time() - (channel_config.context_window_hours * 3600)
                        filtered_by_time = [msg for msg in messages if msg.get("timestamp", 0) >= cutoff_time_window]

                        # Apply max messages filter
                        if len(filtered_by_time) > channel_config.max_context_messages:
                            filtered_messages = filtered_by_time[-channel_config.max_context_messages:]
                        else:
                            filtered_messages = filtered_by_time
                            
                        if len(filtered_messages) != len(messages):
                            # Update the file with filtered messages
                            data["messages"] = filtered_messages
                            data["last_updated"] = time.time()
                            
                            with open(file_path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, indent=2, ensure_ascii=False)
                            
                            num_pruned_from_file = len(messages) - len(filtered_messages)
                            pruned_count += num_pruned_from_file
                            logger.debug(f"Pruned {num_pruned_from_file} old messages from {file_path}")
                        
                        # Remove empty conversation files
                        if not filtered_messages:
                            os.remove(file_path)
                            logger.debug(f"Removed empty conversation file: {file_path}")
                    
                    except Exception as e:
                        logger.error(f"Error processing conversation file {file_path}: {e}", exc_info=True)
            
            logger.info(f"Total pruned {pruned_count} old conversation messages across all channels.")
            return pruned_count
        except Exception as e:
            logger.error(f"Error pruning conversations: {e}", exc_info=True)
            return 0

    # ==================== USER INDEXING METHODS ====================
    
    def get_user_index_file_path(self, guild_id: int) -> str:
        """Get the file path for user index data"""
        return os.path.join(USER_INDEX_DIR, f"guild_{guild_id}_users.json")
    
    def load_user_index(self, guild_id: int) -> Dict[int, UserIndexEntry]:
        """Load user index for a specific guild"""
        file_path = self.get_user_index_file_path(guild_id)
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    user_index = {}
                    for user_id_str, user_data in data.get("users", {}).items():
                        user_id = int(user_id_str)
                        # Instantiate UserIndexEntry, handling potential missing fields with defaults
                        user_entry_data = {k: user_data.get(k, None) for k in [f.name for f in fields(UserIndexEntry)]}
                        user_index[user_id] = UserIndexEntry(**user_entry_data) # type: ignore
                        # Fill in defaults for any missing fields from old data structure
                        for field in fields(UserIndexEntry):
                            if user_index[user_id].__dict__.get(field.name) is None and field.default is not dataclasses.MISSING:
                                user_index[user_id].__dict__[field.name] = field.default
                    
                    #logger.debug(f"Loaded {len(user_index)} users from index for guild {guild_id}")
                    return user_index
            else:
                return {}
        except Exception as e:
            logger.error(f"Error loading user index for guild {guild_id}: {e}", exc_info=True)
            return {}
    
    def save_user_index(self, guild_id: int, user_index: Dict[int, UserIndexEntry]) -> bool:
        """Save user index for a specific guild"""
        file_path = self.get_user_index_file_path(guild_id)
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert to serializable format
            data = {
                "users": {str(user_id): asdict(user_entry) for user_id, user_entry in user_index.items()},
                "last_updated": time.time(),
                "guild_id": guild_id
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            #logger.debug(f"Saved {len(user_index)} users to index for guild {guild_id}")
            return True
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
        """Update user index with information from any Discord user object
        
        This is a unified function that handles updating the user index from different
        Discord object types: Member, User, Message.author, etc.
        
        Args:
            guild_id: ID of the guild this user belongs to
            user: Discord user object to extract data from
            is_message_author: Whether this user is the author of a message (affects message counter)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_index = self.load_user_index(guild_id)
            user_id = user.id
            current_time = time.time()
            
            # Extract all available data from the user object
            user_data = self.extract_user_data(user, guild_id)
            
            if user_id in user_index:
                # Update existing user
                user_entry = user_index[user_id]
                
                # Always update these fields
                user_entry.last_seen = current_time
                user_entry.username = user_data.get("username", user_entry.username) # Always update username if available
                user_entry.display_name = user_data.get("display_name", user_entry.display_name)
                
                # Update optional fields only if new data is available
                if user_data.get("status") is not None:
                    user_entry.status = user_data["status"]
                
                if user_data.get("avatar_url") is not None:
                    user_entry.avatar_url = user_data["avatar_url"]
                
                if user_data.get("roles") is not None:
                    user_entry.roles = user_data["roles"]
                
                if user_data.get("guild_name") is not None:
                    user_entry.guild_name = user_data["guild_name"]
                
                # Increment message count if this is from a message author
                if is_message_author:
                    user_entry.message_count += 1
            else:
                # Create new user entry
                new_user_data = {
                    "user_id": user_id,
                    "username": user_data.get("username", "Unknown"),
                    "display_name": user_data.get("display_name", "Unknown"),
                    "guild_id": guild_id,
                    "guild_name": user_data.get("guild_name", "Unknown"),
                    "roles": user_data.get("roles", []),
                    "avatar_url": user_data.get("avatar_url", None),
                    "status": user_data.get("status", None),
                    "first_seen": current_time,
                    "last_seen": current_time,
                    "message_count": 1 if is_message_author else 0,
                    "is_bot": user_data.get("is_bot", False)
                }
                
                user_entry = UserIndexEntry(**new_user_data) # type: ignore
                user_index[user_id] = user_entry
                logger.debug(f"Added new user {user_entry.username} (ID: {user_entry.user_id}) to user index for guild {guild_id}")
            
            return self.save_user_index(guild_id, user_index)
            
        except Exception as e:
            logger.error(f"Error updating user index for guild {guild_id}, user {user.id}: {e}", exc_info=True)
            return False
    
    def update_contextual_user_index(self, guild_id: int, channel_id: int) -> bool:
        """Update user index based on current conversation context"""
        try:
            # Load current conversation messages
            messages = self.load_conversation_history(guild_id, channel_id)
            if not messages:
                return True # Nothing to do if no messages

            # Get all relevant user IDs from conversation context
            relevant_user_ids = set()
            
            # Users who sent messages in context (human users)
            for msg in messages:
                if not msg.is_bot_response: # Only count human users who sent messages for index
                    relevant_user_ids.add(msg.user_id)
            
            # Users mentioned in messages (extract from content)
            mention_pattern = r'<@!?(\d+)>'
            for msg in messages:
                mentions = re.findall(mention_pattern, msg.content)
                for mention_id_str in mentions:
                    relevant_user_ids.add(int(mention_id_str))

            # NEW: Add users from pinned messages
            pinned_messages = self.load_pinned_messages(guild_id, channel_id)
            for pin in pinned_messages:
                relevant_user_ids.add(pin.user_id)
                mentions = re.findall(mention_pattern, pin.content)
                for mention_id_str in mentions:
                    relevant_user_ids.add(int(mention_id_str))
            
            # Load existing user index
            user_index = self.load_user_index(guild_id)
            
            # For now, let's ensure the index *only* contains users from `relevant_user_ids`.
            # This is a strong "prune to context" operation.
            final_user_index = {uid: user_index[uid] for uid in relevant_user_ids if uid in user_index}
            
            if len(user_index) != len(final_user_index):
                logger.debug(f"Cleaned up user index for guild {guild_id}, channel {channel_id} (removed {len(user_index) - len(final_user_index)} users not in current context).")
            
            return self.save_user_index(guild_id, final_user_index)
        except Exception as e:
            logger.error(f"Error updating contextual user index: {e}", exc_info=True)
            return False
    
    def cleanup_stale_users(self, guild_id: int) -> int:
        """Remove users from index if they haven't been seen recently"""
        try:
            config = self.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
            cleanup_hours = config.get("user_index_cleanup_hours", 168)  # 7 days default
            cutoff_time = time.time() - (cleanup_hours * 3600)
            
            user_index = self.load_user_index(guild_id)
            if not user_index:
                return 0
            
            removed_count = 0
            users_to_remove = []
            
            for user_id, user_entry in user_index.items():
                if user_entry.last_seen < cutoff_time:
                    users_to_remove.append(user_id)
            
            for user_id in users_to_remove:
                del user_index[user_id]
                removed_count += 1
            
            if removed_count > 0:
                self.save_user_index(guild_id, user_index)
                logger.info(f"Cleaned up {removed_count} stale users from guild {guild_id}")
            
            return removed_count
        except Exception as e:
            logger.error(f"Error cleaning up stale users for guild {guild_id}: {e}", exc_info=True)
            return 0
    
    def cleanup_all_stale_users(self, bot_guilds) -> int:
        """Clean up stale users across all guilds"""
        try:
            total_cleaned = 0
            for guild in bot_guilds:
                cleaned = self.cleanup_stale_users(guild.id)
                total_cleaned += cleaned
            
            if total_cleaned > 0:
                logger.info(f"Cleaned up {total_cleaned} stale users across all guilds")
            
            return total_cleaned
        except Exception as e:
            logger.error(f"Error during cleanup of all stale users: {e}", exc_info=True)
            return 0
    
    def get_user_context_for_llm(self, guild_id: int, user_ids: List[int]) -> str:
        """Get user context information for LLM"""
        try:
            user_index = self.load_user_index(guild_id)
            if not user_index or not user_ids:
                return ""
            
            context_lines = []
            context_lines.append("=== Known Users ===")
            
            for user_id in user_ids:
                if user_id in user_index:
                    user = user_index[user_id]
                    # Start with ID, display name and username
                    # Use the actual Discord username (user.name) as the primary identifier
                    user_info = [f"• User: @{user.username} (ID: {user.user_id})"]
                    
                    # Add display name (nickname) if it differs from username
                    if user.username != user.display_name:
                        user_info.append(f"  Nickname: {user.display_name}")
                    
                    # Add roles if available (NO LIMIT NOW)
                    if user.roles:
                        user_info.append(f"  Roles: {', '.join(user.roles)}")
                    
                    # Add status if available
                    #if user.status:
                        #user_info.append(f"  Status: {user.status}")
                    
                    # Join all info with newlines
                    context_lines.append("\n".join(user_info))
            
            context_lines.append("=== End of Known Users ===")
            context_lines.append("")
            
            return "\n".join(context_lines)
        except Exception as e:
            logger.error(f"Error getting user context for LLM: {e}", exc_info=True)
            return ""
    
    # ==================== CHANNEL INDEXING METHODS ====================
    
    def get_channel_index_file_path(self, guild_id: int) -> str:
        """Get the file path for channel index data"""
        return os.path.join(CHANNEL_INDEX_DIR, f"guild_{guild_id}_channels.json")
    
    def load_channel_index(self, guild_id: int) -> Dict[int, ChannelIndexEntry]:
        """Load channel index for a specific guild"""
        file_path = self.get_channel_index_file_path(guild_id)
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    channel_index = {}
                    for channel_id_str, channel_data in data.get("channels", {}).items():
                        channel_id = int(channel_id_str)
                        # Instantiate ChannelIndexEntry, handling potential missing fields with defaults
                        channel_entry_data = {k: channel_data.get(k, None) for k in [f.name for f in fields(ChannelIndexEntry)]}
                        channel_index[channel_id] = ChannelIndexEntry(**channel_entry_data) # type: ignore
                        # Fill in defaults for any missing fields from old data structure
                        for field in fields(ChannelIndexEntry):
                            # Check if field has a default value (not MISSING) and apply it if needed                            if channel_index[channel_id].__dict__.get(field.name) is None:
                                if field.default_factory is not dataclasses.MISSING:
                                    # Use default_factory if available
                                    channel_index[channel_id].__dict__[field.name] = field.default_factory()
                                elif field.default is not dataclasses.MISSING:
                                    # Use default value if available
                                    channel_index[channel_id].__dict__[field.name] = field.default
                    
                    logger.debug(f"Loaded {len(channel_index)} channels from index for guild {guild_id}")
                    return channel_index
            else:
                return {}
        except Exception as e:
            logger.error(f"Error loading channel index for guild {guild_id}: {e}", exc_info=True)
            return {}
    
    def save_channel_index(self, guild_id: int, channel_index: Dict[int, ChannelIndexEntry]) -> bool:
        """Save channel index for a specific guild"""
        file_path = self.get_channel_index_file_path(guild_id)
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert to serializable format
            data = {
                "channels": {str(channel_id): asdict(channel_entry) for channel_id, channel_entry in channel_index.items()},
                "last_updated": time.time(),
                "guild_id": guild_id
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved {len(channel_index)} channels to index for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving channel index for guild {guild_id}: {e}", exc_info=True)
            return False
    
    def index_channel(self, channel) -> ChannelIndexEntry:
        """Create a channel index entry from a Discord channel object"""
        try:
            current_time = time.time()
            
            # Get channel type as string (e.g., 'text_channel', 'public_thread')
            channel_type = str(channel.type).replace('channel_type.', '') # Clean up enum string
            
            # Topic: For TextChannels, it's directly available. For Threads, their 'name' is often their topic.
            topic = None
            if hasattr(channel, 'topic') and channel.topic: # For TextChannels, VoiceChannels etc.
                topic = channel.topic
            elif isinstance(channel, discord.Thread): # For Threads, their name serves as a de-facto topic
                topic = channel.name 
            
            # Category name: For TextChannels, directly available. For Threads, it's their parent's category.
            category_name = None
            if hasattr(channel, 'category') and channel.category: # For TextChannels
                category_name = channel.category.name
            elif isinstance(channel, discord.Thread) and channel.parent: # For Threads, check parent's category
                if hasattr(channel.parent, 'category') and channel.parent.category:
                    category_name = channel.parent.category.name
            
            # NSFW status: For TextChannels, directly available. For Threads, it's their parent's NSFW status.
            is_nsfw = False # Default to False
            if hasattr(channel, 'nsfw'): # For TextChannels etc.
                is_nsfw = channel.nsfw
            elif isinstance(channel, discord.Thread) and channel.parent: # For Threads, use parent's nsfw status
                if hasattr(channel.parent, 'nsfw'):
                    is_nsfw = channel.parent.nsfw
            
            # Get guild name and description
            guild_name = channel.guild.name if hasattr(channel.guild, 'name') else None
            guild_description = channel.guild.description if hasattr(channel.guild, 'description') else None
            
            return ChannelIndexEntry(
                channel_id=channel.id,
                guild_id=channel.guild.id,
                channel_name=channel.name,
                channel_type=channel_type,
                guild_name=guild_name,
                guild_description=guild_description,
                topic=topic,
                category_name=category_name,
                is_nsfw=is_nsfw,
                last_indexed=current_time,
                message_count=0
            )
        except Exception as e:
            logger.error(f"Error indexing channel {getattr(channel, 'id', 'Unknown')}: {e}", exc_info=True)
            raise
    
    def get_channel_context_for_llm(self, guild_id: int, channel_id: int) -> str:
        """Get channel context information for LLM"""
        try:
            channel_index = self.load_channel_index(guild_id)
            if not channel_index or channel_id not in channel_index:
                return ""
            
            channel = channel_index[channel_id]
            context_lines = []
            context_lines.append("=== Current Channel Info ===")
            
            # Add server (guild) name and description if available
            if channel.guild_name:
                context_lines.append(f"Server: {channel.guild_name}")
                if channel.guild_description:
                    context_lines.append(f"Description: {channel.guild_description}")
            
            context_lines.append(f"Channel: #{channel.channel_name}")
            context_lines.append(f"Type: {channel.channel_type}")
            
            if channel.topic:
                context_lines.append(f"Topic: {channel.topic}")
            
            if channel.category_name:
                context_lines.append(f"Category: {channel.category_name}")
            
            if channel.is_nsfw:
                context_lines.append("Note: This is an NSFW channel")
            
            context_lines.append("=== End of Channel Info ===")
            context_lines.append("")
            
            return "\n".join(context_lines)
        except Exception as e:
            logger.error(f"Error getting channel context for LLM: {e}", exc_info=True)
            return ""

    # ==================== PINNED MESSAGES METHODS (NEW) ====================
    def get_pinned_messages_file_path(self, guild_id: int, channel_id: int) -> str:
        """Get the file path for pinned messages data"""
        return os.path.join(PINNED_MESSAGES_DIR, f"guild_{guild_id}_channel_{channel_id}_pins.json")

    async def index_pinned_messages(self, guild_id: int, channel_id: int, channel: discord.abc.Messageable) -> int:
        """Fetches and indexes pinned messages for a channel.
        Only applicable to TextChannels (including threads as they derive from TextChannels).
        """
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.debug(f"Skipping pinned message indexing for non-text/thread channel {channel.name} ({channel_id})")
            return 0

        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        current_pins = []
        indexed_count = 0

        try:
            # Clear existing pins for this channel before re-indexing
            # This ensures only currently pinned messages are stored
            if os.path.exists(file_path):
                os.remove(file_path) # Simpler than loading and merging for now
                logger.debug(f"Cleared old pinned messages file for channel {channel_id}")

            pins = await channel.pins()
            logger.debug(f"Fetched {len(pins)} pinned messages from #{channel.name}")

            for message in pins:
                # Decide if to include bot's own pinned messages or only human/other bots
                if message.author.bot and message.author.id != self.bot_user_id:
                    # Skip other bot's pinned messages if desired, or adjust logic
                    # For now, index only human and self-bot pins
                    continue

                cleaned_content, image_urls, embed_urls = self._process_discord_message_for_context(message)
                
                # Check validity using the existing filter logic (using ConversationMessage for compatibility)
                is_valid, _ = self._is_valid_context_message(
                    ConversationMessage(
                        user_id=message.author.id, username=message.author.display_name,
                        content=cleaned_content, timestamp=message.created_at.timestamp(),
                        message_id=message.id, is_bot_response=message.author.bot,
                        is_self_bot_response=(message.author.id == self.bot_user_id),
                        attachment_urls=image_urls, embed_urls=embed_urls
                    )
                )

                if is_valid:
                    # Update user index for pinned message authors as well
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
                    logger.debug(f"Skipped invalid pinned message {message.id} for indexing (content filter).")

            # Save the new list of pinned messages
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            data_to_save = {
                "pins": [asdict(pin) for pin in current_pins],
                "last_indexed": time.time(),
                "guild_id": guild_id,
                "channel_id": channel_id
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Indexed {indexed_count} pinned messages for #{channel.name} ({channel_id})")
            return indexed_count

        except discord.errors.Forbidden:
            logger.warning(f"Missing permissions to read pins in channel {channel.name} ({channel_id}) in guild {guild_id}")
            return 0
        except Exception as e:
            logger.error(f"Error indexing pinned messages for channel {channel_id}: {e}", exc_info=True)
            return 0

    def load_pinned_messages(self, guild_id: int, channel_id: int) -> List[PinnedMessage]:
        """Loads pinned messages from file for a specific channel."""
        file_path = self.get_pinned_messages_file_path(guild_id, channel_id)
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [PinnedMessage(**msg) for msg in data.get("pins", [])]
            return []
        except Exception as e:
            logger.error(f"Error loading pinned messages for channel {channel_id}: {e}", exc_info=True)
            return []

    def get_pinned_context_for_llm(self, guild_id: int, channel_id: int) -> str:
        """Formats pinned messages for LLM context."""
        pins = self.load_pinned_messages(guild_id, channel_id)
        if not pins:
            return ""
        
        context_lines = []
        context_lines.append("=== Pinned Messages ===")
        context_lines.append("Note: These messages are important channel context.")

        # Sort pins by timestamp (oldest first, like conversation history)
        pins.sort(key=lambda x: x.timestamp)

        user_index = self.load_user_index(guild_id)

        for pin in pins:
            # Determine role/speaker label similar to conversation history
            role_label = ""
            user_entry = user_index.get(pin.user_id)
            if user_entry and user_entry.username:
                role_label = user_entry.username
            else:
                role_label = pin.username # Fallback to stored display_name

            llm_readable_content = self._convert_discord_format_to_llm_readable(pin.content, guild_id)
            
            if pin.attachment_urls:
                image_info = f" (Image: {', '.join(pin.attachment_urls)})"
                llm_readable_content = f"{llm_readable_content}{image_info}".strip()

            context_lines.append(f"{role_label}: {llm_readable_content}")
        
        context_lines.append("=== End of Pinned Messages ===")
        context_lines.append("")
        
        return "\n".join(context_lines)
    # ==================== END PINNED MESSAGES METHODS ====================


    # ==================== FOCUSED INDEXING METHODS ====================
    async def index_chatbot_channel(self, guild_id: int, channel_id: int, channel) -> bool:
        """Index the specific channel where chatbot is enabled and fetch recent message history"""
        try:
            # Index channel metadata
            channel_index = self.load_channel_index(guild_id)
            channel_entry = self.index_channel(channel) # type: ignore
            channel_index[channel_id] = channel_entry
            
            result = self.save_channel_index(guild_id, channel_index)
            if not result:
                logger.error(f"Failed to save channel index for #{channel.name}")
                return False
            
            # Get channel configuration to determine how many messages to fetch
            channel_config = self.get_channel_config(guild_id, channel_id)
            max_messages = channel_config.max_context_messages
            
            logger.debug(f"Fetching last {max_messages} messages from #{channel.name} for chatbot context")
            
            # Fetch recent messages from the channel
            messages_indexed = 0
            messages_skipped = 0
            messages_failed = 0
            messages_fetched = 0
            try:
                # Fetch messages, trying to get more than max_messages to allow filtering.
                # However, Discord's API limits how many messages can be fetched in one call.
                # `limit=max_messages` is appropriate.
                async for message in channel.history(limit=max_messages, oldest_first=False):
                    messages_fetched += 1
                    
                    # Filter out system messages. `discord.MessageType.default` (0) and `discord.MessageType.reply` (19) are standard.
                    # Other types include `discord.MessageType.channel_follow_add`, `pins_add`, `guild_boost`, etc.
                    # We usually only want standard user/bot messages for conversation history.
                    if message.type not in [discord.MessageType.default, discord.MessageType.reply]:
                        messages_skipped += 1
                        logger.debug(f"Skipped system message {message.id} of type {message.type}")
                        continue
                    
                    # Add each message to conversation history
                    # This will also index users who sent the messages, mentioned users, etc.
                    # Ensure bot_user_id is available for this call
                    if self.bot_user_id is None:
                        logger.warning(f"Bot user ID not set in ChatbotManager, cannot correctly mark self-bot messages.")
                        # Attempt to get it from a dummy message or a placeholder
                        # For indexing, this might be okay if it's set later by main bot loop.
                        # But for adding messages here, it's better to have it.
                        # For now, it will default to `is_self_bot_response=False` if bot_user_id is None.
                        bot_id_for_indexing = 0 # Fallback
                    else:
                        bot_id_for_indexing = self.bot_user_id

                    success = self.add_message_to_conversation(guild_id, channel_id, message, bot_id_for_indexing)
                    if success:
                        messages_indexed += 1
                        
                        # Index users mentioned in the message
                        for mentioned_user in message.mentions:
                            self.update_user_index(guild_id, mentioned_user)
                        
                        # Index user who was replied to (if this is a reply)
                        if message.reference and message.reference.resolved:
                            if hasattr(message.reference.resolved, 'author'):
                                self.update_user_index(guild_id, message.reference.resolved.author)
                    else:
                        messages_failed += 1
                        logger.warning(f"Failed to add message {message.id} to conversation history")
                
                logger.info(f"Indexed chatbot channel #{channel.name}: {messages_indexed}/{messages_fetched} messages indexed "
                           f"({messages_skipped} skipped, {messages_failed} failed) for guild {guild_id}")
            except Exception as e:
                logger.error(f"Error fetching message history from #{channel.name}: {e}", exc_info=True)
                # Continue anyway - at least we have the channel metadata indexed
                logger.info(f"Indexed chatbot channel #{channel.name} (metadata only) for guild {guild_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error indexing chatbot channel: {e}", exc_info=True)
            return False
    
    def cleanup_conversation_context(self, guild_id: int, channel_id: int) -> int:
        """Clean up user index to only include users relevant to current conversation"""
        try:
            # Update contextual user index (this handles the cleanup)
            self.update_contextual_user_index(guild_id, channel_id)
            
            # Load updated index to count remaining users
            user_index = self.load_user_index(guild_id)
            logger.info(f"Cleaned up user index for guild {guild_id}, {len(user_index)} users remain in context")
            
            return len(user_index)        
        except Exception as e:
            logger.error(f"Error cleaning up conversation context: {e}", exc_info=True)
            return 0
    
    def get_indexing_stats(self, guild_id: int) -> Dict[str, int]:
        """Get statistics about current indexing for a guild"""
        try:
            user_index = self.load_user_index(guild_id)
            channel_index = self.load_channel_index(guild_id)
            
            return {
                "users_indexed": len(user_index),
                "channels_indexed": len(channel_index),
                "total_user_messages": sum(user.message_count for user in user_index.values()) if user_index else 0
            }
        except Exception as e:
            logger.error(f"Error getting indexing stats: {e}", exc_info=True)
            return {
                "users_indexed": 0,
                "channels_indexed": 0,
                "total_user_messages": 0
            }
    
    def get_all_chatbot_enabled_channels(self, guilds) -> List[Tuple[int, int]]:
        """Get all chatbot-enabled channels across all guilds
        
        Args:
            guilds: List of discord.Guild objects to check
            
        Returns:
            List of tuples containing (guild_id, channel_id) for enabled channels
        """
        enabled_channels = []
        
        try:
            config = self.config_cache
            channels_config = config.get("channels", {})
            
            for guild in guilds:
                guild_key = str(guild.id)
                if guild_key in channels_config:
                    for channel_key, channel_data in channels_config[guild_key].items():
                        if channel_data.get("enabled", False):
                            try:
                                channel_id = int(channel_key)
                                # Verify the channel still exists
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    enabled_channels.append((guild.id, channel_id))
                                else:
                                    logger.debug(f"Skipping deleted channel {channel_id} in guild {guild.name}")
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Invalid channel ID '{channel_key}' in guild {guild.name}: {e}")
                                
        except Exception as e:
            logger.error(f"Error getting chatbot-enabled channels: {e}", exc_info=True)
            
        return enabled_channels

    def check_duplicate_message(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Check if a message is already in the conversation history
        
        Args:
            guild_id: ID of the guild
            channel_id: ID of the channel
            message_id: ID of the message to check
            
        Returns:
            True if message already exists, False otherwise
        """
        try:
            file_path = self.get_conversation_file_path(guild_id, channel_id)
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_messages = data.get("messages", [])
                    
                    # Check if this message ID already exists
                    for msg in existing_messages:
                        if msg.get("message_id") == message_id:
                            #logger.debug(f"Message {message_id} already in conversation history")
                            return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking for duplicate message: {e}", exc_info=True)
            return False

# Global chatbot manager instance
chatbot_manager = ChatbotManager()