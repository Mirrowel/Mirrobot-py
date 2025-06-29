"""
Manages conversation history and lifecycle.
"""

import json
import os
import re
import time
from dataclasses import asdict
from typing import List, Tuple

import discord
from utils.chatbot.config import ConfigManager
from utils.chatbot.models import ConversationMessage, ContentPart
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

CONVERSATION_DATA_DIR = "data/conversations"

class ConversationManager:
    """Manages the lifecycle of conversation histories."""

    def __init__(self, storage_manager: JsonStorageManager, config_manager: ConfigManager, bot_user_id: int = None):
        self.storage_manager = storage_manager
        self.config_manager = config_manager
        self.bot_user_id = bot_user_id

    def set_bot_user_id(self, bot_id: int):
        self.bot_user_id = bot_id

    def get_conversation_file_path(self, guild_id: int, channel_id: int) -> str:
        return os.path.join(CONVERSATION_DATA_DIR, f"guild_{guild_id}", f"channel_{channel_id}.json")

    def load_conversation_history(self, guild_id: int, channel_id: int) -> List[ConversationMessage]:
        """Load conversation history for a specific channel"""
        file_path = self.get_conversation_file_path(guild_id, channel_id)
        
        try:
            data = self.storage_manager.read(file_path)
            if not data:
                return []

            messages = [ConversationMessage(**msg) for msg in data.get("messages", [])]
            
            # Filter messages within the context window
            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
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
        except Exception as e:
            logger.error(f"Error loading conversation history for {file_path}: {e}", exc_info=True)
            return []

    def save_conversation_history(self, guild_id: int, channel_id: int, messages: List[ConversationMessage]) -> bool:
        """Save conversation history for a specific channel"""
        file_path = self.get_conversation_file_path(guild_id, channel_id)
        
        try:
            # Convert messages to dict format
            data = {
                "messages": [asdict(msg) for msg in messages],
                "last_updated": time.time()
            }
            
            #logger.debug(f"Saved {len(messages)} messages to conversation history for {file_path}")
            return self.storage_manager.write(file_path, data)
        except Exception as e:
            logger.error(f"Error saving conversation history to {file_path}: {e}", exc_info=True)
            return False

    def add_message_to_conversation(self, guild_id: int, channel_id: int, message: discord.Message, update_user_index_func) -> bool:
        """Add a message to the conversation history"""
        try:
            if self.check_duplicate_message(guild_id, channel_id, message.id):
                return True

            cleaned_content, image_urls, embed_urls = self._process_discord_message_for_context(message)
            if not cleaned_content and not image_urls:
                logger.debug(f"Skipping message {message.id} as content became empty after media filtering.")
                return False
            
            multimodal_content = []
            if cleaned_content:
                multimodal_content.append(ContentPart(type="text", text=cleaned_content))
            
            IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
            for url in image_urls:
                if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    multimodal_content.append(ContentPart(type="image_url", image_url={"url": url}))
                else:
                    multimodal_content.append(ContentPart(type="document_url", document_url={"url": url}))

            temp_conv_message = ConversationMessage(
                user_id=message.author.id,
                username=message.author.display_name,
                content=cleaned_content,
                timestamp=message.created_at.timestamp(),
                message_id=message.id,
                is_bot_response=message.author.bot,
                is_self_bot_response=(message.author.id == self.bot_user_id),
                referenced_message_id=getattr(message.reference, 'message_id', None) if message.reference else None,
                attachment_urls=image_urls,
                embed_urls=embed_urls,
                multimodal_content=multimodal_content
            )

            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
            cutoff_time = time.time() - (channel_config.context_window_hours * 3600)
            if temp_conv_message.timestamp < cutoff_time:
                logger.debug(f"Skipping message {message.id} as it's outside context window.")
                return False

            is_valid, _ = self._is_valid_context_message(temp_conv_message, debug_mode=False)
            if not is_valid:
                logger.debug(f"Skipping message {message.id} as it's not valid context.")
                return False

            update_user_index_func(guild_id, message.author, is_message_author=True)
            
            messages = self.load_conversation_history(guild_id, channel_id)
            messages.append(temp_conv_message)
            
            if len(messages) > channel_config.max_context_messages:
                messages = messages[-channel_config.max_context_messages:]
            
            return self.save_conversation_history(guild_id, channel_id, messages)
        except Exception as e:
            logger.error(f"Error adding message to conversation for channel {channel_id}: {e}", exc_info=True)
            return False

    def _is_valid_context_message(self, msg: ConversationMessage, debug_mode: bool = False) -> tuple[bool, list[str]]:
        """Check if a message is valid for context inclusion"""
        debug_steps = []
        try:
            content = msg.content.strip()
            message_preview = content[:50] + "..." if len(content) > 50 else content
            
            if debug_mode:
                debug_steps.append(f"📝 **Original Message:** `{content}`")
                debug_steps.append(f"👤 **From User:** {msg.username} (ID: {msg.user_id})")
                debug_steps.append(f"🖼️ **Attachment URLs:** {msg.attachment_urls}")
            
            if not content and not msg.attachment_urls:
                if debug_mode: debug_steps.append("❌ **Filter Result:** Empty message and no attachments - FILTERED")
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
            
            if not content_for_analysis:
                keep_message = bool(mentions or emojis or msg.attachment_urls)
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

    def _process_discord_message_for_context(self, message: discord.Message) -> Tuple[str, List[str], List[str]]:
        """Processes a discord.Message to extract content, filter media, and prepare for context."""
        cleaned_content = message.content
        media_urls, video_urls, embed_urls = [], [], []

        # Supported extensions
        IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        TEXT_EXTENSIONS = ['.pdf', '.txt', '.log', '.ini', '.json', '.xml', '.csv', '.md']
        
        # Extract media URLs from message content
        url_pattern = re.compile(r'https?://\S+')
        urls_to_remove = []
        for url in url_pattern.findall(cleaned_content):
            path = url.split('?')[0]
            
            # Clean trailing punctuation
            cleaned_url = url
            cleaned_path = path
            if cleaned_path.endswith(('.', ',', '!', '?')):
                cleaned_path = cleaned_path[:-1]
                cleaned_url = cleaned_url[:-1]

            if any(cleaned_path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS + TEXT_EXTENSIONS):
                if cleaned_url not in media_urls:
                    media_urls.append(cleaned_url)
                urls_to_remove.append(url)

        for url in urls_to_remove:
            cleaned_content = cleaned_content.replace(url, '').strip()

        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                if attachment.url not in media_urls:
                    media_urls.append(attachment.url)
            elif any(attachment.filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS + TEXT_EXTENSIONS):
                if attachment.url not in media_urls:
                    media_urls.append(attachment.url)
            elif attachment.content_type.startswith(('video/', 'image/gif')) or \
                 (attachment.content_type in ['application/x-discord-application', 'application/octet-stream'] and \
                  attachment.filename.lower().endswith(('.mp4', '.mov', '.webm', '.gif'))):
                video_urls.append(attachment.url)
                if attachment.url in cleaned_content:
                    cleaned_content = cleaned_content.replace(attachment.url, '').strip()
                logger.debug(f"Filtered out video/gif attachment URL: {attachment.url}")

        for embed in message.embeds:
            if embed.type == 'image' and embed.url and any(ext in embed.url.lower() for ext in IMAGE_EXTENSIONS):
                if embed.url not in media_urls:
                    media_urls.append(embed.url)
                if embed.url in cleaned_content:
                    cleaned_content = cleaned_content.replace(embed.url, '').strip()
            elif embed.type in ['video', 'gifv'] and (embed.url or (embed.video and embed.video.url)):
                url_to_filter = embed.url or (embed.video.url if embed.video else None)
                if url_to_filter:
                    video_urls.append(url_to_filter)
                    if url_to_filter in cleaned_content:
                        cleaned_content = cleaned_content.replace(url_to_filter, '').strip()
                    logger.debug(f"Filtered out video/gif embed URL: {url_to_filter}")
            elif embed.url:
                embed_urls.append(embed.url)
        
        return re.sub(r'\s+', ' ', cleaned_content).strip(), media_urls, embed_urls

    def check_duplicate_message(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Check if a message is already in the conversation history"""
        try:
            file_path = self.get_conversation_file_path(guild_id, channel_id)
            data = self.storage_manager.read(file_path)
            if data:
                return any(msg.get("message_id") == message_id for msg in data.get("messages", []))
            return False
        except Exception as e:
            logger.error(f"Error checking for duplicate message in {file_path}: {e}", exc_info=True)
            return False

    def delete_message_from_conversation(self, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Remove a message from conversation history."""
        try:
            messages = self.load_conversation_history(guild_id, channel_id)
            if not messages:
                return False
            
            original_length = len(messages)
            messages = [msg for msg in messages if msg.message_id != message_id]
            
            if len(messages) < original_length:
                logger.debug(f"Removed message {message_id} from conversation history")
                return self.save_conversation_history(guild_id, channel_id, messages)
            else:
                logger.debug(f"Message {message_id} not found for deletion")
                return False
        except Exception as e:
            logger.error(f"Error deleting message from conversation: {e}", exc_info=True)
            return False

    def edit_message_in_conversation(self, guild_id: int, channel_id: int, message_id: int, new_content: str) -> bool:
        """Update the content of an existing message in conversation history."""
        try:
            messages = self.load_conversation_history(guild_id, channel_id)
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
                return self.save_conversation_history(guild_id, channel_id, messages)
            else:
                logger.debug(f"Message {message_id} not found for editing")
                return False
        except Exception as e:
            logger.error(f"Error editing message in conversation: {e}", exc_info=True)
            return False

    def prune_old_conversations(self) -> int:
        """Prune old conversation data to save space."""
        pruned_count = 0
        config = self.config_manager.config_cache
        for guild_key, guild_channels in config.get("channels", {}).items():
            guild_id = int(guild_key)
            guild_path = os.path.join(CONVERSATION_DATA_DIR, f"guild_{guild_id}")
            if not os.path.isdir(guild_path):
                continue

            for channel_key in guild_channels:
                channel_id = int(channel_key)
                channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
                if not channel_config.auto_prune_enabled:
                    continue

                file_path = self.get_conversation_file_path(guild_id, channel_id)
                if not os.path.exists(file_path):
                    continue

                try:
                    messages = self.load_conversation_history(guild_id, channel_id)
                    original_count = len(messages)
                    
                    # load_conversation_history already filters by time, so we just need to check max messages
                    if len(messages) > channel_config.max_context_messages:
                        pruned_messages = messages[-channel_config.max_context_messages:]
                    else:
                        pruned_messages = messages

                    if len(pruned_messages) != original_count:
                        if self.save_conversation_history(guild_id, channel_id, pruned_messages):
                            num_pruned = original_count - len(pruned_messages)
                            pruned_count += num_pruned
                            logger.debug(f"Pruned {num_pruned} old messages from {file_path}")
                    
                    if not pruned_messages and os.path.exists(file_path):
                        os.remove(file_path)
                        logger.debug(f"Removed empty conversation file: {file_path}")

                except Exception as e:
                    logger.error(f"Error processing conversation file {file_path}: {e}", exc_info=True)

        if pruned_count > 0:
            logger.info(f"Total pruned {pruned_count} old conversation messages across all channels.")
        return pruned_count
