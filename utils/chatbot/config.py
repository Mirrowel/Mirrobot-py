"""
Manages chatbot configuration.
"""

from dataclasses import asdict, fields
from typing import Any, Dict

from utils.chatbot.models import ChannelChatbotConfig
from utils.chatbot.persistence import JsonStorageManager
from utils.logging_setup import get_logger

logger = get_logger()

CHATBOT_CONFIG_FILE = "data/chatbot_config.json"

DEFAULT_CHATBOT_CONFIG = {
    "max_context_messages": 400,
    "max_user_context_messages": 100,
    "context_window_hours": 48,
    "response_delay_seconds": 1,
    "max_response_length": 2000,
    "auto_prune_enabled": True,
    "prune_interval_hours": 6,
    "user_index_cleanup_hours": 168,  # 7 days
    "auto_index_on_restart": True,
    "auto_index_on_enable": True
}

class ConfigManager:
    """Manages chatbot configuration."""

    def __init__(self, storage_manager: JsonStorageManager):
        self.storage_manager = storage_manager
        self.config_cache = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load chatbot configuration from file."""
        config = self.storage_manager.read(CHATBOT_CONFIG_FILE)
        if not config:
            logger.info("No chatbot config found, creating a default one.")
            default_config = {"channels": {}, "global": DEFAULT_CHATBOT_CONFIG}
            self.save_config(default_config)
            return default_config
        logger.debug("Loaded chatbot configuration.")
        return config

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """Save chatbot configuration to file."""
        config_to_save = config if config is not None else self.config_cache
        if self.storage_manager.write(CHATBOT_CONFIG_FILE, config_to_save):
            self.config_cache = config_to_save
            logger.debug("Saved chatbot configuration.")
            return True
        return False

    def get_channel_config(self, guild_id: int, channel_id: int) -> "ChannelChatbotConfig":
        """Get chatbot configuration for a specific channel."""
        guild_key = str(guild_id)
        channel_key = str(channel_id)
        
        channel_data = self.config_cache.get("channels", {}).get(guild_key, {}).get(channel_key, {})
        
        global_config = self.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
        merged_config = {**global_config, **channel_data}
        
        config_keys = {f.name for f in fields(ChannelChatbotConfig)}
        filtered_config = {k: v for k, v in merged_config.items() if k in config_keys}
        
        return ChannelChatbotConfig(**filtered_config)

    def set_channel_config(self, guild_id: int, channel_id: int, channel_config: ChannelChatbotConfig) -> bool:
        """Set chatbot configuration for a specific channel."""
        try:
            guild_key = str(guild_id)
            channel_key = str(channel_id)
            
            if "channels" not in self.config_cache:
                self.config_cache["channels"] = {}
            if guild_key not in self.config_cache["channels"]:
                self.config_cache["channels"][guild_key] = {}
            
            self.config_cache["channels"][guild_key][channel_key] = asdict(channel_config)
            
            return self.save_config()
        except Exception as e:
            logger.error(f"Error setting channel config for {guild_id}/{channel_id}: {e}", exc_info=True)
            return False

    def is_chatbot_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if chatbot mode is enabled for a specific channel."""
        return self.get_channel_config(guild_id, channel_id).enabled
