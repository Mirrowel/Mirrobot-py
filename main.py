import asyncio
import os
import platform
from utils.logging_setup import setup_logging
from utils.env_loader import load_environment
from config.config_manager import load_config
from core.bot import create_bot
import logging

async def main():
    """Main entry point for the bot"""
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")
        
    # Setup logging system
    logger = setup_logging()
    logger.info("Starting Mirrobot...")
    
    # Handle Windows event loop policy
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Optionally reduce noisy logs (e.g., from discord)
    logging.getLogger("discord").setLevel(logging.INFO)

    # Load environment variables
    load_environment()
    
    # Load configuration
    config = load_config()
    
    # Create and run the bot
    bot = create_bot(config)

    # Get the bot token, trying config first, then environment variable
    bot_token = config.get('token') or os.environ.get('DISCORD_BOT_TOKEN')
    if not bot_token:
        logger.critical("DISCORD_BOT_TOKEN not found in config or environment variables. Bot cannot start.")
        return

    try:
        await bot.start(bot_token)
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown requested. Exiting.")
    except Exception as e:
        # The bot's internal KeyboardInterrupt handler will be respected by discord.py
        # We only need to catch other fatal exceptions here.
        print(f"Fatal error: {e}")
