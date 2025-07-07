"""
Manages conversation history and lifecycle.
"""

import asyncio
import json
import os
import re
import time
from dataclasses import asdict
from typing import List, Tuple
from urllib.parse import urlparse

import discord
from utils.chatbot.config import ConfigManager
from utils.chatbot.indexing import IndexingManager
from utils.chatbot.models import ConversationMessage, ContentPart
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

CONVERSATION_DATA_DIR = "data/conversations"

class ConversationManager:
    """Manages the lifecycle of conversation histories."""

    def __init__(self, storage_manager: JsonStorageManager, config_manager: ConfigManager, index_manager: IndexingManager, bot_user_id: int = None):
        self.storage_manager = storage_manager
        self.config_manager = config_manager
        self.index_manager = index_manager
        self.bot_user_id = bot_user_id

    def set_bot_user_id(self, bot_id: int):
        self.bot_user_id = bot_id

    def get_conversation_file_path(self, guild_id: int, channel_id: int) -> str:
        return os.path.join(CONVERSATION_DATA_DIR, f"guild_{guild_id}", f"channel_{channel_id}.json")

    async def clear_conversation_history(self, guild_id: int, channel_id: int):
        """Clear conversation history for a specific channel from cache and disk."""
        await self.index_manager.clear_conversation_history_cache(guild_id, channel_id)
        logger.debug(f"Cleared conversation history for channel {channel_id} in guild {guild_id}")

    async def load_conversation_history(self, guild_id: int, channel_id: int) -> List[ConversationMessage]:
        """Load conversation history for a specific channel from the cache."""
        try:
            messages = await self.index_manager.get_conversation_history(guild_id, channel_id)
            
            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
            
            # Determine the definitive cutoff time.
            time_window_cutoff = time.time() - (channel_config.context_window_hours * 3600)
            checkpoint_cutoff = channel_config.last_cleared_timestamp or 0
            final_cutoff = max(time_window_cutoff, checkpoint_cutoff)
            
            # Filter messages based on the cutoff time and validity.
            valid_messages = [
                msg for msg in messages
                if msg.timestamp >= final_cutoff and self._is_valid_context_message(msg)[0]
            ]
            
            return valid_messages
        except Exception as e:
            logger.error(f"Error loading conversation history for channel {channel_id}: {e}", exc_info=True)
            return []

    async def add_message_to_conversation(self, guild_id: int, channel_id: int, message: discord.Message) -> Tuple[bool, List[discord.User]]:
        """
        Adds a message to conversation history.
        Returns a tuple: (success_boolean, list_of_users_to_index).
        """
        try:
            # --- Pre-emptive Filtering ---
            # This check is now handled more intelligently in _process_discord_message_for_context
            # by differentiating between image embeds and other types.

            if await self.check_duplicate_message(guild_id, channel_id, message.id):
                return True, []

            cleaned_content, image_urls, embed_urls = self._process_discord_message_for_context(message)
            if not cleaned_content and not image_urls:
                return False, []

            multimodal_content = [ContentPart(type="text", text=cleaned_content)] if cleaned_content else []
            multimodal_content.extend(ContentPart(type="image_url", image_url={"url": url}) for url in image_urls)

            conv_message = ConversationMessage(
                user_id=message.author.id, username=message.author.display_name,
                author=message.author,
                content=cleaned_content, timestamp=message.created_at.timestamp(),
                message_id=message.id, is_bot_response=message.author.bot,
                is_self_bot_response=(message.author.id == self.bot_user_id),
                referenced_message_id=getattr(message.reference, 'message_id', None),
                attachment_urls=image_urls, embed_urls=embed_urls,
                multimodal_content=multimodal_content
            )

            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
            cutoff_time = time.time() - (channel_config.context_window_hours * 3600)
            if conv_message.timestamp < cutoff_time:
                return False, []

            is_valid, _ = self._is_valid_context_message(conv_message)
            if not is_valid:
                return False, []

            # Add message directly to the cache via IndexingManager
            await self.index_manager.add_message_to_history(guild_id, channel_id, conv_message)
            
            # Pruning logic can be handled here or in a separate maintenance task
            # For now, let's keep it simple and rely on periodic pruning.
            
            users_to_index = [message.author]
            return True, users_to_index

        except Exception as e:
            logger.error(f"Error adding message to conversation for channel {channel_id}: {e}", exc_info=True)
            return False, []

    async def bulk_add_messages_to_conversation(self, guild_id: int, channel_id: int, new_messages: List[discord.Message]) -> Tuple[int, List[discord.User]]:
        """
        Adds a list of messages to history efficiently.
        Returns a tuple: (number_of_messages_added, list_of_unique_users_to_index).
        """
        try:
            if not new_messages:
                return 0, []

            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
            cutoff_time = time.time() - (channel_config.context_window_hours * 3600)
            
            existing_history = await self.load_conversation_history(guild_id, channel_id)
            existing_message_ids = {msg.message_id for msg in existing_history}
            
            converted_messages = []
            users_to_update = set()

            for message in new_messages:
                if message.id in existing_message_ids:
                    continue
                
                # If the message has embeds, filter it out immediately.
                if message.embeds:
                    logger.debug(f"Bulk message {message.id} filtered out because it contains embeds.")
                    continue

                cleaned_content, image_urls, embed_urls = self._process_discord_message_for_context(message)
                if not cleaned_content and not image_urls:
                    continue

                multimodal_content = [ContentPart(type="text", text=cleaned_content)] if cleaned_content else []
                multimodal_content.extend(ContentPart(type="image_url", image_url={"url": url}) for url in image_urls)

                conv_message = ConversationMessage(
                    user_id=message.author.id, username=message.author.display_name,
                    author=message.author,
                    content=cleaned_content, timestamp=message.created_at.timestamp(),
                    message_id=message.id, is_bot_response=message.author.bot,
                    is_self_bot_response=(message.author.id == self.bot_user_id),
                    referenced_message_id=getattr(message.reference, 'message_id', None),
                    attachment_urls=image_urls, embed_urls=embed_urls,
                    multimodal_content=multimodal_content
                )

                if conv_message.timestamp < cutoff_time:
                    continue

                is_valid, _ = self._is_valid_context_message(conv_message)
                if not is_valid:
                    continue
                
                converted_messages.append(conv_message)
                users_to_update.add(message.author)

            if not converted_messages:
                return 0, []

            combined_messages = existing_history + converted_messages
            combined_messages.sort(key=lambda m: m.timestamp)
            
            if len(combined_messages) > channel_config.max_context_messages:
                combined_messages = combined_messages[-channel_config.max_context_messages:]
            
            await self.index_manager.replace_conversation_history(guild_id, channel_id, combined_messages)
            return len(converted_messages), list(users_to_update)
            
        except Exception as e:
            logger.error(f"Error bulk adding messages to conversation for channel {channel_id}: {e}", exc_info=True)
            return 0, []

    def _is_valid_context_message(self, msg: ConversationMessage, debug_mode: bool = False) -> tuple[bool, list[str]]:
        """Check if a message is valid for context inclusion"""
        debug_steps = []
        try:
            content = msg.content.strip() if msg.content else ""
            has_image = any(part.type == 'image_url' for part in msg.multimodal_content)
            message_preview = content[:50] + "..." if len(content) > 50 else content

            if debug_mode:
                debug_steps.append(f"📝 **Original Message:** `{content}`")
                debug_steps.append(f"👤 **From User:** {msg.username} (ID: {msg.user_id})")
                debug_steps.append(f"🖼️ **Has Image:** {has_image}")

            # A message is invalid if it has no text AND no images.
            if not content and not has_image:
                if debug_mode: debug_steps.append("❌ **Filter Result:** Empty message and no attachments - FILTERED")
                return False, debug_steps

            # Filter out messages that are just non-image embeds (e.g., links to other sites)
            if msg.embed_urls:
                if debug_mode: debug_steps.append("❌ **Filter Result:** Message contains non-image embed URLs - FILTERED")
                return False, debug_steps

            mention_pattern = r'<@!?(\d+)>'
            emoji_pattern = r'<a?:\w+:\d+>'
            mentions = re.findall(mention_pattern, content)
            emojis = re.findall(emoji_pattern, content)
            
            content_without_mentions = re.sub(mention_pattern, '', content).strip()
            content_for_analysis = re.sub(emoji_pattern, '', content_without_mentions).strip()
            
            if debug_mode:
                debug_steps.append(f"👥 **Mentions Found:** {len(mentions)}")
                debug_steps.append(f"😀 **Emojis Found:** {len(emojis)}")
                debug_steps.append(f"🔍 **Content for Analysis:** `{content_for_analysis}`")

            # If there's no text left after stripping mentions/emojis, keep it only if it has an image or was just mentions/emojis.
            if not content_for_analysis:
                keep_message = bool(mentions or emojis or has_image)
                if debug_mode: debug_steps.append("✅ **Filter Result:** Message is just mentions/emojis/attachments - KEPT" if keep_message else "❌ **Filter Result:** Message became empty after cleaning - FILTERED")
                return keep_message, debug_steps

            if not any(c.isalnum() for c in content_for_analysis):
                if debug_mode: debug_steps.append(f"❌ **Filter Result:** No alphanumeric characters in `{content_for_analysis}` - FILTERED")
                return False, debug_steps
            
            command_prefixes = ['!', '/', '$', '?', '.', '-', '+', '>', '<', '=', '~', '`']
            if content_for_analysis.startswith(tuple(command_prefixes)):
                if debug_mode: debug_steps.append(f"❌ **Filter Result:** Command prefix detected - FILTERED")
                return False, debug_steps
            
            if re.match(r'^[a-zA-Z0-9]{1,5}!', content_for_analysis):
                if debug_mode: debug_steps.append(f"❌ **Filter Result:** Command pattern detected - FILTERED")
                return False, debug_steps
            
            if debug_mode:
                debug_steps.append(f"✅ **Filter Result:** Message `{message_preview}` passed all filters - KEPT")
            return True, debug_steps
            
        except Exception as e:
            if debug_mode: debug_steps.append(f"⚠️ **Error during validation:** {str(e)} - defaulting to KEEP")
            logger.error(f"Error validating context message from {msg.username}: {e}", exc_info=True)
            return True, debug_steps

    def _is_image_url(self, url: str) -> bool:
        """
        Check if a URL points to a supported, non-GIF image by checking the
        path extension and blocking known GIF-hosting domains.
        """
        try:
            # 1. Domain Blacklist for known GIF providers
            gif_domains = ['tenor.com', 'giphy.com']
            parsed_url = urlparse(url)
            if any(domain in parsed_url.netloc for domain in gif_domains):
                logger.debug(f"URL {url} blocked by domain blacklist.")
                return False

            # 2. Check file extension
            image_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']
            return any(parsed_url.path.lower().endswith(ext) for ext in image_extensions)
        except Exception:
            return False

    def _process_discord_message_for_context(self, message: discord.Message) -> Tuple[str, List[str], List[str]]:
        """
        Processes a discord.Message to extract content, filter media, and prepare for context.
        This is the standardized function for media extraction.
        """
        content = message.content
        seen_normalized_urls = set()
        image_urls = []
        other_urls = set()

        def _normalize_url(url: str) -> str:
            """Normalizes a URL by removing its query parameters and fragment for deduplication."""
            try:
                return url.split('?')[0]
            except Exception:
                return url

        def _add_image_url(url: str):
            """Adds a URL to the list if it's a valid, non-duplicate image."""
            if not url or not self._is_image_url(url):
                return
            normalized_url = _normalize_url(url)
            if normalized_url not in seen_normalized_urls:
                image_urls.append(url)
                seen_normalized_urls.add(normalized_url)

        # 1. Process Attachments
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                _add_image_url(attachment.url)
            else:
                other_urls.add(attachment.url)

        # 2. Process Embeds
        for embed in message.embeds:
            # An embed can represent a direct image link, which we want to capture.
            if embed.url and self._is_image_url(embed.url):
                _add_image_url(embed.url)

            # It can also have a separate image or thumbnail attached.
            if embed.thumbnail and embed.thumbnail.url:
                _add_image_url(embed.thumbnail.url)
            if embed.image and embed.image.url:
                _add_image_url(embed.image.url)

            # If the embed itself is not an image link, treat its URL as something to be stripped.
            if embed.url and not self._is_image_url(embed.url):
                other_urls.add(embed.url)
            if embed.video and embed.video.url:
                other_urls.add(embed.video.url)

        # 3. Process URLs in the message content
        url_pattern = re.compile(r'https?://\S+')
        found_urls = url_pattern.findall(content)
        for url in found_urls:
            # Attempt to add as an image, otherwise it will be stripped.
            _add_image_url(url)
            other_urls.add(url)

        # 4. Clean the message content by removing all identified URLs
        # We use the original image URLs for stripping, not the normalized ones.
        all_urls_to_strip = set(image_urls).union(other_urls)
        cleaned_content = content
        for url in all_urls_to_strip:
            # Use a more robust replacement to avoid partial matches
            cleaned_content = cleaned_content.replace(url, ' ')

        # Final cleanup of whitespace
        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
        
        # Ensure that URLs classified as images are not also in the "other" urls list.
        final_other_urls = other_urls - set(image_urls)
        
        # Return cleaned content, a list of unique image URLs, and a list of other URLs
        return cleaned_content, image_urls, list(final_other_urls)

    async def check_duplicate_message(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Check if a message is already in the conversation history"""
        try:
            # This can remain somewhat synchronous as it's a read-only check on potentially cached data
            history = await self.load_conversation_history(guild_id, channel_id)
            return any(msg.message_id == message_id for msg in history)
        except Exception as e:
            logger.error(f"Error checking for duplicate message in channel {channel_id}: {e}", exc_info=True)
            return False

    async def delete_message_from_conversation(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Remove a message from conversation history."""
        try:
            messages = await self.load_conversation_history(guild_id, channel_id)
            if not messages:
                return False
            
            original_length = len(messages)
            messages = [msg for msg in messages if msg.message_id != message_id]
            
            if len(messages) < original_length:
                await self.index_manager.replace_conversation_history(guild_id, channel_id, messages)
                logger.debug(f"Removed message {message_id} from conversation history")
                return True
            else:
                logger.debug(f"Message {message_id} not found for deletion")
                return False
        except Exception as e:
            logger.error(f"Error deleting message from conversation: {e}", exc_info=True)
            return False

    async def edit_message_in_conversation(self, guild_id: int, channel_id: int, message_id: int, new_content: str) -> bool:
        """Update the content of an existing message in conversation history."""
        try:
            messages = await self.load_conversation_history(guild_id, channel_id)
            if not messages:
                return False
            
            message_found = False
            for msg in messages:
                if msg.message_id == message_id:
                    msg.content = new_content
                    message_found = True
                    logger.debug(f"Updated message {message_id} in conversation history")
                    break
            
            if message_found:
                await self.index_manager.replace_conversation_history(guild_id, channel_id, messages)
                return True
            else:
                logger.debug(f"Message {message_id} not found for editing")
                return False
        except Exception as e:
            logger.error(f"Error editing message in conversation: {e}", exc_info=True)
            return False

