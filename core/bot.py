import os
import discord
from discord.ext import commands
from core.ocr import respond_to_ocr
from utils.logging_setup import get_logger
import sys
import asyncio
from collections import defaultdict
from utils.log_manager import LogManager
from cogs import cogs
import re
# Import chatbot_manager directly here for config access
from utils.chatbot.manager import chatbot_manager
from utils.chatbot.config import DEFAULT_CHATBOT_CONFIG
from utils.file_processor import extract_text_from_attachment, extract_text_from_url
from utils.chatbot.models import ConversationMessage, ContentPart
from utils.discord_utils import reply_or_send, handle_streaming_text_response
from utils.media_cache import MediaCacheManager

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
    # Required for user index to get member roles and status
    intents.members = True
    intents.presences = True

    bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None, chunk_guilds_at_startup=False)
    
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
    bot.log_manager = LogManager()
    bot.media_cache_manager = MediaCacheManager(config, bot)

    # Chatbot message queue
    bot.chatbot_message_queues = defaultdict(asyncio.Queue)
    bot.chatbot_worker_tasks = {}
    
    # Set up event handlers
    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user.name}!')

        # --- Set bot's user ID in chatbot_manager and start it ---
        chatbot_manager.set_bot_user_id(bot.user.id)
        chatbot_manager.set_media_cache_manager(bot.media_cache_manager)
        await chatbot_manager.index_manager.start()
        await bot.media_cache_manager.start()
        # --- END NEW ---

        # Get worker count from config (default to 2 workers if not specified)
        worker_count = config.get('ocr_worker_count', 2)
        logger.info(f"Starting {worker_count} OCR workers")
        
        # Start multiple OCR workers
        for i in range(worker_count):
            asyncio.create_task(ocr_worker(bot, worker_id=i+1))
        
        # Schedule log cleanup task to run daily
        async def cleanup_logs_task():
            while True:
                try:
                    bot.log_manager.cleanup_old_logs()
                except Exception as e:
                    logger.error(f"Error cleaning up logs: {e}")
                await asyncio.sleep(86400)  # 24 hours
        
        # Schedule user index cleanup task
        async def cleanup_user_index_task():
            while True:
                try:
                    # Wait 24 hours before first cleanup and between subsequent cleanups
                    await asyncio.sleep(86400)
                    logger.info("Starting daily stale user cleanup...")
                    total_cleaned = await chatbot_manager.cleanup_all_stale_users(bot.guilds)
                    if total_cleaned > 0:
                        logger.info(f"Daily cleanup complete: removed {total_cleaned} stale users.")
                    else:
                        logger.info("Daily cleanup complete: no stale users found.")
                except Exception as e:
                    logger.error(f"Error in periodic user index cleanup: {e}", exc_info=True)
                
        bot.log_cleanup_task = asyncio.create_task(cleanup_logs_task())
        bot.user_cleanup_task = asyncio.create_task(cleanup_user_index_task())
        logger.info("Resource monitoring and log management initialized")
        
        # Auto-index chatbot-enabled channels on bot restart
        async def auto_index_on_restart():
            try:
                config_data = chatbot_manager.config_cache.get("global", {})
                if not config_data.get("auto_index_on_restart", True):
                    logger.debug("Auto-indexing on restart is disabled")
                    return

                logger.info("Starting concurrent chatbot channel re-indexing...")
                
                enabled_channels_config = chatbot_manager.config_cache.get("channels", {})
                if not enabled_channels_config:
                    logger.info("No chatbot-enabled channels found in config for re-indexing.")
                    return

                tasks = []
                guilds_with_indexed_channels = set()

                async def index_channel_and_pins(guild, channel):
                    """Helper function to index a channel and its pins, returning results."""
                    try:
                        logger.debug(f"Starting indexing for #{channel.name} in {guild.name}")
                        history_success = await chatbot_manager.index_chatbot_channel(guild.id, channel.id, channel)
                        
                        pins_indexed = 0
                        if history_success and isinstance(channel, (discord.TextChannel, discord.Thread)):
                            pins_indexed = await chatbot_manager.index_pinned_messages(channel)
                        
                        logger.debug(f"Finished indexing for #{channel.name}. Success: {history_success}, Pins: {pins_indexed}")
                        return {"success": history_success, "pins": pins_indexed, "guild_id": guild.id}
                    except Exception as e:
                        logger.error(f"Error in indexing task for channel {channel.id} in guild {guild.id}: {e}", exc_info=True)
                        return {"success": False, "pins": 0, "guild_id": guild.id, "error": e}

                for guild in bot.guilds:
                    guild_key = str(guild.id)
                    if guild_key not in enabled_channels_config:
                        continue

                    enabled_channel_ids = {int(cid) for cid, data in enabled_channels_config[guild_key].items() if data.get("enabled")}
                    if not enabled_channel_ids:
                        continue
                    
                    all_guild_channels = list(guild.channels) + list(guild.threads)
                    for channel in all_guild_channels:
                        if channel.id in enabled_channel_ids:
                            tasks.append(index_channel_and_pins(guild, channel))
                            guilds_with_indexed_channels.add(guild.id)

                if not tasks:
                    logger.info("No channels to index after filtering.")
                    return

                logger.info(f"Gathered {len(tasks)} indexing tasks. Running concurrently...")
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                total_channels_indexed = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
                total_pins_indexed = sum(r.get("pins", 0) for r in results if isinstance(r, dict))
                failed_tasks = sum(1 for r in results if isinstance(r, Exception) or (isinstance(r, dict) and not r.get("success")))

                logger.info(f"Concurrent indexing complete. {total_channels_indexed} channels succeeded, {failed_tasks} failed.")
                
                # Cleanup stale users in guilds that had channels indexed
                total_users_cleaned = 0
                if guilds_with_indexed_channels:
                    logger.info(f"Cleaning up stale users for {len(guilds_with_indexed_channels)} guilds.")
                    for guild_id in guilds_with_indexed_channels:
                        try:
                            cleaned_count = await chatbot_manager.cleanup_stale_users(guild_id)
                            total_users_cleaned += cleaned_count
                        except Exception as e:
                            logger.error(f"Error during user cleanup for guild {guild_id}: {e}")

                logger.info(f"Chatbot re-indexing on restart complete: {total_channels_indexed} channels/threads indexed, {total_pins_indexed} pinned messages indexed, {total_users_cleaned} stale users cleaned.")

            except Exception as e:
                logger.error(f"Fatal error during chatbot channel re-indexing on restart: {e}", exc_info=True)
        
        # Start auto-indexing task
        asyncio.create_task(auto_index_on_restart())
        
        # Load cogs after bot is ready
        await load_cogs(bot)
    
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
            
        # Create a task for processing this message to avoid blocking the event handler
        asyncio.create_task(process_message(bot, message, config))
        
        await bot.process_commands(message)
    
    @bot.event
    async def on_raw_message_edit(payload):
        """Handle raw message edit events (for messages not in cache)"""
        #logger.debug(f"Raw message edit event: Message ID={payload.message_id}, Channel ID={payload.channel_id}, Guild ID={payload.guild_id}")
        
        # Extract necessary data from payload
        message_id = payload.message_id
        channel_id = payload.channel_id
        guild_id = payload.guild_id
        
        # The payload data contains the updated message information
        # We need the new content
        new_content = payload.data.get('content')
        
        # If content is not available in the payload (e.g., embed changes), skip
        if new_content is None:
            #logger.debug(f"Raw edit payload for message {message_id} does not contain content. Skipping.")
            return

        # Only handle edits in guild channels
        if guild_id is None:
            #logger.debug("Skipping raw edit - not in guild")
            return
        
        try:
            # Update message in conversation history if chatbot is enabled
            from utils.chatbot.manager import chatbot_manager

            #logger.debug(f"Checking chatbot enabled for guild {guild_id}, channel {channel_id} for raw edit")

            # Check if chatbot mode is enabled for this channel
            if chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
                #logger.debug(f"Attempting to edit message {message_id} in conversation history via raw event")
                result = await chatbot_manager.edit_message_in_conversation(guild_id, channel_id, message_id, new_content)
                #logger.debug(f"Raw edit result: {result}")
            #else:
                #logger.debug("Chatbot not enabled for this channel for raw edit")
        except Exception as e:
            logger.error(f"Error handling raw edited message: {e}", exc_info=True)

    @bot.event
    async def on_raw_message_delete(payload):
        """Handle raw message delete events (for messages not in cache)"""
        #logger.debug(f"Raw message delete event: Message ID={payload.message_id}, Channel ID={payload.channel_id}, Guild ID={payload.guild_id}")
        
        # Only handle deletions in guild channels
        if payload.guild_id is None:
            #logger.debug("Skipping raw delete - not in guild")
            return
        
        try:
            # Remove message from conversation history if chatbot is enabled
            from utils.chatbot.manager import chatbot_manager
            guild_id = payload.guild_id
            channel_id = payload.channel_id
            message_id = payload.message_id

            #logger.debug(f"Checking chatbot enabled for guild {guild_id}, channel {channel_id} for raw delete")
            
            # Check if chatbot mode is enabled for this channel
            if chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
                #logger.debug(f"Attempting to delete message {message_id} from conversation history via raw event")
                result = await chatbot_manager.delete_message_from_conversation(guild_id, channel_id, message_id)
                #logger.debug(f"Raw delete result: {result}")
            #else:
                #logger.debug("Chatbot not enabled for this channel for raw delete")
        except Exception as e:
            logger.error(f"Error handling raw deleted message: {e}", exc_info=True)

    @bot.event
    async def on_guild_remove(guild):
        """Handle the bot being removed from a guild."""
        logger.warning(f"Bot removed from guild: {guild.name} ({guild.id}). Cleaning up all associated data.")
        await chatbot_manager.cleanup_guild_data(guild.id)

    @bot.event
    async def on_guild_channel_delete(channel):
        """Handle a channel being deleted."""
        logger.info(f"Channel #{channel.name} ({channel.id}) deleted in guild {channel.guild.name}. Cleaning up associated data.")
        await chatbot_manager.cleanup_channel_data(channel.guild.id, channel.id)

    @bot.event
    async def on_guild_channel_update(before, after):
        """Handle a channel being updated (e.g., name, topic)."""
        if chatbot_manager.config_manager.is_chatbot_enabled(after.guild.id, after.id):
            logger.info(f"Chatbot-enabled channel #{after.name} was updated. Re-indexing channel info.")
            await chatbot_manager.indexing_manager.update_channel_index(after)

    @bot.event
    async def on_guild_channel_pins_update(channel, last_pin):
        """Handle pinned messages being updated in a channel."""
        if chatbot_manager.config_manager.is_chatbot_enabled(channel.guild.id, channel.id):
            logger.info(f"Pins updated in chatbot-enabled channel #{channel.name}. Re-indexing pins.")
            await chatbot_manager.index_pinned_messages(channel)
    
    # Global error handler
    @bot.event
    async def on_close():
        """Handle bot shutdown gracefully."""
        logger.info("Bot is shutting down. Performing cleanup...")
        await bot.media_cache_manager.shutdown()
        await chatbot_manager.index_manager.shutdown()
        logger.info("Cleanup complete.")

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
            # logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
            pass  # Ignore unknown commands
        elif isinstance(error, commands.CheckFailure):
            # This handles cases where a permission check fails.
            # We log this at INFO level as it's a common, expected event.
            logger.debug(f"Permission check failed for command '{ctx.command.name}' by user '{ctx.author}'.")
            pass
        else:
            # Handle other types of errors
            error_details = f"Error in command '{ctx.command}': {error.__class__.__name__}: {error}"
            if ctx.guild:
                logger.error(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}, Command: {ctx.command}, User: {ctx.author}: {error_details}", exc_info=True)
            else:
                logger.error(f"Command error in DM for user {ctx.author}: {error_details}", exc_info=True)
            
            # Send a generic error message to the user for unhandled errors
            try:
                await reply_or_send(ctx, f"An unexpected error occurred: ```{error_details}```", delete_after=20)
            except Exception as send_error:
                logger.error(f"Failed to send error message to user: {send_error}", exc_info=True)


    return bot

