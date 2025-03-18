import discord
from discord.ext import commands
import cogs
from core.ocr import respond_to_ocr
from utils.logging_setup import get_logger
import sys
import asyncio
from utils.resource_monitor import ResourceMonitor, get_system_info
from utils.log_manager import LogManager
from cogs.__init__ import cogs

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
    
    # Create a queue for OCR processing tasks with max size to prevent memory issues
    max_queue_size = config.get('ocr_max_queue_size', 100)
    bot.ocr_queue = asyncio.Queue(maxsize=max_queue_size)
    
    # Add OCR queue statistics
    bot.ocr_queue_stats = {
        'total_enqueued': 0,
        'total_processed': 0,
        'total_rejected': 0,
        'high_watermark': 0,
    }
    
    # Set up resource monitoring
    bot.resource_monitor = ResourceMonitor()
    bot.log_manager = LogManager()
    
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
        
        # Start resource monitoring
        bot.resource_monitor.start()
        
        # Schedule log cleanup task to run daily
        async def cleanup_logs_task():
            while True:
                try:
                    bot.log_manager.cleanup_old_logs()
                except Exception as e:
                    logger.error(f"Error cleaning up logs: {e}")
                await asyncio.sleep(86400)  # 24 hours
                
        bot.log_cleanup_task = asyncio.create_task(cleanup_logs_task())
        logger.info("Resource monitoring and log management initialized")
        
        # Load cogs after bot is ready
        await load_cogs(bot)
    
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
            
        # Create a task for processing this message to avoid blocking the event handler
        asyncio.create_task(process_message(bot, message, config))
        
        await bot.process_commands(message)
    
    # Global error handler
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            permissions = ', '.join([f'`{p.replace("_", " ").title()}`' for p in error.missing_permissions])
            await ctx.send(f"⚠️ **Missing Permissions**: I need {permissions} permission(s) to run this command.", 
                          delete_after=15)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏰ This command is on cooldown. Please try again in {error.retry_after:.1f} seconds.",
                          delete_after=10)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: `{error.param.name}`. Please check the command syntax.",
                          delete_after=15)
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument: {str(error)}. Please check the command syntax.",
                          delete_after=15)
        elif isinstance(error, commands.CommandNotFound):
            # Log the error
            # logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name if ctx.guild else 'DM'}:{ctx.guild.id if ctx.guild else 'N/A'}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
            pass  # Ignore unknown commands
        elif isinstance(error, commands.CheckFailure):
            pass  # Permission denied, already logged
        else:
            # Handle other types of errors
            if ctx.guild:
                logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
            else:
                logger.debug("Command error in DM")
            logger.error(f"Error in command '{ctx.command}': {error.__class__.__name__}: {error}")
            await ctx.send(f"Error in command '{ctx.command}': {error.__class__.__name__}: {error}")

    return bot

