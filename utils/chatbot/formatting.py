"""
Formats conversation context for the language model.
"""

import re
import time
from typing import List, Optional, Union

import discord

from utils.chatbot.config import ConfigManager
from utils.chatbot.conversation import ConversationManager
from utils.chatbot.indexing import IndexingManager
from utils.chatbot.models import ConversationMessage
from utils.logging_setup import get_logger
from utils.media_cache import MediaCacheManager

logger = get_logger()

class LLMContextFormatter:
    """Formats conversation context for the LLM."""

    def __init__(self, config_manager: ConfigManager, conv_manager: ConversationManager, index_manager: IndexingManager, media_cache_manager: MediaCacheManager):
        self.config_manager = config_manager
        self.conv_manager = conv_manager
        self.index_manager = index_manager
        self.media_cache_manager = media_cache_manager

    async def get_prioritized_context(self, guild_id: int, channel_id: int, requesting_user_id: int) -> List[ConversationMessage]:
        """Get conversation context prioritized for the requesting user"""
        try:
            all_messages = await self.conv_manager.load_conversation_history(guild_id, channel_id)
            channel_config = self.config_manager.get_channel_config(guild_id, channel_id)
            
            if not all_messages:
                return []
            
            all_messages.sort(key=lambda x: x.timestamp)
            
            recent_messages = all_messages[-channel_config.max_context_messages:]
            
            requesting_user_messages = [msg for msg in recent_messages if int(msg.user_id) == requesting_user_id]
            other_messages = [msg for msg in recent_messages if int(msg.user_id) != requesting_user_id]
            
            prioritized_messages = requesting_user_messages[-channel_config.max_user_context_messages:]
            
            remaining_space = channel_config.max_context_messages - len(prioritized_messages)
            
            if remaining_space > 0:
                additional_messages_to_add = sorted(other_messages + requesting_user_messages[:-len(prioritized_messages)], key=lambda x: x.timestamp)
                prioritized_messages.extend(additional_messages_to_add[-remaining_space:])
            
            prioritized_messages.sort(key=lambda x: x.timestamp)
            
            if len(prioritized_messages) > channel_config.max_context_messages:
                prioritized_messages = prioritized_messages[-channel_config.max_context_messages:]
            
            user_msg_count = len([msg for msg in prioritized_messages if int(msg.user_id) == requesting_user_id])
            other_msg_count = len(prioritized_messages) - user_msg_count
            
            logger.debug(f"Generated prioritized context with {len(prioritized_messages)} messages for user {requesting_user_id} ({user_msg_count} user, {other_msg_count} other)")
            return prioritized_messages
        except Exception as e:
            logger.error(f"Error getting prioritized context: {e}", exc_info=True)
            return []

    async def _format_message_content(self, msg: ConversationMessage, local_id: int, guild_id: int, channel_id: int, message_id_to_local_index: dict) -> Union[str, List[dict]]:
        """
        Private helper to format the content of a single message.
        Returns a list of content parts for multimodal messages, or a single string for text-only.
        """
        # --- Unified Message Formatting ---
        user_index = await self.index_manager.load_user_index(guild_id)
        
        # Determine the role label. Use the bot's name for its own messages.
        if msg.is_self_bot_response:
            bot_user = user_index.get(msg.user_id)
            role_label = bot_user.username if bot_user else "Mirrobot"
        else:
            role_label = user_index.get(msg.user_id).username if user_index.get(msg.user_id) else msg.username
        
        reply_info = ""
        if msg.referenced_message_id:
            if msg.referenced_message_id in message_id_to_local_index:
                reply_info = f"[Replying to #{message_id_to_local_index[msg.referenced_message_id]}] "
            else:
                full_history = await self.index_manager.get_conversation_history(guild_id, channel_id)
                original_msg = next((m for m in full_history if m.message_id == msg.referenced_message_id), None)
                if original_msg:
                    original_author = (user_index.get(original_msg.user_id).username if user_index.get(original_msg.user_id) else original_msg.username)
                    snippet = self._create_smart_snippet(original_msg.content or "")
                    reply_info = f'[Replying to @{original_author}: "{snippet}"] '

        prefix = f"[{local_id}] [id:{msg.user_id}] {role_label}: {reply_info}"
        
        # If there's no special multimodal content, format as a simple string.
        if not msg.multimodal_content or all(p.type == "text" for p in msg.multimodal_content):
            text_content = msg.content or ""
            llm_readable_content = await self._convert_discord_format_to_llm_readable(text_content, guild_id)
            return f"{prefix}{llm_readable_content}".strip()

        # Handle multimodal content by creating a list of parts.
        content_parts = []
        text_segments = [prefix]
        
        for part in msg.multimodal_content:
            if part.type == "text" and part.text:
                text_segments.append(await self._convert_discord_format_to_llm_readable(part.text, guild_id))
            elif part.type == "image_url" and part.image_url and part.image_url.get("url"):
                # Add any pending text as a single part first.
                if len(text_segments) > 0:
                    content_parts.append({"type": "text", "text": " ".join(text_segments).strip()})
                    text_segments = [] # Reset for next text block
                # Add the image part.
                content_parts.append({"type": "image_url", "image_url": {"url": part.image_url["url"]}})
        
        # Add any remaining text at the end.
        if len(text_segments) > 0:
             content_parts.append({"type": "text", "text": " ".join(text_segments).strip()})

        return content_parts

    def _create_smart_snippet(self, text: str) -> str:
        """Creates a context-aware, intelligently truncated snippet of a given text."""
        SNIPPET_TARGET_PERCENTAGE = 0.3
        SNIPPET_MIN_LENGTH = 30
        SNIPPET_MAX_LENGTH = 150
        LONG_MESSAGE_THRESHOLD = 500

        if not text:
            return ""

        original_length = len(text)

        # If the text is short, return it as is.
        if original_length <= SNIPPET_MAX_LENGTH:
            return text

        def intelligent_truncate(content: str, max_len: int) -> str:
            """Truncates text to a max length, preferring to end on a sentence or phrase boundary."""
            if len(content) <= max_len:
                return content
            
            truncated = content[:max_len]
            
            # Try to find a sentence-ending punctuation mark.
            sentence_end_pos = -1
            for p in ['.', '!', '?']:
                sentence_end_pos = max(sentence_end_pos, truncated.rfind(p))
            
            if sentence_end_pos > 0:
                return truncated[:sentence_end_pos + 1]

            # Fallback to phrase-ending punctuation.
            phrase_end_pos = -1
            for p in [',', ';', ':']:
                phrase_end_pos = max(phrase_end_pos, truncated.rfind(p))
            
            if phrase_end_pos > 0:
                return truncated[:phrase_end_pos + 1]

            # Fallback to the last space to avoid cutting a word.
            last_space = truncated.rfind(' ')
            if last_space > 0:
                return truncated[:last_space] + "..."

            # Absolute fallback: hard truncate.
            return truncated + "..."

        # For long messages, create a dual-part snippet.
        if original_length > LONG_MESSAGE_THRESHOLD:
            start_snippet = intelligent_truncate(text, SNIPPET_MAX_LENGTH // 2)
            end_snippet = intelligent_truncate(text[-(SNIPPET_MAX_LENGTH // 2):], SNIPPET_MAX_LENGTH // 2)
            return f"{start_snippet} ... {end_snippet}"
        
        # For medium messages, create a single, percentage-based snippet.
        else:
            target_length = int(original_length * SNIPPET_TARGET_PERCENTAGE)
            final_length = max(SNIPPET_MIN_LENGTH, min(target_length, SNIPPET_MAX_LENGTH))
            return intelligent_truncate(text, final_length)

    async def format_context_for_llm(self, messages: List[ConversationMessage], guild_id: int, channel_id: int) -> tuple[str, List[dict]]:
        """
        Formats all context into a static string and a structured list of message dictionaries.
        Returns a tuple: (static_context_string, history_messages_list).
        """
        try:
            # Part 1: Assemble the static context string
            static_context_parts = []
            if guild_id and channel_id:
                static_context_parts.append(await self.get_channel_context_for_llm(guild_id, channel_id))
            if guild_id and messages:
                unique_user_ids = list(set(msg.user_id for msg in messages if not msg.is_bot_response))
                if unique_user_ids:
                    static_context_parts.append(await self.get_user_context_for_llm(guild_id, unique_user_ids))
            if guild_id and channel_id:
                static_context_parts.append(await self.get_pinned_context_for_llm(guild_id, channel_id))
            
            static_context_string = "\n".join(filter(None, static_context_parts))

            # Part 2: Assemble the structured conversation history
            if not messages:
                return static_context_string, []

            history_messages = []
            message_id_to_local_index = {msg.message_id: i + 1 for i, msg in enumerate(messages)}

            for i, msg in enumerate(messages):
                role = "assistant" if msg.is_self_bot_response else "user"
                content_object = await self._format_message_content(msg, i + 1, guild_id, channel_id, message_id_to_local_index)
                
                
                history_messages.append({"role": role, "content": content_object})

            return static_context_string, history_messages
        except Exception as e:
            logger.error(f"Error formatting context for LLM: {e}", exc_info=True)
            return "", []

    async def format_single_message(self, msg: ConversationMessage, history_messages: List[ConversationMessage], guild_id: int, channel_id: int) -> str:
        """Formats a single message using the same logic as the history formatter."""
        local_id = len(history_messages) + 1
        message_id_to_local_index = {m.message_id: i + 1 for i, m in enumerate(history_messages)}
        return await self._format_message_content(msg, local_id, guild_id, channel_id, message_id_to_local_index)

    async def _convert_discord_format_to_llm_readable(self, content: str, guild_id: int) -> str:
        """
        Converts Discord-specific formats and plain text names into a standardized
        @username format for the LLM context.
        """
        user_index = await self.index_manager.load_user_index(guild_id)
        if not user_index:
            return content

        emote_placeholders = {}
        placeholder_id = 0
        def store_emote(match):
            nonlocal placeholder_id
            emote = match.group(0)
            placeholder = f"__EMOTE__{placeholder_id}__"
            emote_placeholders[placeholder] = emote
            placeholder_id += 1
            return placeholder

        # 1. Protect custom emotes by replacing them with placeholders
        processed_content = re.sub(r'<a?:\w+:\d+>', store_emote, content)

        # 2. Handle standard Discord mentions first (<@12345>)
        def replace_mention_id(match):
            user_id = int(match.group(1))
            user = user_index.get(user_id)
            return f"@{user.username}" if user else "@Unknown User"
        processed_content = re.sub(r'<@!?(\d+)>', replace_mention_id, processed_content)

        # 3. Handle all other display names and usernames, stripping markdown
        name_to_username = {}
        for user in user_index.values():
            # Map both display name and username to the canonical @username
            name_to_username[user.display_name.lower()] = f"@{user.username}"
            name_to_username[user.username.lower()] = f"@{user.username}"
        
        # Sort by length descending to match longer names first
        sorted_names = sorted(name_to_username.keys(), key=len, reverse=True)
        
        # Create a regex that finds names, optionally surrounded by markdown
        # This looks for markdown characters like *, _, ~, `, ⭐ etc.
        escaped_names = [re.escape(name) for name in sorted_names if len(name) >= 3]
        if escaped_names:
            pattern = re.compile(
                r'(?<![@\w])(?:[\s\*\_~`⭐]*)(' + '|'.join(escaped_names) + r')(?:[\s\*\_~`⭐]*)(?!\w)',
                re.IGNORECASE
            )

            def replace_name(match):
                # The first group is the plain name, stripped of markdown
                matched_name = match.group(1).lower()
                return name_to_username.get(matched_name, match.group(0))

            processed_content = pattern.sub(replace_name, processed_content)

        # 4. Restore emotes before final cleanup
        for placeholder, emote in emote_placeholders.items():
            processed_content = processed_content.replace(placeholder, emote)

        # 5. Final cleanup
        processed_content = re.sub(r'(?<=\s):(\d+\.?)\s*$', '', processed_content, flags=re.MULTILINE)
        processed_content = re.sub(r'\s+', ' ', processed_content).strip()
        processed_content = re.sub(r'\s+([.,!?:;])', r'\1', processed_content)
        
        return processed_content

    async def format_llm_output_for_discord(self, text: str, guild: discord.Guild, bot_user_id: int = 0, bot_names: List[str] = []) -> str:
        """
        Cleans and formats LLM output for display on Discord.
        Handles:
        - Removing `Username:` prefixes.
        - Preventing bot self-mentions.
        - Converting internal `@username` and plain text names to display names.
        - Special handling for the creator's username.
        - Cleaning up leftover artifacts.
        """
        try:
            emote_placeholders = {}
            placeholder_id = 0
            def store_emote(match):
                nonlocal placeholder_id
                emote = match.group(0)
                placeholder = f"__EMOTE__{placeholder_id}__"
                emote_placeholders[placeholder] = emote
                placeholder_id += 1
                return placeholder

            # 1. Protect custom emotes by replacing them with placeholders
            processed_text = re.sub(r'<a?:\w+:\d+>', store_emote, text)

            # 2. Remove mass mentions
            processed_text = re.sub(r'@(everyone|here)', '', processed_text, flags=re.IGNORECASE)

            # 3. Failsafe: Strip any context formatting the LLM might have parroted.
            # This is a multi-pass failsafe to handle different parroting scenarios.
            
            # First, handle the most common full-line prefixes.
            # Matches "[1] [id:123] User:" or "[1] User:"
            processed_text = re.sub(r'^\s*\[\d+\]\s*(\[id:\d+\]\s*)?.*?:\s*', '', processed_text)
            
            # Next, handle individual components that might be parroted alone.
            # Matches "[Replying to #123]"
            processed_text = re.sub(r'\[Replying to #\d+\]\s*', '', processed_text)
            # Matches "[id:1234567890]"
            processed_text = re.sub(r'\[id:\d+\]\s*', '', processed_text)
            # Matches stray "[123]" anywhere in the text
            processed_text = re.sub(r'\s*\[\d{1,3}\]\s*', ' ', processed_text)

            #logger.debug(f"Anti-parrot post-filter text: '{processed_text[:100]}...'")

            creator_id = 214161976534892545
            creator_username = "⭐ **Mirrowel**"

            # 4. Strip "Username:" prefixes, but only if they are at the very start of the message.
            # This regex is designed to be specific: it matches up to 60 characters that are not a newline or colon,
            # and do not contain sentence-ending punctuation, to avoid stripping legitimate sentences.
            username_colon_pattern = r'^\s*[^:\n.!?]{1,60}:\s*'
            processed_text = re.sub(username_colon_pattern, '', processed_text).strip()

            # 4. Sanitize mentions
            user_index = await self.index_manager.load_user_index(guild.id)

            # 4a. Convert raw user mentions (<@123>) to display names
            def replace_user_mention(match):
                user_id = int(match.group(1))
                if user_id == creator_id:
                    return creator_username
                if user_index and user_id in user_index:
                    return user_index[user_id].display_name
                # Fallback for users not in the index
                member = guild.get_member(user_id)
                if member:
                    return member.display_name
                return f"`@Unknown User`"
            
            processed_text = re.sub(r'<@!?(\d+)>', replace_user_mention, processed_text)

            # 4b. Convert role mentions (<@&123>) to role names
            def replace_role_mention(match):
                role_id = int(match.group(1))
                role = guild.get_role(role_id)
                if role:
                    # Return as code block to prevent ping but show name
                    return f"`@{role.name}`"
                return f"`@deleted-role`"

            processed_text = re.sub(r'<@&(\d+)>', replace_role_mention, processed_text)

            # 5. Convert all username mentions to display names
            if user_index:
                # Create a mapping from various names to user objects
                name_to_user = {}
                for user in user_index.values():
                    name_to_user[user.username.lower()] = user
                    if user.display_name:
                        name_to_user[user.display_name.lower()] = user

                if name_to_user:
                    # Prioritize longer names to avoid partial matches
                    sorted_names = sorted(name_to_user.keys(), key=len, reverse=True)
                    
                    # Build a regex to find all possible names, with or without @
                    # This includes plain text names and @mentions, and strips surrounding markdown/junk
                    escaped_names = [re.escape(name) for name in sorted_names if len(name) >= 3]
                    if not escaped_names:
                        # Still need to restore emotes even if no names are processed
                        for placeholder, emote in emote_placeholders.items():
                            processed_text = processed_text.replace(placeholder, emote)
                        return processed_text

                    pattern = re.compile(r'(?<!\w)@?(?:[\s\*\_~`⭐]*)(' + '|'.join(escaped_names) + r')(?:[\s\*\_~`⭐]*)(?!\w)', re.IGNORECASE)

                    def replace_func(match):
                        matched_name = match.group(1).lower()
                        user = name_to_user.get(matched_name)

                        if not user:
                            return match.group(0)

                        # Special case for the creator
                        if int(user.user_id) == creator_id:
                            return creator_username
                        
                        # Default to display name
                        return user.display_name or user.username

                    processed_text = pattern.sub(replace_func, processed_text)

            # 5. Restore emotes before final cleanup
            for placeholder, emote in emote_placeholders.items():
                processed_text = processed_text.replace(placeholder, emote)

            # 6. Final Cleanup
            # Collapse horizontal whitespace, but preserve newlines
            processed_text = re.sub(r'[ \t]+', ' ', processed_text)
            # Collapse more than 2 newlines into 2 to preserve paragraphs
            processed_text = re.sub(r'\n{3,}', '\n\n', processed_text)
            # Remove space before punctuation (this will also join lines if punctuation is on a new line)
            processed_text = re.sub(r'\s+([.,!?:;])', r'\1', processed_text)

            # 7. Final mention sanitization pass to catch any stragglers
            processed_text = re.sub(r'<@&(\d+)>', r'`<@&\1>`', processed_text)
            processed_text = re.sub(r'<@!?(\d+)>', r'`<@\1>`', processed_text)
            
            processed_text = processed_text.strip()
            
            return processed_text
        except Exception as e:
            logger.error(f"Error formatting LLM output for Discord: {e}", exc_info=True)
            return text

    async def get_channel_context_for_llm(self, guild_id: int, channel_id: int) -> str:
        """Get channel context information for LLM"""
        try:
            channel_index = await self.index_manager.load_channel_index(guild_id)
            if channel_id not in channel_index: return ""
            
            channel = channel_index[channel_id]
            lines = ["=== Current Channel Info ==="]
            if channel.guild_name:
                lines.append(f"Server: {channel.guild_name}")
                if channel.guild_description:
                    lines.append(f"Description: {channel.guild_description}")
            lines.append(f"Channel: #{channel.channel_name}")
            lines.append(f"Type: {channel.channel_type}")
            if channel.topic: lines.append(f"Topic: {channel.topic}")
            if channel.category_name: lines.append(f"Category: {channel.category_name}")
            if channel.is_nsfw: lines.append("Note: This is an NSFW channel")
            lines.append("=== End of Channel Info ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting channel context for LLM: {e}", exc_info=True)
            return ""

    async def format_channel_context_for_llm_from_object(self, channel_obj) -> str:
        """Get channel context information for LLM from a discord.Channel object"""
        try:
            # This method doesn't need to be async if index_channel isn't, but we make it async for consistency.
            # If index_channel becomes async, this will be ready.
            entry = self.index_manager.index_channel(channel_obj)
            lines = ["=== Current Channel Info ==="]
            if entry.guild_name:
                lines.append(f"Server: {entry.guild_name}")
                if entry.guild_description:
                    lines.append(f"Description: {entry.guild_description}")
            lines.append(f"Channel: #{entry.channel_name}")
            lines.append(f"Type: {entry.channel_type}")
            if entry.topic: lines.append(f"Topic: {entry.topic}")
            if entry.category_name: lines.append(f"Category: {entry.category_name}")
            if entry.is_nsfw: lines.append("Note: This is an NSFW channel")
            lines.append("=== End of Channel Info ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error formatting channel context from object: {e}", exc_info=True)
            return ""

    async def get_user_context_for_llm(self, guild_id: int, user_ids: List[int]) -> str:
        """Get user context information for LLM"""
        try:
            user_index = await self.index_manager.load_user_index(guild_id)
            if not user_ids: return ""

            if self.index_manager.bot_user_id and self.index_manager.bot_user_id not in user_ids:
                user_ids.append(self.index_manager.bot_user_id)

            lines = ["=== Known Users ==="]
            for user_id in user_ids:
                if user_id in user_index:
                    user = user_index[user_id]
                    parts = [
                        f"ID: {user.user_id}",
                        f"Handle: @{user.username}",
                        f"Nickname: {user.display_name}"
                    ]
                    if user.roles:
                        parts.append(f"Roles: {', '.join(user.roles)}")
                    lines.append(f"• {' | '.join(parts)}")
            lines.append("=== End of Known Users ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting user context for LLM: {e}", exc_info=True)
            return ""

    async def format_user_context_for_llm_from_objects(self, users: List[Union[discord.Member, discord.User]]) -> str:
        """Get user context information for LLM from a list of live discord.User or discord.Member objects."""
        try:
            if not users:
                return ""

            lines = ["=== Known Users ==="]
            for user in users:
                # The guild_id is needed for role extraction if the user object is a discord.User
                guild_id = user.guild.id if hasattr(user, 'guild') else None
                user_data = self.index_manager.extract_user_data(user, guild_id=guild_id)
                
                parts = [
                    f"ID: {user_data.get('user_id')}",
                    f"Handle: @{user_data.get('username')}",
                    f"Nickname: {user_data.get('display_name')}"
                ]
                roles = user_data.get('roles')
                if roles:
                    parts.append(f"Roles: {', '.join(roles)}")
                lines.append(f"• {' | '.join(parts)}")
                
            lines.append("=== End of Known Users ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error formatting user context from objects: {e}", exc_info=True)
            return ""

    async def format_user_context_for_llm(self, user: Union[discord.Member, discord.User]) -> str:
        """Get user context information for LLM from a single live discord.User or discord.Member object."""
        return await self.format_user_context_for_llm_from_objects([user])

    async def get_pinned_context_for_llm(self, guild_id: int, channel_id: int) -> str:
        """Formats pinned messages for LLM context."""
        try:
            pins = self.index_manager.load_pinned_messages(guild_id, channel_id)
            if not pins: return ""

            lines = ["=== Pinned Messages ===", "Note: These messages are important channel context."]
            pins.sort(key=lambda x: x.timestamp)
            user_index = await self.index_manager.load_user_index(guild_id)

            for pin in pins:
                role_label = (user_index.get(pin.user_id).username if user_index.get(pin.user_id) else pin.username)
                content = await self._convert_discord_format_to_llm_readable(pin.content, guild_id)
                
                if pin.attachment_urls:
                    image_parts = []
                    for url in pin.attachment_urls:
                        validated_url, expired_filename = await self.validate_and_update_url(url, pin, guild_id, channel_id)
                        if validated_url:
                            image_parts.append(f"Image: {validated_url}")
                        elif expired_filename:
                            image_parts.append(f"Image {expired_filename} expired")
                    if image_parts:
                        content += f" ({', '.join(image_parts)})"
                        logger.debug(f"Appended to pinned message content: {content}")

                lines.append(f"{role_label}: {content.strip()}")
            
            lines.append("=== End of Pinned Messages ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting pinned context for LLM: {e}", exc_info=True)
            return ""

    async def validate_and_update_url(self, url: str, message: ConversationMessage, guild_id: int, channel_id: int) -> tuple[Optional[str], Optional[str]]:
        """
        Validates a URL and returns a tuple of (validated_url, expired_filename).
        If the URL is valid, it returns (new_or_original_url, None).
        If the URL is expired, it returns (None, filename).
        
        Note: This function no longer appends text to the message content directly.
        The calling function is responsible for handling the expired_filename.
        """
        original_url = url
        filename = original_url.split('/')[-1].split('?')[0]

        # 1. Handle Discord URLs by attempting to cache them.
        if "discord" in url:
            cached_url_result = await self.media_cache_manager.cache_url(url)
            if cached_url_result is None:
                logger.warning(f"Expired Discord URL {url} found in message {message.message_id}. Removing from history.")
                if original_url in message.attachment_urls:
                    message.attachment_urls.remove(original_url)
                    await self.conv_manager.update_message_in_conversation(guild_id, channel_id, message)
                return None, filename
            url = cached_url_result

        # 2. Handle non-Discord URLs (assumed to be from our cache).
        else:
            url_hash = self.media_cache_manager.get_hash_for_cached_url(url)
            if url_hash:
                cached_entry = self.media_cache_manager.media_entries.get(url_hash)
                if cached_entry:
                    expiry = cached_entry.get('expiry_timestamp')
                    if expiry is not None and expiry < time.time():
                        logger.warning(f"Expired cached URL {url} found in message {message.message_id}. Removing from history.")
                        if original_url in message.attachment_urls:
                            message.attachment_urls.remove(original_url)
                            await self.conv_manager.update_message_in_conversation(guild_id, channel_id, message)
                        return None, filename
        
        return url, None
