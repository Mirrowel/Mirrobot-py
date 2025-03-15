import os
import platform
import asyncio
from core.bot import create_bot
from utils.logging_setup import setup_logging
from config.config_manager import load_config
import logging

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")
        
    # Setup logging system
    logger = setup_logging()
    logger.info("Starting Mirrobot...")
    
    # Handle Windows event loop policy
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Load configuration
    config = load_config()
    
    # Create and run the bot
    bot = create_bot(config)
    bot.run(config['token'])