async def process_message(bot, message, config):
    """Process an incoming message for OCR if needed"""
    try:
        # First, check for chatbot mode processing
        await process_chatbot_message(bot, message)
        
        # Then continue with existing OCR processing
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

def _chatbot_worker_done_callback(bot, task: asyncio.Task):
    """Callback to clean up worker task references for the chatbot."""
    try:
        task.result()
    except asyncio.CancelledError:
        logger.info(f"Chatbot worker task {task.get_name()} was cancelled.")
    except Exception as e:
        logger.error(f"Chatbot worker task {task.get_name()} failed: {e}", exc_info=True)
    
    for channel_id, worker_task in list(bot.chatbot_worker_tasks.items()):
        if worker_task == task:
            logger.info(f"Cleaning up finished chatbot worker for channel {channel_id}.")
            del bot.chatbot_worker_tasks[channel_id]
            break

async def _chatbot_queue_worker(bot, channel_id: int):
    """Worker that processes messages for the chatbot feature in a single channel."""
    logger.info(f"Starting chatbot worker for channel {channel_id}")
    q = bot.chatbot_message_queues[channel_id]
    
    while True:
        try:
            message = await asyncio.wait_for(q.get(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.info(f"Chatbot worker for channel {channel_id} timing out due to inactivity.")
            break

        try:
            # Determine if we should respond or just log the message
            should_respond = chatbot_manager.should_respond_to_message(
                message.guild.id, channel_id, message, bot.user.id
            )

            if should_respond:
                logger.debug(f"Worker for {channel_id} processing response for message {message.id}")
                await handle_chatbot_response(bot, message)
            else:
                # If not responding, just add the message to history for context.
                await chatbot_manager.add_message_to_conversation(message.guild.id, channel_id, message)
                logger.debug(f"Worker for {channel_id} logged message {message.id} to history.")

        except Exception as e:
            logger.error(f"Error in chatbot worker for channel {channel_id} processing message {message.id}: {e}", exc_info=True)
        finally:
            q.task_done()
            
    logger.info(f"Stopping chatbot worker for channel {channel_id} as queue is empty.")

async def process_chatbot_message(bot, message):
    """Enqueue a message for chatbot processing if the feature is enabled."""
    try:
        if message.author.bot or not message.guild:
            return

        if chatbot_manager.is_chatbot_enabled(message.guild.id, message.channel.id):
            channel_id = message.channel.id
            logger.debug(f"Enqueuing chatbot message {message.id} for channel {channel_id}")
            await bot.chatbot_message_queues[channel_id].put(message)

            if channel_id not in bot.chatbot_worker_tasks or bot.chatbot_worker_tasks[channel_id].done():
                logger.info(f"Creating new chatbot worker for channel {channel_id}.")
                task = asyncio.create_task(_chatbot_queue_worker(bot, channel_id), name=f"chatbot-worker-{channel_id}")
                task.add_done_callback(lambda t: _chatbot_worker_done_callback(bot, t))
                bot.chatbot_worker_tasks[channel_id] = task
                
    except Exception as e:
        logger.error(f"Error enqueuing chatbot message: {e}", exc_info=True)

async def handle_chatbot_response(bot, message, stream: bool = True):
    """
    Handles the logic for generating and sending a chatbot response.
    This function is now called by the queue worker.
    """
    try:
        from cogs.llm_commands import LLMCommands
        guild_id = message.guild.id
        channel_id = message.channel.id
        channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
        llm_cog: LLMCommands = bot.get_cog('LLMCommands')

        if not llm_cog or not llm_cog.provider_status or not any(llm_cog.provider_status.values()):
            logger.warning(f"No LLM providers online for chatbot response in channel {channel_id}. Skipping.")
            return

        if channel_config.response_delay_seconds > 0:
            await asyncio.sleep(channel_config.response_delay_seconds)
        
        async with message.channel.typing():
            # The rest of the response generation logic remains largely the same.
            # The key change is that this entire block is now executed sequentially by the worker.
            context_messages = await chatbot_manager.get_prioritized_context(guild_id, channel_id, message.author.id)
            static_context, history_messages = await chatbot_manager.format_context_for_llm(context_messages, guild_id, channel_id)
            system_prompt_for_llm = llm_cog.load_system_prompt(guild_id, prompt_type="chat")

            bot_mention_pattern = f'<@!?{bot.user.id}>'
            if not re.search(bot_mention_pattern, message.content):
                message.content = f'<@{bot.user.id}> {message.content}'

            await chatbot_manager.add_message_to_conversation(guild_id, channel_id, message)

            cleaned_content, image_urls, other_urls = await chatbot_manager.conversation_manager._process_discord_message_for_context(message)
            
            extracted_text = []
            for attachment in message.attachments:
                if attachment.url in other_urls and not (attachment.content_type and attachment.content_type.startswith('image/')):
                    text = await extract_text_from_attachment(attachment)
                    if text: extracted_text.append(text)
            
            for url in other_urls:
                if any(url.lower().endswith(ext) for ext in ['.pdf', '.txt', '.log', '.ini']):
                    text = await extract_text_from_url(url)
                    if text: extracted_text.append(text)

            prompt_text = f"{' '.join(extracted_text)}\n\n{cleaned_content}" if extracted_text else cleaned_content

            prompt_conv_message = ConversationMessage(
                user_id=message.author.id, username=message.author.display_name,
                content=prompt_text, timestamp=message.created_at.timestamp(), message_id=message.id,
                is_bot_response=False, is_self_bot_response=False,
                referenced_message_id=getattr(message.reference, 'message_id', None) if message.reference else None,
                attachment_urls=image_urls,
                multimodal_content=[ContentPart(type="text", text=prompt_text)] + [ContentPart(type="image_url", image_url={"url": url}) for url in image_urls]
            )

            user_prompt_content = await chatbot_manager.formatter.format_single_message(
                msg=prompt_conv_message, history_messages=context_messages,
                guild_id=guild_id, channel_id=channel_id
            )

            response_data, model_name = await llm_cog.make_llm_request(
                prompt=user_prompt_content, system_prompt=system_prompt_for_llm,
                context=static_context, history=history_messages, model_type="chat",
                guild_id=guild_id, channel_id=channel_id, image_urls=image_urls,
                stream=stream
            )

            if stream:
                await handle_streaming_text_response(bot, message, response_data, model_name, llm_cog, max_messages=1)
                logger.info(f"Sent streaming chatbot response to message {message.id} in channel {channel_id}")
            else:
                # Non-streaming logic
                response_text = response_data
                if response_text:
                    formatted_response = await chatbot_manager.formatter.format_llm_output_for_discord(
                        text=response_text, guild_id=message.guild.id, bot_user_id=bot.user.id,
                        bot_names=["Mirrobot", "Helper Retirement Machine 9000"]
                    )
                    final_response, _ = llm_cog.strip_thinking_tokens(formatted_response)

                    if len(final_response) > 2000:
                        logger.warning(f"LLM response ({len(final_response)} chars) exceeds Discord limit (2000). Truncating intelligently.")
                        from utils.discord_utils import truncate_to_last_sentence
                        final_response = truncate_to_last_sentence(final_response, 2000)

                    sent_message = await reply_or_send(message, final_response)
                    await chatbot_manager.add_message_to_conversation(guild_id, channel_id, sent_message)
                    logger.info(f"Sent chatbot response to message {message.id} in channel {channel_id}")
                else:
                    await reply_or_send(message, "I'm having trouble generating a response right now. Please try again.", delete_after=10)

    except Exception as e:
        logger.error(f"Error in handle_chatbot_response for message {message.id}: {e}", exc_info=True)
        try:
            await reply_or_send(message, "I encountered an error while thinking of a response. Please try again.", delete_after=10)
        except Exception:
            pass

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
