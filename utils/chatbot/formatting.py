"""
Formats conversation context for the language model.
"""

import re
from typing import List

from utils.chatbot.config import ConfigManager
from utils.chatbot.conversation import ConversationManager
from utils.chatbot.indexing import IndexingManager
from utils.chatbot.models import ConversationMessage
from utils.logging_setup import get_logger

logger = get_logger()

class LLMContextFormatter:
    """Formats conversation context for the LLM."""

    def __init__(self, config_manager: ConfigManager, conv_manager: ConversationManager, index_manager: IndexingManager):
        self.config_manager = config_manager
        self.conv_manager = conv_manager
        self.index_manager = index_manager

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

    async def _format_message_content(self, msg: ConversationMessage, local_id: int, guild_id: int, channel_id: int, message_id_to_local_index: dict) -> str:
        """Private helper to format the content of a single message."""
        user_index = await self.index_manager.load_user_index(guild_id)
        role_label = "Mirrobot" if msg.is_self_bot_response else (user_index.get(msg.user_id).username if user_index.get(msg.user_id) else msg.username)
        
        reply_info = ""
        if msg.referenced_message_id:
            if msg.referenced_message_id in message_id_to_local_index:
                reply_info = f"[Replying to #{message_id_to_local_index[msg.referenced_message_id]}] "
            else:
                # This is a performance hit, but necessary for out-of-context replies.
                # Consider caching full history if this becomes a bottleneck.
                full_history = await self.conv_manager.load_conversation_history(guild_id, channel_id)
                original_msg = next((m for m in full_history if m.message_id == msg.referenced_message_id), None)
                if original_msg:
                    original_author = (user_index.get(original_msg.user_id).username if user_index.get(original_msg.user_id) else original_msg.username)
                    snippet = (original_msg.content or "")[:75] + ("..." if len(original_msg.content or "") > 75 else "")
                    reply_info = f'[Replying to @{original_author}: "{snippet}"] '

        line_parts = [f"[{local_id}] [id:{msg.user_id}] {role_label}: {reply_info}"]

        # Use a temporary variable for content to handle cases where multimodal_content is empty
        content_to_process = msg.multimodal_content if msg.multimodal_content else [ConversationMessage(type="text", text=msg.content)]

        if msg.multimodal_content:
            text_segments = []
            for part in msg.multimodal_content:
                if part.type == "text" and part.text:
                    text_segments.append(await self._convert_discord_format_to_llm_readable(part.text, guild_id))
                elif part.type == "image_url" and part.image_url and part.image_url.get("url"):
                    if text_segments:
                        line_parts.append(" ".join(text_segments))
                        text_segments = []
                    line_parts.append(f"(Image: {part.image_url['url']})")
            if text_segments:
                line_parts.append(" ".join(text_segments))
        else: # Fallback for older data or non-multimodal messages
            llm_readable_content = await self._convert_discord_format_to_llm_readable(msg.content, guild_id)
            if msg.attachment_urls:
                llm_readable_content += f" (Image: {', '.join(msg.attachment_urls)})"
            line_parts.append(llm_readable_content)

        return " ".join(line_parts).strip()

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
                content_string = await self._format_message_content(msg, i + 1, guild_id, channel_id, message_id_to_local_index)
                history_messages.append({"role": role, "content": content_string})

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

        processed_content = content

        # 1. Handle standard Discord mentions first (<@12345>)
        def replace_mention_id(match):
            user_id = int(match.group(1))
            user = user_index.get(user_id)
            return f"@{user.username}" if user else "@Unknown User"
        processed_content = re.sub(r'<@!?(\d+)>', replace_mention_id, processed_content)

        # 2. Handle the specially formatted creator name
        # This specifically looks for the formatted name and converts it back.
        creator_username_formatted = "⭐ \\*\\*Mirrowel\\*\\*"
        processed_content = re.sub(creator_username_formatted, "@Mirrowel", processed_content)

        # 3. Handle all other display names and usernames, stripping markdown
        name_to_username = {}
        for user in user_index.values():
            # Map both display name and username to the canonical @username
            name_to_username[user.display_name.lower()] = f"@{user.username}"
            name_to_username[user.username.lower()] = f"@{user.username}"
        
        # Sort by length descending to match longer names first
        sorted_names = sorted(name_to_username.keys(), key=len, reverse=True)
        
        # Create a regex that finds names, optionally surrounded by markdown
        # This looks for markdown characters like *, _, ~, `, etc.
        escaped_names = [re.escape(name) for name in sorted_names if len(name) >= 3]
        if escaped_names:
            pattern = re.compile(
                r'(?<![@\w])(?:[\*\_~`]*|⭐\s\*\*?)(' + '|'.join(escaped_names) + r')(?:[\*\_~`]*|\*\*?)(?!\w)',
                re.IGNORECASE
            )

            def replace_name(match):
                # The first group is the plain name, stripped of markdown
                matched_name = match.group(1).lower()
                return name_to_username.get(matched_name, match.group(0))

            processed_content = pattern.sub(replace_name, processed_content)

        # 4. Final cleanup
        processed_content = re.sub(r'(?<=\s):(\d+\.?)\s*$', '', processed_content, flags=re.MULTILINE)
        processed_content = re.sub(r'\s+', ' ', processed_content).strip()
        processed_content = re.sub(r'\s+([.,!?:;])', r'\1', processed_content)
        
        return processed_content

    async def format_llm_output_for_discord(self, text: str, guild_id: int, bot_user_id: int = 0, bot_names: List[str] = []) -> str:
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
            # 0. Failsafe: Strip any context formatting the LLM might have parroted.
            # This is a multi-pass failsafe to handle different parroting scenarios.
            # First, handle the complex case with a reply block, which may or may not have a username.
            p1 = r'\[\d+\].*?\[Replying to #\d+\]\s*'
            processed_text = re.sub(p1, '', text.strip())
            # Second, handle the simpler case with just a username prefix.
            p2 = r'\[\d+\]\s*.*?:'
            processed_text = re.sub(p2, '', processed_text.strip())
            # Third, handle standalone reply blocks on their own lines.
            p3 = r'^\s*\[Replying to #\d+\]\s*'
            processed_text = re.sub(p3, '', processed_text, flags=re.MULTILINE).strip()

            # Fourth, filter out stray numerical tags like [372] that the LLM sometimes outputs.
            p4 = r'\s*\[\d{1,3}\]\s*'
            processed_text = re.sub(p4, ' ', processed_text).strip()
            #logger.debug(f"Anti-parrot post-filter text: '{processed_text[:100]}...'")

            creator_id = 214161976534892545
            creator_username = "⭐ **Mirrowel**"

            # 1. Strip "Username:" prefixes, but only if they are at the very start of the message.
            username_colon_pattern = r'^(?:[a-zA-Z0-9_ -]+):\s*'
            processed_text = re.sub(username_colon_pattern, '', processed_text).strip()

            # 3. Convert all username mentions to display names
            user_index = await self.index_manager.load_user_index(guild_id)
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
                    # This includes plain text names and @mentions
                    escaped_names = [re.escape(name) for name in sorted_names if len(name) >= 3]
                    if not escaped_names:
                        return processed_text # No names to process

                    pattern = re.compile(r'(?<!\w)@?(' + '|'.join(escaped_names) + r')(?!\w)', re.IGNORECASE)

                    def replace_func(match):
                        matched_name = match.group(1).lower()
                        user = name_to_user.get(matched_name)

                        if not user:
                            return match.group(0)

                        # Special case for the creator
                        if int(user.user_id) == creator_id:
                            return creator_username
                        
                        # Handle bot self-mentions that might have been missed
                        if bot_names and int(user.user_id) == bot_user_id:
                            return ""

                        # Default to display name
                        return user.display_name or user.username

                    processed_text = pattern.sub(replace_func, processed_text)

            # 4. Final Cleanup
            processed_text = re.sub(r'\s+', ' ', processed_text).strip()
            processed_text = re.sub(r'\s+([.,!?:;])', r'\1', processed_text)
            
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
                    content += f" (Image: {', '.join(pin.attachment_urls)})"
                lines.append(f"{role_label}: {content.strip()}")
            
            lines.append("=== End of Pinned Messages ===\n")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting pinned context for LLM: {e}", exc_info=True)
            return ""
