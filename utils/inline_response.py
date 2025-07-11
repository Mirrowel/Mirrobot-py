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
    use_streaming: bool = True
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
        """
        Builds a context for an inline response by efficiently fetching and processing message history.
        1.  Fetches a large batch of recent messages.
        2.  Identifies required context messages (trigger, replies, user history).
        3.  Enters a "fetch until found" loop if any replied-to messages are not in the initial batch.
        4.  Processes all messages in-memory to stitch bot responses and format the final context.
        """
        config = self.get_channel_config(message.guild.id, message.channel.id)
        
        # In-memory store for all messages fetched, keyed by ID for fast lookups.
        message_pool: Dict[int, discord.Message] = {}
        
        # Set of message IDs that are required for full context (mainly replies).
        required_message_ids = set()

        # --- Step 1: Initial Batch Fetch ---
        # Fetch a single large batch of messages to minimize initial API calls.
        # This batch will serve as the primary source for context building.
        history_limit = 100
        oldest_message_in_pool = message
        
        async for history_msg in message.channel.history(limit=history_limit, before=message):
            message_pool[history_msg.id] = history_msg
            if history_msg.created_at < oldest_message_in_pool.created_at:
                oldest_message_in_pool = history_msg
        
        # Add the triggering message itself to the pool.
        message_pool[message.id] = message

        # --- Step 2: Gather Core Context & Identify Missing Replies ---
        # This set will hold the messages that form the core of our context.
        context_messages: Dict[int, discord.Message] = {message.id: message}

        # Add user-specific messages from the initial pool.
        user_messages_found = 0
        for msg in sorted(message_pool.values(), key=lambda m: m.created_at, reverse=True):
            if msg.author.id == message.author.id and msg.id not in context_messages:
                if user_messages_found < config.user_context_messages:
                    context_messages[msg.id] = msg
                    user_messages_found += 1
                else:
                    break
        
        # Add general channel messages from the initial pool.
        channel_messages_found = 0
        for msg in sorted(message_pool.values(), key=lambda m: m.created_at, reverse=True):
            if msg.id not in context_messages:
                if channel_messages_found < config.context_messages:
                    context_messages[msg.id] = msg
                    channel_messages_found += 1
                else:
                    break

        # Identify all unique replied-to message IDs from our current context.
        for msg in context_messages.values():
            if msg.reference and msg.reference.message_id:
                required_message_ids.add(msg.reference.message_id)

        # --- Step 3: "Fetch Until Found" Loop for Deep Replies ---
        # If a required reply is not in our pool, fetch older messages until it is found.
        # This ensures context is complete, even for replies to very old messages.
        fetch_attempts = 0
        max_fetch_attempts = 10 # Safety break to prevent infinite loops
        
        missing_ids = required_message_ids - message_pool.keys()
        
        while missing_ids and fetch_attempts < max_fetch_attempts:
            logger.debug(f"Missing {len(missing_ids)} replied-to messages. Fetching older history...")
            fetch_attempts += 1
            
            new_messages_fetched = 0
            async for history_msg in message.channel.history(limit=history_limit, before=oldest_message_in_pool):
                if history_msg.id not in message_pool:
                    message_pool[history_msg.id] = history_msg
                    new_messages_fetched += 1
                    if history_msg.created_at < oldest_message_in_pool.created_at:
                        oldest_message_in_pool = history_msg
            
            if new_messages_fetched == 0:
                logger.warning("No more messages in channel history, but some replies are still missing.")
                break # Exit if channel history is exhausted.

            missing_ids = required_message_ids - message_pool.keys()

        # Add all found replies to our final context set.
        for msg_id in required_message_ids:
            if msg_id in message_pool and msg_id not in context_messages:
                context_messages[msg_id] = message_pool[msg_id]

        # --- Step 4: Proactive User Indexing ---
        # Ensure all users in the context are fully indexed before formatting.
        author_ids_in_context = {msg.author.id for msg in context_messages.values()}
        user_index = await chatbot_manager.index_manager.load_user_index(message.guild.id)
        
        missing_user_ids = {uid for uid in author_ids_in_context if uid not in user_index}
        
        if missing_user_ids:
            logger.debug(f"Found {len(missing_user_ids)} users not in index. Fetching full member data.")
            newly_fetched_members = []
            for user_id in missing_user_ids:
                try:
                    member = await message.guild.fetch_member(user_id)
                    newly_fetched_members.append(member)
                except discord.NotFound:
                    logger.warning(f"Could not fetch member with ID {user_id} for inline context; they may have left the server.")
                except Exception as e:
                    logger.error(f"Error fetching member {user_id}: {e}", exc_info=True)
            
            if newly_fetched_members:
                await chatbot_manager.index_manager.update_users_bulk(message.guild.id, newly_fetched_members)
                logger.debug(f"Updated user index with {len(newly_fetched_members)} newly fetched members.")

        # --- Step 5: In-Memory Bot Message Stitching ---
        # The message_pool contains a wide swath of channel history. We can search it
        # to stitch together multi-part bot messages without any new API calls.
        final_messages: Dict[int, discord.Message] = context_messages.copy()
        
        # Create a sorted list of all messages in the pool for efficient searching.
        sorted_pool = sorted(message_pool.values(), key=lambda m: m.created_at)
        pool_indices = {msg.id: i for i, msg in enumerate(sorted_pool)}

        # Check messages that are already in our core context.
        messages_to_check = list(context_messages.values())
        
        for msg in messages_to_check:
            if msg.author.bot:
                # This message is from a bot. Search for its other parts in the pool.
                current_index = pool_indices.get(msg.id)
                if current_index is None: continue

                # Search backwards from the message's position in the sorted pool.
                for i in range(current_index - 1, -1, -1):
                    prev_msg = sorted_pool[i]
                    # Check if the previous message is from the same bot and within a close time frame.
                    if prev_msg.author.id == msg.author.id and (sorted_pool[i+1].created_at - prev_msg.created_at).total_seconds() < 10:
                        if prev_msg.id not in final_messages:
                            final_messages[prev_msg.id] = prev_msg
                    else:
                        # Break if the chain is interrupted by another author or a time gap.
                        break
                
                # Search forwards from the message's position.
                for i in range(current_index + 1, len(sorted_pool)):
                    next_msg = sorted_pool[i]
                    # Check if the next message is a continuation from the same bot.
                    if next_msg.author.id == msg.author.id and (next_msg.created_at - sorted_pool[i-1].created_at).total_seconds() < 10:
                        if next_msg.id not in final_messages:
                            final_messages[next_msg.id] = next_msg
                    else:
                        # Break if the chain is interrupted.
                        break

        # --- Step 6: Final Formatting ---
        # Convert the final set of discord.Message objects into ConversationMessage format.
        final_sorted_list = sorted(final_messages.values(), key=lambda m: m.created_at)
        
        formatted_context = []
        for msg in final_sorted_list:
            cleaned_content, image_urls, _ = await chatbot_manager.conversation_manager._process_discord_message_for_context(msg)
            
            multimodal_content = []
            if cleaned_content:
                multimodal_content.append(ContentPart(type="text", text=cleaned_content))
            for url in image_urls:
                multimodal_content.append(ContentPart(type="image_url", image_url={"url": url}))

            if not multimodal_content:
                continue

            conv_message = ConversationMessage(
                user_id=msg.author.id,
                username=msg.author.display_name,
                guild_id=msg.guild.id if msg.guild else None,
                content=cleaned_content,
                timestamp=msg.created_at.timestamp(),
                message_id=msg.id,
                is_bot_response=msg.author.bot,
                is_self_bot_response=(msg.author.id == message.guild.me.id),
                referenced_message_id=getattr(msg.reference, 'message_id', None) if msg.reference else None,
                attachment_urls=image_urls,
                multimodal_content=multimodal_content
            )

            # Pre-emptive filtering for bot's own embed-only messages, which don't get saved to history
            # but need to be filtered from on-the-fly context building.
            if conv_message.is_self_bot_response and not conv_message.content.strip():
                continue

            # Apply the standard validation logic used for persistent history
            is_valid, _ = chatbot_manager.conversation_manager._is_valid_context_message(conv_message)
            if not is_valid:
                continue

            formatted_context.append(conv_message)
            
        return formatted_context


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
