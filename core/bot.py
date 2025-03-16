import discord
from discord.ext import commands
from utils.logging_setup import get_logger
import sys
import asyncio

logger = get_logger()

def get_prefix(bot, message):
    """Function to get the prefix for a server"""
    # Default prefix is '!'
    default_prefix = bot.config.get('command_prefix', '!')
    
    # Create list of prefixes - always include the bot mention as a universal prefix
    # This will allow users to use @Mirrobot command in any server
    prefixes = [f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']  # Bot mentions with space after
    
    # If in a DM or no guild, use the default prefix
    if message.guild is None:
        return default_prefix
    
    # Get server-specific prefix if it exists
    guild_id = str(message.guild.id)
    server_prefix = bot.config.get('server_prefixes', {}).get(guild_id, default_prefix)
    prefixes.append(server_prefix)
    
    return prefixes

def get_server_prefix(bot, message):
    """Get the prefix for a specific server"""
    # Default prefix is '!'
    default_prefix = bot.config.get('command_prefix', '!')
    
    # If in a DM or no guild, use the default prefix
    if message.guild is None:
        return default_prefix
    
    # Get server-specific prefix if it exists
    guild_id = str(message.guild.id)
    return bot.config.get('server_prefixes', {}).get(guild_id, default_prefix)

def apply_command_categories(bot):
    """Apply categories to all commands, ensuring they're correctly set"""
    for cmd in bot.commands:
        # Check if category is already set directly on the command
        if hasattr(cmd, 'category') and cmd.category:
            logger.debug(f"Command '{cmd.name}' already has category: {cmd.category}")
            continue
            
        # Try to find category in callback
        if hasattr(cmd, 'callback') and hasattr(cmd.callback, 'category'):
            cmd.category = cmd.callback.category
            logger.debug(f"Applied category '{cmd.category}' from callback to command '{cmd.name}'")
        elif hasattr(cmd, 'cog_name'):
            # For commands in Cogs, if no explicit category is set, use the Cog name
            cmd.category = cmd.cog_name
            logger.debug(f"Applied Cog name '{cmd.category}' as category for command '{cmd.name}'")
        else:
            cmd.category = "Miscellaneous"
            logger.debug(f"Assigned default category 'Miscellaneous' to command '{cmd.name}'")
    
    # Log summary of categories
    categories = {}
    for cmd in bot.commands:
        cat = getattr(cmd, 'category', "Miscellaneous")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(cmd.name)
    
    for cat, cmds in sorted(categories.items()):
        logger.debug(f"Category '{cat}' has {len(cmds)} commands: {', '.join(cmds)}")

def create_bot(config):
    """Create and configure the bot"""
    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.message_content = True
    
    bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
    
    # Store config in the bot for easy access
    bot.config = config
    
    # Create a queue for OCR processing tasks
    bot.ocr_queue = asyncio.Queue()
    
    # Set up event handlers
    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user.name}!')
        
        # Get worker count from config (default to 2 workers if not specified)
        worker_count = config.get('ocr_worker_count', 2)
        logger.info(f"Starting {worker_count} OCR workers")
        
        # Start multiple OCR workers
        for i in range(worker_count):
            asyncio.create_task(ocr_worker(bot, worker_id=i+1))
        
        # Load cogs after bot is ready
        await load_cogs(bot)
    
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
            
        # Create a task for processing this message to avoid blocking the event handler
        asyncio.create_task(process_message(bot, message, config))
        
        await bot.process_commands(message)
    
    # Error handler for commands
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            # Log the error
            logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name if ctx.guild else 'DM'}:{ctx.guild.id if ctx.guild else 'N/A'}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
        elif isinstance(error, commands.CheckFailure):
            pass  # Permission denied, already logged
        else:
            # Handle other types of errors
            if ctx.guild:
                logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
            else:
                logger.debug("Command error in DM")
            logger.error(f"Error in command '{ctx.command}': {error}")
            await ctx.send(f"Error in command '{ctx.command}': {error}")
    
    return bot

async def process_message(bot, message, config):
    """Process an incoming message for OCR if needed"""
    try :
        # Check if message should be processed for OCR and queue it
        if message.guild and str(message.guild.id) in config['ocr_read_channels']:
            guild_id = str(message.guild.id)
            if guild_id not in config['ocr_read_channels']:
                logger.info(f'No read channels found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
                config['ocr_read_channels'][guild_id] = []
                from config.config_manager import save_config
                save_config(config)
                
            if message.channel.id in config['ocr_read_channels'][guild_id]:
                # Queue the message for OCR processing
                await bot.ocr_queue.put(message)
                logger.debug(f"Queued message for OCR processing: {message.id}")
    except Exception as e:
        logger.error(f"Error in message processing: {e}")

async def ocr_worker(bot, worker_id=1):
    """Worker to process OCR tasks from the queue"""
    logger.info(f"OCR worker {worker_id} started")
    while True:
        try:
            # Get a message from the queue
            message = await bot.ocr_queue.get()
            
            try:
                # Import here to avoid circular imports
                from core.ocr import process_pics
                logger.debug(f"Worker {worker_id} processing message: {message.id}")
                await process_pics(bot, message)
                logger.debug(f"Worker {worker_id} completed OCR task for message: {message.id}")
            except Exception as e:
                logger.error(f"Worker {worker_id} error processing OCR task: {e}")
            finally:
                # Mark the task as done
                bot.ocr_queue.task_done()
        except Exception as e:
            logger.error(f"Error in OCR worker {worker_id}: {e}")
            # Sleep briefly to avoid tight loop in case of repeated errors
            await asyncio.sleep(1)

async def load_cogs(bot):
    """Load all cogs for the bot"""
    from cogs.ocr_config import OCRConfigCog
    from cogs.bot_config import BotConfigCog
    from cogs.permission_commands import PermissionCommandsCog
    from cogs.pattern_commands import PatternCommandsCog
    from cogs.system_commands import SystemCommandsCog
    
    # Add cogs
    await bot.add_cog(OCRConfigCog(bot))
    await bot.add_cog(BotConfigCog(bot))
    await bot.add_cog(PermissionCommandsCog(bot))
    await bot.add_cog(PatternCommandsCog(bot))
    await bot.add_cog(SystemCommandsCog(bot))
    
    logger.info("All cogs loaded successfully")
    
    # Apply command categories after all cogs are loaded
    apply_command_categories(bot)