async def process_message(bot, message, config):
    """Process an incoming message for OCR if needed"""
    try:
        # Check if message should be processed for OCR
        if message.guild and str(message.guild.id) in config['ocr_read_channels']:
            guild_id = str(message.guild.id)
            
            if guild_id not in config['ocr_read_channels']:
                logger.info(f'No read channels found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
                config['ocr_read_channels'][guild_id] = []
                from config.config_manager import save_config
                save_config(config)
                
            if message.channel.id in config['ocr_read_channels'][guild_id]:
                # Validate if the message contains OCR-processable content before queueing
                has_valid_image = False
                
                # Check for valid attachments
                if message.attachments:
                    attachment = message.attachments[0]
                    logger.debug(f"Received a help request:\nServer: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + (f" Parent:{message.channel.parent}" if hasattr(message.channel, 'type') and message.channel.type in ['public_thread', 'private_thread'] else ""))
                    logger.debug(f'Received an attachment of size: {attachment.size}')
                    
                    # Validate image attachment
                    if (attachment.size < 500000 and 
                        attachment.content_type and 
                        attachment.content_type.startswith('image/') and
                        hasattr(attachment, 'width') and
                        hasattr(attachment, 'height') and
                        attachment.width > 300 and 
                        attachment.height > 200):
                        
                        logger.debug(f'Valid image attachment found: {attachment.url}')
                        has_valid_image = True
                    else:
                        # Invalid image, skip queueing
                        if attachment.content_type and attachment.content_type.startswith('image/'):
                            if not (hasattr(attachment, 'width') and hasattr(attachment, 'height') and attachment.width > 300 and attachment.height > 200):
                                await respond_to_ocr(bot, message, 'Images must be at least 300x200 pixels.')
                        else:
                            await respond_to_ocr(bot, message, 'Please attach or link an image (no GIFs) with a size less than 500KB.')
                else:
                    # No attachments, check for image URLs
                    import re
                    urls = re.findall(r'(https?://\S+)', message.content)
                    if urls:
                        # Assume the first URL is the image link
                        logger.debug(f'Checking URL for valid image: {urls[0]}')
                        try:
                            import requests
                            from PIL import Image
                            import io
                            
                            response = requests.head(urls[0], timeout=5)
                            content_type = response.headers.get('content-type')
                            content_length = int(response.headers.get('content-length', 0))
                            
                            if content_type and content_type.startswith('image/') and content_length < 500000:
                                # Download a bit of the image to check dimensions
                                image_response = requests.get(urls[0], timeout=5)
                                img_data = io.BytesIO(image_response.content)
                                img = Image.open(img_data)
                                width, height = img.size
                                
                                if width > 300 and height > 200:
                                    logger.debug(f"Valid image URL found: {urls[0]}")
                                    has_valid_image = True
                                else:
                                    await respond_to_ocr(bot, message, 'Images must be at least 300x200 pixels.')
                            else:
                                # Not a valid image URL
                                if urls[0].lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                                    await respond_to_ocr(bot, message, 'Please attach or link an image (no GIFs) with a size less than 500KB.')
                        except Exception as e:
                            logger.debug(f"Error checking image URL: {e}")
                
                # Only queue if we have a valid image
                if has_valid_image:
                    # Apply backpressure handling
                    try:
                        # Try to add the message to the queue with a timeout
                        # This prevents the bot from hanging indefinitely if the queue is full
                        timeout = 5.0  # 5 seconds timeout
                        
                        # Check if queue is close to capacity before trying to add
                        if bot.ocr_queue.qsize() >= bot.ocr_queue.maxsize * 0.9:  # 90% full
                            logger.warning(f"OCR queue is at {bot.ocr_queue.qsize()}/{bot.ocr_queue.maxsize} capacity - approaching limit")
                        
                        await asyncio.wait_for(bot.ocr_queue.put(message), timeout=timeout)
                        
                        # Update statistics
                        bot.ocr_queue_stats['total_enqueued'] += 1
                        current_size = bot.ocr_queue.qsize()
                        if current_size > bot.ocr_queue_stats['high_watermark']:
                            bot.ocr_queue_stats['high_watermark'] = current_size
                            
                        logger.debug(f"Queued message for OCR processing: {message.id} (queue size: {bot.ocr_queue.qsize()})")
                        
                    except asyncio.TimeoutError:
                        # Queue is full and we timed out waiting
                        bot.ocr_queue_stats['total_rejected'] += 1
                        logger.error(f"OCR queue full - rejecting message {message.id} from {message.guild.name}")
                        # Optionally notify the user that the system is busy
                        try:
                            await message.add_reaction("⏳")  # Hourglass to indicate system busy
                        except Exception:
                            pass  # Ignore if we can't add reaction
    except Exception as e:
        logger.error(f"Error processing message for OCR: {e}")

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
                
                # Update statistics
                bot.ocr_queue_stats['total_processed'] += 1
                
            except Exception as e:
                logger.error(f"Worker {worker_id} error processing OCR task: {e}")
            finally:
                # Always mark task as done
                bot.ocr_queue.task_done()
                
        except Exception as e:
            logger.error(f"Error in OCR worker {worker_id}: {e}")
            # Sleep briefly to prevent tight error loops
            await asyncio.sleep(1)

async def load_cogs(bot):
    """Load all cogs for the bot"""
    # Load all cogs
    error_occurred = False
    for cog_file in cogs:
        full_cog = f"cogs.{cog_file}"  # Prepend folder name
        try:
            await bot.load_extension(full_cog)
        except Exception as e:
            logger.error(f"Failed to load extension {full_cog}: {e}")
            error_occurred = True
        else:
            logger.debug(f"Loaded extension: {full_cog}")

    if not error_occurred:
        logger.info(f"All {len(cogs)} cogs loaded successfully")
    
    # Apply command categories after all cogs are loaded
    apply_command_categories(bot)

def get_ocr_queue_stats(bot):
    """Get statistics about the OCR queue"""
    stats = bot.ocr_queue_stats.copy()
    stats['current_size'] = bot.ocr_queue.qsize()
    stats['max_size'] = bot.ocr_queue.maxsize
    stats['utilization_pct'] = (stats['current_size'] / stats['max_size'] * 100) if stats['max_size'] > 0 else 0
    return stats
