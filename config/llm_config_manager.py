import json
import os
from typing import Dict, Any, List, Optional, Tuple
from utils.logging_setup import get_logger
from utils.chatbot.manager import chatbot_manager

logger = get_logger()

# Default LLM configuration
DEFAULT_LLM_CONFIG = {
    "base_url": "http://localhost:1234",
    "timeout": 120,
    "max_retries": 2,
    "retry_delay": 5,
    "models": {
        "default": "chutes/deepseek-ai/DeepSeek-V3-0324",
        "chat": "chutes/deepseek-ai/DeepSeek-V3-0324",
        "ask": "chutes/deepseek-ai/DeepSeek-V3-0324",
        "think": "chutes/deepseek-ai/DeepSeek-R1-0528"
    },
    "safety_settings": {
        "harassment": "BLOCK_MEDIUM_AND_ABOVE",
        "hate_speech": "BLOCK_MEDIUM_AND_ABOVE",
        "sexually_explicit": "BLOCK_MEDIUM_AND_ABOVE",
        "dangerous_content": "BLOCK_MEDIUM_AND_ABOVE"
    },
    "servers": {}
}

LLM_CONFIG_FILE = "data/llm_config.json"

def load_api_keys_from_env():
    """
    Loads API keys from environment variables and groups them by provider.
    Example: GEMINI_API_KEY_1, OPENROUTER_API_KEY_1
    """
    api_keys = {}
    for key, value in os.environ.items():
        if key.endswith("_API_KEY") or "_API_KEY_" in key:
            # Extract provider name (e.g., "GEMINI" from "GEMINI_API_KEY_1")
            provider = key.split('_API_KEY')[0].lower()
            if provider not in api_keys:
                api_keys[provider] = []
            api_keys[provider].append(value)
    
    if not api_keys:
        logger.warning("No API keys found in environment variables.")
    else:
        logger.info(f"Loaded API keys for providers: {list(api_keys.keys())}")
        
    return api_keys

def validate_llm_config(config):
    """Validate LLM configuration structure and contents"""
    errors = []
    
    # Check required fields
    required_fields = {
        "base_url": str,
        "timeout": int,
        "max_retries": int,
        "retry_delay": int,
        "models": dict
    }
    
    for field, field_type in required_fields.items():
        if field not in config:
            errors.append(f"Missing required LLM field: {field}")
        elif not isinstance(config[field], field_type):
            errors.append(f"LLM field {field} should be of type {field_type.__name__}, got {type(config[field]).__name__}")

    if "models" in config and isinstance(config["models"], dict):
        for model_type in ["default", "chat", "ask", "think"]:
            if model_type not in config["models"]:
                errors.append(f"Missing required model type in global 'models': {model_type}")
            elif not isinstance(config["models"][model_type], str):
                errors.append(f"Global model for '{model_type}' should be a string.")
    else:
        errors.append("Global 'models' field must be a dictionary.")
    
    # Validate server configurations if present
    if "servers" in config and isinstance(config["servers"], dict):
        for server_id, server_config in config["servers"].items():
            if not isinstance(server_config, dict):
                errors.append(f"LLM server config for {server_id} should be a dictionary")
                continue
            
            if "models" not in server_config:
                errors.append(f"Missing 'models' object in server config for {server_id}")
            elif not isinstance(server_config["models"], dict):
                errors.append(f"'models' in server config for {server_id} should be a dictionary")
            else:
                for model_type in ["default", "chat", "ask", "think"]:
                    if model_type not in server_config["models"]:
                        errors.append(f"Missing required model type in 'models' for server {server_id}: {model_type}")
                    elif not isinstance(server_config["models"][model_type], str):
                        errors.append(f"Model for '{model_type}' in server {server_id} should be a string.")

    if errors:
        for error in errors:
            logger.error(f"LLM config validation error: {error}")
        return False
    
    return True

