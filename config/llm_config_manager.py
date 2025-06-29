import json
import os
from utils.logging_setup import get_logger

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
