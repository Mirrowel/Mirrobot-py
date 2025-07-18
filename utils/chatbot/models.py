"""
Data models for the chatbot functionality.
"""

import dataclasses
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union

@dataclass
class ContentPart:
    """Represents a part of a message's content, which can be text or an image."""
    type: str  # "text" or "image_url"
    # for text type
    text: Optional[str] = None
    # for image_url type
    image_url: Optional[Dict[str, Any]] = None

@dataclass
class ConversationMessage:
    """Represents a message in a conversation"""
    user_id: int
    username: str
    content: str
    timestamp: float
    message_id: int
    guild_id: Optional[int] = None
    author: Optional[Any] = None # discord.User or discord.Member
    is_bot_response: bool = False
    is_self_bot_response: bool = False # NEW: Is this bot's own response
    referenced_message_id: Optional[int] = None
    attachment_urls: List[str] = dataclasses.field(default_factory=list)
    embed_urls: List[str] = dataclasses.field(default_factory=list)
    multimodal_content: List[ContentPart] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        """Ensure multimodal_content is a list of ContentPart objects."""
        if self.multimodal_content and isinstance(self.multimodal_content, list) and self.multimodal_content and isinstance(self.multimodal_content[0], dict):
            self.multimodal_content = [ContentPart(**part) for part in self.multimodal_content]
        
        if self.author and isinstance(self.author, dict):
            author_data = self.author
            # --- Backward Compatibility Layer ---
            # 1. Handle 'username' vs 'name'
            if 'username' not in author_data and 'name' in author_data:
                author_data['username'] = author_data.pop('name')
            
            # 2. Add 'discriminator' if missing
            if 'discriminator' not in author_data:
                author_data['discriminator'] = '0'

            # 3. Add 'avatar' if missing
            if 'avatar' not in author_data:
                author_data['avatar'] = None

            # --- Data Type Correction ---
            # discord.py's User expects 'id' to be an int.
            if 'id' in author_data:
                author_data['id'] = int(author_data['id'])

            from discord import User
            self.author = User(state=None, data=author_data)

    def to_dict(self):
        """
        Manually converts the dataclass to a dictionary to ensure all fields are
        JSON serializable and avoid deepcopy errors with complex objects.
        """
        # Manually construct the dictionary from basic types
        data = {
            'user_id': self.user_id,
            'username': self.username,
            'content': self.content,
            'timestamp': self.timestamp,
            'message_id': self.message_id,
            'guild_id': self.guild_id,
            'is_bot_response': self.is_bot_response,
            'is_self_bot_response': self.is_self_bot_response,
            'referenced_message_id': self.referenced_message_id,
            'attachment_urls': self.attachment_urls,
            'embed_urls': self.embed_urls,
            # Convert ContentPart objects to dicts
            'multimodal_content': [
                {'type': part.type, 'text': part.text, 'image_url': part.image_url}
                for part in self.multimodal_content
            ]
        }

        # Safely handle the 'author' field
        if self.author:
            data['author'] = {
                'id': self.author.id,
                'username': self.author.name,
                'discriminator': self.author.discriminator,
                'display_name': self.author.display_name,
                'avatar': getattr(self.author.avatar, 'key', None)
            }
        else:
            data['author'] = None
            
        return data

@dataclass
class PinnedMessage:
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
    safety_settings: Optional[Dict[str, str]] = None
    last_cleared_timestamp: Optional[float] = None
    
    def __post_init__(self):
        # Handle cases where config might have old values or missing fields
        # Ensure numerical values are within bounds
        self.max_context_messages = max(10, min(self.max_context_messages, 1000))
        self.max_user_context_messages = max(5, min(self.max_user_context_messages, 500))
        self.context_window_hours = max(1, min(self.context_window_hours, 168))
        self.response_delay_seconds = max(0, min(self.response_delay_seconds, 10))
        self.max_response_length = max(100, min(self.max_response_length, 4000))
        self.prune_interval_hours = max(1, min(self.prune_interval_hours, 48))
        
        # Ensure boolean values are actually booleans
        self.enabled = bool(self.enabled)
        self.auto_prune_enabled = bool(self.auto_prune_enabled)
        self.auto_respond_to_mentions = bool(self.auto_respond_to_mentions)
        self.auto_respond_to_replies = bool(self.auto_respond_to_replies)
