import json
import os
from utils.logging_setup import get_logger

logger = get_logger()

def validate_config(config):
    """Validate configuration structure and contents"""
    errors = []
    
    # Check required fields
    required_fields = {
        'token': str,
        'command_prefix': str,
        'ocr_worker_count': int,
        'ocr_read_channels': dict,
        'ocr_response_channels': dict,
        'ocr_response_fallback': dict,
        'command_permissions': dict,
        'server_prefixes': dict
    }
    
    for field, field_type in required_fields.items():
        # Skip token check if using environment variable
        if field == 'token' and 'DISCORD_BOT_TOKEN' in os.environ:
            continue
            
        if field not in config:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(config[field], field_type):
            errors.append(f"Field {field} should be of type {field_type.__name__}, got {type(config[field]).__name__}")
    
    # Validate nested structures if primary fields exist
    if 'ocr_read_channels' in config and isinstance(config['ocr_read_channels'], dict):
        for guild_id, channels in config['ocr_read_channels'].items():
            if not isinstance(channels, list):
                errors.append(f"ocr_read_channels.{guild_id} should be a list, got {type(channels).__name__}")
    
    if 'ocr_response_channels' in config and isinstance(config['ocr_response_channels'], dict):
        for guild_id, channels in config['ocr_response_channels'].items():
            if not isinstance(channels, list):
                errors.append(f"ocr_response_channels.{guild_id} should be a list, got {type(channels).__name__}")
    
    if 'ocr_response_fallback' in config and isinstance(config['ocr_response_fallback'], dict):
        for guild_id, channels in config['ocr_response_fallback'].items():
            if not isinstance(channels, list):
                errors.append(f"ocr_response_fallback.{guild_id} should be a list, got {type(channels).__name__}")
    
    # Validate ocr_worker_count has reasonable value
    if 'ocr_worker_count' in config and isinstance(config['ocr_worker_count'], int):
        if config['ocr_worker_count'] < 1 or config['ocr_worker_count'] > 10:
            errors.append(f"ocr_worker_count should be between 1 and 10, got {config['ocr_worker_count']}")
    
    # Validate ocr_max_queue_size if present
    if 'ocr_max_queue_size' in config:
        if not isinstance(config['ocr_max_queue_size'], int):
            errors.append(f"ocr_max_queue_size should be an integer, got {type(config['ocr_max_queue_size']).__name__}")
        elif config['ocr_max_queue_size'] < 10 or config['ocr_max_queue_size'] > 1000:
            errors.append(f"ocr_max_queue_size should be between 10 and 1000, got {config['ocr_max_queue_size']}")
    
    if errors:
        for error in errors:
            logger.error(f"Config validation error: {error}")
        return False
    
    return True

def load_config(config_file='config.json'):
    """Load configuration from file"""
    try:
        # Check for environment variables first
        token_from_env = os.environ.get('DISCORD_BOT_TOKEN')
        
        with open(config_file, 'r') as file:
            config = json.load(file)
            logger.info(f"Successfully loaded configuration from {config_file}")
            
            # Use environment variable for token if available
            if token_from_env:
                config['token'] = token_from_env
                logger.info("Using token from environment variable")
            
            # Initialize missing config elements with defaults
            if 'ocr_read_channels' not in config:
                config['ocr_read_channels'] = {}
            if 'ocr_response_channels' not in config:
                config['ocr_response_channels'] = {}
            if 'ocr_response_fallback' not in config:
                config['ocr_response_fallback'] = {}
            if 'command_permissions' not in config:
                config['command_permissions'] = {}
            if 'server_prefixes' not in config:
                config['server_prefixes'] = {}
            if 'command_prefix' not in config:
                config['command_prefix'] = '!'
            if 'ocr_max_queue_size' not in config:
                config['ocr_max_queue_size'] = 100  # Default to 100 queue items
            
            # Check for LLM settings that should be migrated
            if any(key in config for key in ['llm', 'llm_global', 'llm_servers']):
                try:
                    from config.llm_config_manager import migrate_from_main_config
                    logger.info("Migrating LLM settings to dedicated LLM config file...")
                    migrate_from_main_config(config)
                    
                    # Remove LLM settings from main config after migration
                    for key in ['llm', 'llm_global', 'llm_servers']:
                        if key in config:
                            logger.info(f"Removing {key} from main config after migration to dedicated LLM config")
                            del config[key]
                    
                    # Save the updated config without LLM settings
                    save_config(config, config_file)
                except Exception as e:
                    logger.error(f"Failed to migrate LLM settings: {e}")
            
            # Validate the configuration
            if not validate_config(config):
                logger.error("Configuration validation failed. Check the errors above and fix your config file.")
                raise ValueError("Invalid configuration")
                
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise

def save_config(config, config_file='config.json'):
    """Save configuration to file"""
    try:
        # Don't save token from environment variable back to file
        if 'DISCORD_BOT_TOKEN' in os.environ and 'token' in config:
            config_to_save = config.copy()
            config_to_save['token'] = "See environment variable DISCORD_BOT_TOKEN"
        else:
            config_to_save = config
            
        with open(config_file, 'w') as file:
            json.dump(config_to_save, file, indent=4)
            logger.info(f"Successfully saved configuration to {config_file}")
            return True
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return False

def update_config_section(section_name, section_data, config_file='config.json'):
    """Update a specific section of the configuration"""
    config = load_config(config_file)
    config[section_name] = section_data
    return save_config(config, config_file)
