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
    "auto_index_on_enable": True,
    "auto_respond_to_all": False,
    "include_bot_messages": False,
    "reply_to_bots": False,
    "extract_embed_text": False,
    "use_streaming": True,
}

# Keys that are per-channel and should never appear in server/global settings
_CHANNEL_ONLY_KEYS = {"enabled", "last_cleared_timestamp"}


class ConfigManager:
    """Manages chatbot configuration. Supports 3-tier hierarchy: global -> server -> channel."""

    def __init__(self, storage_manager: JsonStorageManager):
        self.storage_manager = storage_manager
        self.config_cache = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load chatbot configuration from file, migrating old format if needed."""
        config = self.storage_manager.read(CHATBOT_CONFIG_FILE)
        if not config:
            logger.info("No chatbot config found, creating a default one.")
            default_config = {
                "global": DEFAULT_CHATBOT_CONFIG,
                "servers": {},
            }
            self.save_config(default_config)
            return default_config

        # Migration: old format used top-level "channels" -> guild_id -> channel_id
        # New format uses "servers" -> guild_id -> { "server_settings": {}, "channels": {} }
        if "channels" in config and "servers" not in config:
            old_channels = config.pop("channels")
            servers = {}
            for guild_key, channels in old_channels.items():
                servers[guild_key] = {"server_settings": {}, "channels": channels}
            config["servers"] = servers
            self.save_config(config)
            logger.info(
                "Migrated chatbot config from flat channels to server hierarchy."
            )

        # Ensure the servers key exists
        if "servers" not in config:
            config["servers"] = {}

        logger.debug("Loaded chatbot configuration.")
        return config

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """Save configuration to file."""
        config_to_save = config if config is not None else self.config_cache
        if self.storage_manager.write(CHATBOT_CONFIG_FILE, config_to_save):
            self.config_cache = config_to_save
            logger.debug("Saved chatbot configuration.")
            return True
        return False

    def _get_guild_data(self, guild_id: int) -> Dict[str, Any]:
        """Get the full guild data dict (server_settings + channels)."""
        return self.config_cache.get("servers", {}).get(str(guild_id), {})

    def get_channel_config(
        self, guild_id: int, channel_id: int
    ) -> "ChannelChatbotConfig":
        """Get chatbot configuration for a specific channel, merged from global -> server -> channel."""
        guild_key = str(guild_id)
        channel_key = str(channel_id)

        global_config = self.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
        server_settings = (
            self.config_cache.get("servers", {})
            .get(guild_key, {})
            .get("server_settings", {})
        )
        channel_data = (
            self.config_cache.get("servers", {})
            .get(guild_key, {})
            .get("channels", {})
            .get(channel_key, {})
        )

        # 3-tier merge: global -> server -> channel
        merged_config = {**global_config, **server_settings, **channel_data}

        config_keys = {f.name for f in fields(ChannelChatbotConfig)}
        filtered_config = {k: v for k, v in merged_config.items() if k in config_keys}

        return ChannelChatbotConfig(**filtered_config)

    def get_server_config(self, guild_id: int) -> "ChannelChatbotConfig":
        """Get chatbot configuration merged from global -> server (no channel overrides)."""
        guild_key = str(guild_id)

        global_config = self.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
        server_settings = (
            self.config_cache.get("servers", {})
            .get(guild_key, {})
            .get("server_settings", {})
        )

        merged_config = {**global_config, **server_settings}

        config_keys = {f.name for f in fields(ChannelChatbotConfig)}
        filtered_config = {k: v for k, v in merged_config.items() if k in config_keys}

        return ChannelChatbotConfig(**filtered_config)

    def get_specific_config(
        self, guild_id: int, channel_id: int = None
    ) -> Dict[str, Any]:
        """Get raw config dict for a specific level (server or channel) without merging."""
        guild_key = str(guild_id)
        if channel_id:
            return (
                self.config_cache.get("servers", {})
                .get(guild_key, {})
                .get("channels", {})
                .get(str(channel_id), {})
                .copy()
            )
        else:
            return (
                self.config_cache.get("servers", {})
                .get(guild_key, {})
                .get("server_settings", {})
                .copy()
            )

    def set_config(
        self, guild_id: int, new_settings: Dict[str, Any], channel_id: int = None
    ) -> bool:
        """Set partial config at server or channel level (merges with existing). Mirrors inline pattern."""
        try:
            guild_key = str(guild_id)

            if "servers" not in self.config_cache:
                self.config_cache["servers"] = {}
            if guild_key not in self.config_cache["servers"]:
                self.config_cache["servers"][guild_key] = {
                    "server_settings": {},
                    "channels": {},
                }

            guild_data = self.config_cache["servers"][guild_key]

            if channel_id:
                channel_key = str(channel_id)
                if "channels" not in guild_data:
                    guild_data["channels"] = {}
                current = guild_data["channels"].get(channel_key, {})
                current.update(new_settings)
                guild_data["channels"][channel_key] = current
            else:
                if "server_settings" not in guild_data:
                    guild_data["server_settings"] = {}
                current = guild_data.get("server_settings", {})
                current.update(new_settings)
                guild_data["server_settings"] = current

            return self.save_config()
        except Exception as e:
            logger.error(
                f"Error setting config for {guild_id}/{channel_id}: {e}",
                exc_info=True,
            )
            return False

    def set_channel_config(
        self, guild_id: int, channel_id: int, channel_config: ChannelChatbotConfig
    ) -> bool:
        """Set full channel config (writes the entire dataclass). Used by chatbot_enable/disable."""
        try:
            guild_key = str(guild_id)
            channel_key = str(channel_id)

            if "servers" not in self.config_cache:
                self.config_cache["servers"] = {}
            if guild_key not in self.config_cache["servers"]:
                self.config_cache["servers"][guild_key] = {
                    "server_settings": {},
                    "channels": {},
                }

            self.config_cache["servers"][guild_key]["channels"][channel_key] = asdict(
                channel_config
            )

            return self.save_config()
        except Exception as e:
            logger.error(
                f"Error setting channel config for {guild_id}/{channel_id}: {e}",
                exc_info=True,
            )
            return False

    def remove_guild_config(self, guild_id: int):
        """Remove all configuration for a specific guild."""
        guild_key = str(guild_id)
        if guild_key in self.config_cache.get("servers", {}):
            del self.config_cache["servers"][guild_key]
            self.save_config()
            logger.info(f"Removed all channel configurations for guild {guild_id}.")

    def remove_channel_config(self, guild_id: int, channel_id: int):
        """Remove configuration for a specific channel."""
        guild_key = str(guild_id)
        channel_key = str(channel_id)
        servers = self.config_cache.get("servers", {})
        if guild_key in servers and channel_key in servers[guild_key].get(
            "channels", {}
        ):
            del servers[guild_key]["channels"][channel_key]
            if not servers[guild_key]["channels"]:
                servers[guild_key]["channels"] = {}
            self.save_config()
            logger.info(
                f"Removed configuration for channel {channel_id} in guild {guild_id}."
            )

    def is_chatbot_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if chatbot mode is enabled for a specific channel."""
        return self.get_channel_config(guild_id, channel_id).enabled
