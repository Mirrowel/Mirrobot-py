import json
from utils.logging_setup import get_logger

logger = get_logger()

def load_config(config_file='config.json'):
    """Load configuration from file"""
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
            logger.info(f"Successfully loaded configuration from {config_file}")
            
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
                
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise

def save_config(config, config_file='config.json'):
    """Save configuration to file"""
    try:
        with open(config_file, 'w') as file:
            json.dump(config, file, indent=4)
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
