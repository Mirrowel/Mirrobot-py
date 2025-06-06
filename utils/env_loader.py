"""
Environment variable loader for Mirrobot
"""
import os
from dotenv import load_dotenv
from utils.logging_setup import get_logger

logger = get_logger()

def load_environment():
    """Load environment variables from .env file if present"""
    try:
        # Try to load from .env file
        env_loaded = load_dotenv()
        
        if env_loaded:
            logger.info("Loaded environment variables from .env file")
        else:
            logger.debug("No .env file found or it's empty, using system environment variables only")
            
        # Check for required environment variables
        if 'DISCORD_BOT_TOKEN' in os.environ:
            logger.info("Found DISCORD_BOT_TOKEN in environment variables")
            # Mask token in logs for security
            token = os.environ['DISCORD_BOT_TOKEN']
            visible_part = token[:5] + "..." + token[-5:] if len(token) > 10 else "***masked***"
            logger.debug(f"Using token: {visible_part}")

        # Check for Google AI API Key
        if 'GOOGLE_AI_API_KEY' in os.environ:
            logger.info("Found GOOGLE_AI_API_KEY in environment variables")
            # Mask token in logs for security
            api_key = os.environ['GOOGLE_AI_API_KEY']
            visible_key_part = api_key[:5] + "..." + api_key[-5:] if len(api_key) > 10 else "***masked***"
            logger.debug(f"Google AI API Key: {visible_key_part}")
        else:
            logger.warning("GOOGLE_AI_API_KEY not found in environment variables. Cloud LLM features will be unavailable unless set in config.")

    except Exception as e:
        logger.error(f"Error loading environment variables: {e}")
