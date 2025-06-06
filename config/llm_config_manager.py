import json
import os
from utils.logging_setup import get_logger

logger = get_logger()

# Default LLM configuration
DEFAULT_LLM_CONFIG = {
    "base_url": "http://localhost:1234",
    "timeout": 120,
    "max_retries": 3,
    "retry_delay": 2,
    "provider": "local",  # Can be "local" or "google_ai"
    "google_ai_api_key": None,  # API key for Google AI services
    "google_ai_model_name": "gemma-3-27b-it",  # Default model for Google AI
    "servers": {}  # Server-specific configurations will be stored here
}

LLM_CONFIG_FILE = "data/llm_config.json"

def validate_llm_config(config):
    """Validate LLM configuration structure and contents"""
    errors = []
    
    # Check required fields
    required_fields = {
        "base_url": str,
        "timeout": int,
        "max_retries": int,
        "retry_delay": int,
        "provider": str
    }
    
    for field, field_type in required_fields.items():
        if field not in config:
            errors.append(f"Missing required LLM field: {field}")
        elif not isinstance(config[field], field_type):
            errors.append(f"LLM field {field} should be of type {field_type.__name__}, got {type(config[field]).__name__}")
    
    # Validate provider value
    if "provider" in config and config["provider"] not in ["local", "google_ai"]:
        errors.append(f"LLM provider should be 'local' or 'google_ai', got '{config['provider']}'")
    
    # Validate server configurations if present
    if "servers" in config and isinstance(config["servers"], dict):
        for server_id, server_config in config["servers"].items():
            if not isinstance(server_config, dict):
                errors.append(f"LLM server config for {server_id} should be a dictionary")
                continue
            
            for field in ["enabled", "preferred_model", "last_used_model"]:
                if field not in server_config:
                    errors.append(f"Missing field {field} in server config for {server_id}")
    
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
        
        # Don't save API key to file if it's in environment variable
        if 'GOOGLE_AI_API_KEY' in os.environ and 'google_ai_api_key' in config:
            config_to_save = config.copy()
            config_to_save['google_ai_api_key'] = "See environment variable GOOGLE_AI_API_KEY"
        else:
            config_to_save = config
        
        with open(LLM_CONFIG_FILE, 'w') as file:
            json.dump(config_to_save, file, indent=4)
            logger.debug(f"Successfully saved LLM configuration to {LLM_CONFIG_FILE}")
            return True
    except Exception as e:
        logger.error(f"Error saving LLM configuration: {e}")
        return False

def get_server_config(config, server_id):
    """Get server-specific LLM configuration"""
    servers = config.get("servers", {})
    server_id_str = str(server_id)
    
    if server_id_str in servers:
        server_config = servers[server_id_str]
    else:
        # Create default server config
        server_config = {
            "enabled": False,
            "preferred_model": None,
            "last_used_model": None
        }
    
    return server_config

def update_server_config(config, server_id, server_config):
    """Update server-specific LLM configuration"""
    if "servers" not in config:
        config["servers"] = {}
    
    server_id_str = str(server_id)
    config["servers"][server_id_str] = server_config
    return save_llm_config(config)

def migrate_from_main_config(main_config=None):
    """Migrate LLM configuration from main config and chatbot config to dedicated LLM config"""
    llm_config = load_llm_config()
    
    if main_config is not None:
        # Migrate global LLM settings
        if "llm_global" in main_config:
            global_config = main_config["llm_global"]
            for key in ["base_url", "timeout", "max_retries", "retry_delay"]:
                if key in global_config:
                    llm_config[key] = global_config[key]
        
        # Migrate server-specific settings
        if "llm_servers" in main_config:
            llm_config["servers"] = main_config["llm_servers"]
        
        # Migrate legacy settings if present
        if "llm" in main_config:
            legacy_config = main_config["llm"]
            llm_config["base_url"] = legacy_config.get("base_url", llm_config["base_url"])
            llm_config["timeout"] = legacy_config.get("timeout", llm_config["timeout"])
            llm_config["max_retries"] = legacy_config.get("max_retries", llm_config["max_retries"])
            llm_config["retry_delay"] = legacy_config.get("retry_delay", llm_config["retry_delay"])
            
            # Also migrate enabled status for servers if available
            if "enabled" in legacy_config:
                # Apply to all servers by default
                for server_id in llm_config["servers"]:
                    if server_id in llm_config["servers"]:
                        llm_config["servers"][server_id]["enabled"] = legacy_config["enabled"]
    
    # Migrate from chatbot config
    try:
        import json
        import os
        
        # Try to load chatbot config directly
        chatbot_config_file = "data/chatbot_config.json"
        if os.path.exists(chatbot_config_file):
            with open(chatbot_config_file, 'r') as file:
                chatbot_config = json.load(file)
                
                # Get global chatbot settings
                global_config = chatbot_config.get("global", {})
                
                # Get provider and API key settings
                if "llm_provider" in global_config:
                    llm_config["provider"] = global_config["llm_provider"]
                    logger.info(f"Migrated LLM provider from chatbot config: {global_config['llm_provider']}")
                
                if "google_ai_api_key" in global_config and global_config["google_ai_api_key"]:
                    llm_config["google_ai_api_key"] = global_config["google_ai_api_key"]
                    logger.info("Migrated Google AI API key from chatbot config")
                
                if "google_ai_model_name" in global_config:
                    llm_config["google_ai_model_name"] = global_config["google_ai_model_name"]
                    logger.info(f"Migrated Google AI model name from chatbot config: {global_config['google_ai_model_name']}")
                
                # Also look for channel-specific settings
                for server_id, channels in chatbot_config.get("channels", {}).items():
                    if server_id not in llm_config["servers"]:
                        llm_config["servers"][server_id] = {
                            "enabled": True,
                            "preferred_model": None,
                            "last_used_model": None
                        }
    except Exception as e:
        logger.error(f"Error migrating from chatbot config file: {e}")
        
        # Fall back to importing from chatbot manager if direct access fails
        try:
            from utils.chatbot_manager import chatbot_manager
            chatbot_config = chatbot_manager.config_cache.get("global", {})
            
            # Get provider and API key settings
            if "llm_provider" in chatbot_config:
                llm_config["provider"] = chatbot_config["llm_provider"]
            
            if "google_ai_api_key" in chatbot_config and chatbot_config["google_ai_api_key"]:
                llm_config["google_ai_api_key"] = chatbot_config["google_ai_api_key"]
            
            if "google_ai_model_name" in chatbot_config:
                llm_config["google_ai_model_name"] = chatbot_config["google_ai_model_name"]
        except Exception as e:
            logger.error(f"Error migrating from chatbot manager: {e}")
    
    # If google_ai is the provider but no API key is set, check environment variable
    if llm_config["provider"] == "google_ai" and not llm_config["google_ai_api_key"]:
        api_key = os.environ.get("GOOGLE_AI_API_KEY")
        if api_key:
            llm_config["google_ai_api_key"] = api_key
            logger.info("Using Google AI API key from environment variable")
    
    # Save the migrated config
    save_llm_config(llm_config)
    logger.info("Successfully migrated and saved LLM configuration")
    return llm_config