def load_llm_config():
    """Load LLM configuration from file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(LLM_CONFIG_FILE), exist_ok=True)
        
        if os.path.exists(LLM_CONFIG_FILE):
            with open(LLM_CONFIG_FILE, 'r') as file:
                config = json.load(file)
                #logger.info(f"Successfully loaded LLM configuration from {LLM_CONFIG_FILE}")
                
                # Initialize missing config elements with defaults
                for key, value in DEFAULT_LLM_CONFIG.items():
                    if key not in config:
                        config[key] = value
                
                # Validate the configuration
                if not validate_llm_config(config):
                    logger.error("LLM configuration validation failed. Using defaults.")
                    return DEFAULT_LLM_CONFIG
                    
                return config
        else:
            # Create default config file
            logger.info(f"LLM config file not found. Creating default at {LLM_CONFIG_FILE}")
            save_llm_config(DEFAULT_LLM_CONFIG)
            return DEFAULT_LLM_CONFIG
    except Exception as e:
        logger.error(f"Error loading LLM configuration: {e}")
        return DEFAULT_LLM_CONFIG

def get_safety_settings(guild_id: Optional[int] = None, channel_id: Optional[int] = None) -> Dict[str, str]:
    """
    Get safety settings with channel > server > global fallback.
    """
    llm_config = load_llm_config()

    # 1. Check for channel-specific settings
    if guild_id and channel_id:
        channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
        if channel_config and channel_config.safety_settings:
            return channel_config.safety_settings

    # 2. Check for server-specific settings
    if guild_id:
        server_config = llm_config.get("servers", {}).get(str(guild_id))
        if server_config and "safety_settings" in server_config:
            return server_config["safety_settings"]

    # 3. Fallback to global settings
    return llm_config.get("safety_settings", DEFAULT_LLM_CONFIG["safety_settings"])

def save_server_safety_settings(guild_id: int, settings: Dict[str, str]) -> bool:
    """Save safety settings for a specific server."""
    config = load_llm_config()
    config.setdefault("servers", {}).setdefault(str(guild_id), {})["safety_settings"] = settings
    return save_llm_config(config)

def get_reasoning_budget(model_name: str, mode: str, guild_id: int) -> Tuple[Optional[int], bool]:
    """Get reasoning budget level and custom flag with hierarchical fallback."""
    llm_config = load_llm_config()
    server_budgets = llm_config.get("servers", {}).get(str(guild_id), {}).get("reasoning_budgets", {})
    
    model_budgets = server_budgets.get(model_name, {})
    
    # Get budget for the specific mode, or fallback to default
    budget_setting = model_budgets.get(mode, model_budgets.get("default"))
    
    if isinstance(budget_setting, dict):
        # New format: {'level': level, 'custom_reasoning_budget': custom_flag}
        return budget_setting.get("level"), budget_setting.get("custom_reasoning_budget", budget_setting.get("custom", False)) # Added backward compatibility
    elif isinstance(budget_setting, int):
        # Old format: just the level
        return budget_setting, False
    
    return None, False

def save_reasoning_budget(model: str, mode: str, level: int, guild_id: int, custom_reasoning_budget: bool = False) -> bool:
    """Save a reasoning budget for a model and mode."""
    config = load_llm_config()
    budgets = config.setdefault("servers", {}).setdefault(str(guild_id), {}).setdefault("reasoning_budgets", {})
    
    model_budgets = budgets.setdefault(model, {})
    model_budgets[mode] = {
        "level": level,
        "custom_reasoning_budget": custom_reasoning_budget
    }
    
    return save_llm_config(config)

def get_all_reasoning_budgets(guild_id: int) -> Dict[str, Any]:
    """Get all reasoning budgets for a specific server."""
    llm_config = load_llm_config()
    return llm_config.get("servers", {}).get(str(guild_id), {}).get("reasoning_budgets", {})

def save_llm_config(config):
    """Save LLM configuration to file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(LLM_CONFIG_FILE), exist_ok=True)
        
        # Create a copy to avoid modifying the original dict
        config_to_save = config.copy()

        # Remove fields that are now managed by the rotator or env vars
        config_to_save.pop('provider', None)
        config_to_save.pop('google_ai_api_key', None)
        config_to_save.pop('google_ai_model_name', None)

        with open(LLM_CONFIG_FILE, 'w') as file:
            json.dump(config_to_save, file, indent=4)
            logger.debug(f"Successfully saved LLM configuration to {LLM_CONFIG_FILE}")
            return True
    except Exception as e:
        logger.error(f"Error saving LLM configuration: {e}")
        return False

# This function is now obsolete as configuration is simplified.
# It can be removed or left for historical purposes if needed.
def migrate_from_main_config(main_config=None):
    """This function is deprecated."""
    logger.warning("migrate_from_main_config is deprecated and should no longer be used.")
    return load_llm_config()
