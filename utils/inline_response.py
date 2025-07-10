import re
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse
import discord

from utils.chatbot.models import ConversationMessage, ContentPart
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger
from utils.chatbot.manager import chatbot_manager # Import the global manager

logger = get_logger()

CONFIG_FILE = "data/inline_response_config.json"

@dataclass
class InlineResponseConfig:
    """Configuration for the Inline Response feature."""
    enabled: bool = False
    trigger_on_start_only: bool = True
    model_type: str = "ask"
    context_messages: int = 30
    user_context_messages: int = 15
    # New permission fields
    role_whitelist: List[int] = None
    member_whitelist: List[int] = None
    role_blacklist: List[int] = None
    member_blacklist: List[int] = None

    def __post_init__(self):
        # Ensure lists are initialized correctly if they are None
        if self.role_whitelist is None:
            self.role_whitelist = []
        if self.member_whitelist is None:
            self.member_whitelist = []
        if self.role_blacklist is None:
            self.role_blacklist = []
        if self.member_blacklist is None:
            self.member_blacklist = []

DEFAULT_CONFIG = asdict(InlineResponseConfig())

class InlineResponseManager:
    """Manages inline response configuration."""

    def __init__(self, storage_manager: JsonStorageManager):
        self.storage_manager = storage_manager
        self.config_cache = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        config = self.storage_manager.read(CONFIG_FILE)
        if not config:
            logger.info("No inline response config found, creating a default one.")
            # New structure: servers contain server-level settings and channel-specific overrides
            default_config = {"servers": {}}
            self.save_config(default_config)
            return default_config
        
        logger.debug("Loaded inline response configuration.")
        return config

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """Save configuration to file."""
        config_to_save = config if config is not None else self.config_cache
        if self.storage_manager.write(CONFIG_FILE, config_to_save):
            self.config_cache = config_to_save
            logger.debug("Saved inline response configuration.")
            return True
        return False

    def get_channel_config(self, guild_id: int, channel_id: int) -> "InlineResponseConfig":
        """
        Get the effective configuration for a specific channel, applying the hierarchy.
        Hierarchy: Channel settings are combined with (union) or override server settings.
        - For permission lists (whitelists/blacklists), the lists are combined (union).
        - For other settings, channel-specific values override server-wide values.
        """
        guild_key = str(guild_id)
        channel_key = str(channel_id)
        
        # 1. Start with hardcoded defaults
        effective_config_dict = DEFAULT_CONFIG.copy()

        # 2. Layer server-wide settings on top
        server_settings = self.config_cache.get("servers", {}).get(guild_key, {}).get("server_settings", {})
        effective_config_dict.update(server_settings)

        # 3. Layer channel-specific settings, handling list unions
        channel_settings = self.config_cache.get("servers", {}).get(guild_key, {}).get("channels", {}).get(channel_key, {})
        
        # Combine permission lists
        server_role_wl = set(server_settings.get('role_whitelist', []))
        channel_role_wl = set(channel_settings.get('role_whitelist', []))
        effective_config_dict['role_whitelist'] = list(server_role_wl.union(channel_role_wl))

        server_member_wl = set(server_settings.get('member_whitelist', []))
        channel_member_wl = set(channel_settings.get('member_whitelist', []))
        effective_config_dict['member_whitelist'] = list(server_member_wl.union(channel_member_wl))

        server_role_bl = set(server_settings.get('role_blacklist', []))
        channel_role_bl = set(channel_settings.get('role_blacklist', []))
        effective_config_dict['role_blacklist'] = list(server_role_bl.union(channel_role_bl))

        server_member_bl = set(server_settings.get('member_blacklist', []))
        channel_member_bl = set(channel_settings.get('member_blacklist', []))
        effective_config_dict['member_blacklist'] = list(server_member_bl.union(channel_member_bl))

        # Update other settings with channel-specific overrides
        for key, value in channel_settings.items():
            if key not in ['role_whitelist', 'member_whitelist', 'role_blacklist', 'member_blacklist']:
                effective_config_dict[key] = value
        
        # Filter to only include keys present in the dataclass
        config_keys = {f.name for f in fields(InlineResponseConfig)}
        filtered_config = {k: v for k, v in effective_config_dict.items() if k in config_keys}
        
        return InlineResponseConfig(**filtered_config)

    def get_specific_config(self, guild_id: int, channel_id: int = None) -> Dict[str, Any]:
        """
        Gets the raw configuration dictionary for a specific level (server or channel) without the hierarchy.
        This is used when editing a config, to ensure we're not modifying a merged config.
        Returns a copy of the raw config dict.
        """
        guild_key = str(guild_id)
        
        if channel_id:
            channel_key = str(channel_id)
            return self.config_cache.get("servers", {}).get(guild_key, {}).get("channels", {}).get(channel_key, {}).copy()
        else:
            return self.config_cache.get("servers", {}).get(guild_key, {}).get("server_settings", {}).copy()

    def set_config(self, guild_id: int, new_settings: Dict[str, Any], channel_id: int = None):
        """
        Set or update configuration for a server or a specific channel.
        It merges the new settings with the existing ones.
        If channel_id is None, sets the server-wide configuration.
        Otherwise, sets the configuration for the specified channel.
        """
        guild_key = str(guild_id)
        
        # Ensure the server entry exists
        if "servers" not in self.config_cache:
            self.config_cache["servers"] = {}
        if guild_key not in self.config_cache["servers"]:
            self.config_cache["servers"][guild_key] = {"server_settings": {}, "channels": {}}

        if channel_id:
            # Setting for a specific channel
            channel_key = str(channel_id)
            if "channels" not in self.config_cache["servers"][guild_key]:
                self.config_cache["servers"][guild_key]["channels"] = {}
            
            # Get current settings and update them
            current_settings = self.config_cache["servers"][guild_key]["channels"].get(channel_key, {})
            current_settings.update(new_settings)
            self.config_cache["servers"][guild_key]["channels"][channel_key] = current_settings
        else:
            # Setting for the whole server
            current_settings = self.config_cache["servers"][guild_key].get("server_settings", {})
            current_settings.update(new_settings)
            self.config_cache["servers"][guild_key]["server_settings"] = current_settings
            
        return self.save_config()
            
    def is_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if inline response is enabled for a specific channel."""
        return self.get_channel_config(guild_id, channel_id).enabled

    async def build_context(self, message: discord.Message) -> List[ConversationMessage]:
        """Builds a context for an inline response."""
        config = self.get_channel_config(message.guild.id, message.channel.id)
        
        all_messages: Dict[int, discord.Message] = {}

        # 1. Fetch replied-to message
        if message.reference and message.reference.message_id:
            try:
                replied_to_message = await message.channel.fetch_message(message.reference.message_id)
                all_messages[replied_to_message.id] = replied_to_message
            except discord.NotFound:
                logger.warning(f"Could not find replied-to message {message.reference.message_id}")
            except discord.HTTPException as e:
                logger.error(f"Failed to fetch replied-to message: {e}")

        # 2. Fetch channel history
        if config.context_messages > 0:
            async for history_message in message.channel.history(limit=config.context_messages, before=message):
                all_messages[history_message.id] = history_message

        # 3. Fetch user history and the messages they replied to
        if config.user_context_messages > 0:
            user_messages_found = 0
            user_messages_for_reply_check = []
            # We search a bit wider to find user messages
            async for history_message in message.channel.history(limit=100, before=message):
                if history_message.author.id == message.author.id:
                    if history_message.id not in all_messages:
                        all_messages[history_message.id] = history_message
                        user_messages_for_reply_check.append(history_message)
                    user_messages_found += 1
                    if user_messages_found >= config.user_context_messages:
                        break
            
            # For each of the user's messages, fetch any message they replied to
            for user_msg in user_messages_for_reply_check:
                if user_msg.reference and user_msg.reference.message_id:
                    if user_msg.reference.message_id not in all_messages:
                        try:
                            # Use resolved if available, otherwise fetch
                            if user_msg.reference.resolved and isinstance(user_msg.reference.resolved, discord.Message):
                                replied_to_message = user_msg.reference.resolved
                            else:
                                replied_to_message = await message.channel.fetch_message(user_msg.reference.message_id)
                            all_messages[replied_to_message.id] = replied_to_message
                        except discord.NotFound:
                            logger.warning(f"Could not find replied-to message {user_msg.reference.message_id} from user's history.")
                        except discord.HTTPException as e:
                            logger.error(f"Failed to fetch replied-to message {user_msg.reference.message_id}: {e}")
        
        # Add the trigger message itself
        all_messages[message.id] = message

        # 4. Sort chronologically
        sorted_messages = sorted(all_messages.values(), key=lambda m: m.created_at)

        # 5. Convert to ConversationMessage
        context_messages = []
        for msg in sorted_messages:
            # Use the centralized function from the chatbot manager's conversation utility
            cleaned_content, image_urls, _ = await chatbot_manager.conversation_manager._process_discord_message_for_context(msg)
            
            multimodal_content = []
            if cleaned_content:
                multimodal_content.append(ContentPart(type="text", text=cleaned_content))
            for url in image_urls:
                multimodal_content.append(ContentPart(type="image_url", image_url={"url": url}))

            if not multimodal_content:
                continue

            context_messages.append(ConversationMessage(
                user_id=msg.author.id,
                username=msg.author.display_name,
                content=cleaned_content,
                timestamp=msg.created_at.timestamp(),
                message_id=msg.id,
                is_bot_response=msg.author.bot,
                is_self_bot_response=(msg.author.id == message.guild.me.id),
                referenced_message_id=getattr(msg.reference, 'message_id', None) if msg.reference else None,
                attachment_urls=image_urls,
                multimodal_content=multimodal_content
            ))
            
        return context_messages


def split_message(text: str, limit: int = 2000) -> List[str]:
    """
    Splits a string of text into a list of smaller strings, each under the
    specified character limit, without breaking words or formatting.
    Returns an empty list if the input text is empty or just whitespace.
    """
    if not text or text.isspace():
        logger.warning("split_message received empty or whitespace-only text. Returning empty list.")
        return []

    if len(text) <= limit:
        return [text]

    chunks = []
    current_chunk = ""
    
    # Preserve paragraphs by splitting by them first
    paragraphs = text.split('\n\n')
    
    for i, paragraph in enumerate(paragraphs):
        # If a single paragraph is over the limit, split it by lines
        if len(paragraph) > limit:
            lines = paragraph.split('\n')
            for line in lines:
                if len(current_chunk) + len(line) + 1 > limit:
                    chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    current_chunk += f"\n{line}"
            continue # Move to the next paragraph

        # Check if adding the next paragraph fits
        if len(current_chunk) + len(paragraph) + 2 > limit:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += f"\n\n{paragraph}"
            else:
                current_chunk = paragraph
        
        # Add paragraph separator back if it's not the last one
        if i < len(paragraphs) - 1:
            # This check is to avoid adding separators if the next chunk starts fresh
            if len(current_chunk) + 2 <= limit:
                 pass # Separator is handled by the logic above

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Final check for any chunks that might still be over the limit due to long lines
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > limit:
            # Force split the oversized chunk by words
            words = chunk.split(' ')
            new_chunk = ""
            for word in words:
                # If a single word is over the limit, it must be split forcefully
                if len(word) > limit:
                    if new_chunk: # Add whatever was in new_chunk before this monster word
                        final_chunks.append(new_chunk.strip())
                    # Split the monster word itself
                    for i in range(0, len(word), limit):
                        final_chunks.append(word[i:i+limit])
                    new_chunk = "" # Reset new_chunk
                    continue

                if len(new_chunk) + len(word) + 1 > limit:
                    if new_chunk: # Ensure we don't add empty strings
                        final_chunks.append(new_chunk.strip())
                    new_chunk = word
                else:
                    if new_chunk:
                        new_chunk += f" {word}"
                    else:
                        new_chunk = word
            if new_chunk: # Add the last part
                final_chunks.append(new_chunk.strip())
        else:
            final_chunks.append(chunk)
            
    # Final filter to remove any empty strings that might have slipped through
    return [c for c in final_chunks if c and not c.isspace()]
