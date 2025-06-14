import os
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
import re
# Import chatbot_manager directly here for config access
from utils.chatbot_manager import chatbot_manager, DEFAULT_CHATBOT_CONFIG

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

        # --- Set bot's user ID in chatbot_manager ---
        # from utils.chatbot_manager import chatbot_manager # Already imported above
        chatbot_manager.set_bot_user_id(bot.user.id)
        logger.info(f"ChatbotManager bot_user_id set to {bot.user.id}")
        # --- END NEW ---

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
        
        # Schedule user index cleanup task
        async def cleanup_user_index_task():
            while True:
                try:
                    await asyncio.sleep(3600)  # Wait 1 hour before first cleanup
                    from utils.chatbot_manager import chatbot_manager
                    total_cleaned = chatbot_manager.cleanup_all_stale_users(bot.guilds)
                    if total_cleaned > 0:
                        logger.info(f"Periodic cleanup: removed {total_cleaned} stale users")
                except Exception as e:
                    logger.error(f"Error in periodic user index cleanup: {e}")
                
        bot.log_cleanup_task = asyncio.create_task(cleanup_logs_task())
        bot.user_cleanup_task = asyncio.create_task(cleanup_user_index_task())
        logger.info("Resource monitoring and log management initialized")
        
        # Auto-index chatbot-enabled channels on bot restart
        async def auto_index_on_restart():
            try:
                # from utils.chatbot_manager import chatbot_manager # Already imported above

                config_data = chatbot_manager.config_cache.get("global", {})
                if config_data.get("auto_index_on_restart", True):
                    logger.info("Starting chatbot channel re-indexing on bot restart...")

                    # Get enabled channels directly from config file structure
                    # Use the loaded config cache
                    enabled_channels_config = chatbot_manager.config_cache.get("channels", {})

                    if not enabled_channels_config:
                        logger.info("No chatbot-enabled channels found in config for re-indexing")
                        return

                    total_channels_indexed = 0
                    total_users_cleaned = 0 # This cleanup is done guild-wide after all channels in a guild are indexed
                    total_pins_indexed = 0 # For pins

                    # Iterate through all guilds the bot is in
                    for guild in bot.guilds:
                        guild_id = guild.id
                        guild_key = str(guild_id)

                        # Check if this guild has any channels enabled in the config
                        if guild_key in enabled_channels_config:
                            enabled_channel_ids_in_config = set(int(cid) for cid, data in enabled_channels_config[guild_key].items() if data.get("enabled", False))

                            if not enabled_channel_ids_in_config:
                                logger.debug(f"No enabled channels found in config for guild {guild.name} ({guild_id})")
                                continue

                            guild_channels_indexed = 0

                            # Get all channels and threads in the guild
                            # Fetch threads separately as guild.channels only gets top-level channels
                            # guild.threads is a list of all threads the bot is currently aware of in the guild
                            all_guild_channels_and_threads = list(guild.channels) + list(guild.threads)


                            # Iterate through all channels and threads to find the enabled ones
                            for channel_object in all_guild_channels_and_threads:
                                # Ensure it's a type we can index (TextChannel or Thread) and is in the enabled list
                                # discord.Thread objects inherit from discord.TextChannel as of discord.py 2.0+
                                if isinstance(channel_object, (discord.TextChannel, discord.Thread)) and channel_object.id in enabled_channel_ids_in_config:
                                    try:
                                        logger.debug(f"Indexing enabled channel/thread #{channel_object.name} ({channel_object.id}) in guild {guild.name} ({guild_id})")
                                        success = await chatbot_manager.index_chatbot_channel(guild_id, channel_object.id, channel_object)
                                        if success:
                                            # Index pinned messages if applicable (TextChannel and Thread objects both have .pins())
                                            indexed_pins = await chatbot_manager.index_pinned_messages(guild_id, channel_object.id, channel_object)
                                            total_pins_indexed += indexed_pins

                                            guild_channels_indexed += 1
                                            # Increment total count outside the inner loop
                                            # total_channels_indexed += 1 # This line should be outside the inner loop, moved below
                                            logger.debug(f"Re-indexed chatbot channel/thread and pins (if applicable) #{channel_object.name} in {guild.name}")
                                    except Exception as e:
                                        logger.error(f"Error indexing channel/thread {channel_object.id} in guild {guild.name}: {e}", exc_info=True)

                            # Increment total channels indexed by the number of channels/threads indexed in this guild
                            total_channels_indexed += guild_channels_indexed

                            # Perform cleanup of users not in current context for this guild
                            try:
                                # This should ideally be done after all *relevant* channels in a guild are processed,
                                # or as a separate periodic task. Doing it per guild after its channels are processed
                                # seems reasonable for startup.
                                cleaned_users = chatbot_manager.cleanup_stale_users(guild_id)
                                total_users_cleaned += cleaned_users
                                if cleaned_users > 0:
                                    logger.debug(f"Cleaned up {cleaned_users} stale users in guild {guild.name}")
                            except Exception as e:
                                logger.error(f"Error cleaning up users in guild {guild.name}: {e}")

                    logger.info(f"Chatbot re-indexing on restart complete: {total_channels_indexed} channels/threads indexed, {total_pins_indexed} pinned messages indexed, {total_users_cleaned} stale users cleaned across guilds with enabled channels")
                else:
                    logger.debug("Auto-indexing on restart is disabled")
            except Exception as e:
                logger.error(f"Error during chatbot channel re-indexing on restart: {e}")
        
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
            from utils.chatbot_manager import chatbot_manager

            #logger.debug(f"Checking chatbot enabled for guild {guild_id}, channel {channel_id} for raw edit")

            # Check if chatbot mode is enabled for this channel
            if chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
                #logger.debug(f"Attempting to edit message {message_id} in conversation history via raw event")
                result = chatbot_manager.edit_message_in_conversation(guild_id, channel_id, message_id, new_content)
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
            from utils.chatbot_manager import chatbot_manager
            guild_id = payload.guild_id
            channel_id = payload.channel_id
            message_id = payload.message_id

            #logger.debug(f"Checking chatbot enabled for guild {guild_id}, channel {channel_id} for raw delete")
            
            # Check if chatbot mode is enabled for this channel
            if chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
                #logger.debug(f"Attempting to delete message {message_id} from conversation history via raw event")
                result = chatbot_manager.delete_message_from_conversation(guild_id, channel_id, message_id)
                #logger.debug(f"Raw delete result: {result}")
            #else:
                #logger.debug("Chatbot not enabled for this channel for raw delete")
        except Exception as e:
            logger.error(f"Error handling raw deleted message: {e}", exc_info=True)
    
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
            # logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if hasattr(ctx.channel, 'type') and ctx.channel.type in ['public_thread', 'private_thread'] else ""))
            pass  # Ignore unknown commands
        elif isinstance(error, commands.CheckFailure):
            # This handles cases where a permission check fails.
            # The permission system itself should handle sending a user-friendly error message,
            # so we just pass here to avoid duplicate or generic error messages.
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
                await ctx.send(f"An unexpected error occurred: ```{error_details}```", delete_after=20)
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

async def process_chatbot_message(bot, message):
    """Process a message for chatbot mode if enabled"""
    try:
        # Skip bot messages
        if message.author.bot:
            return
        
        # Only process guild messages
        if not message.guild:
            return

        # from utils.chatbot_manager import chatbot_manager # Already imported above

        guild_id = message.guild.id
        channel_id = message.channel.id
        
        # Check if chatbot mode is enabled for this channel
        if not chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
            return
        
        # Always add the message to conversation history if chatbot is enabled
        chatbot_manager.add_message_to_conversation(guild_id, channel_id, message, bot.user.id) # Pass bot.user.id
        
        # Check if we should respond to this message
        if chatbot_manager.should_respond_to_message(guild_id, channel_id, message, bot.user.id):
            logger.debug(f"Processing chatbot response for message {message.id} in channel {channel_id}")
            
            # Create a task to handle the response asynchronously
            asyncio.create_task(handle_chatbot_response(bot, message))
        
    except Exception as e:
        logger.error(f"Error processing chatbot message: {e}")

async def handle_chatbot_response(bot, message):
    """Handle generating and sending a chatbot response"""
    try:
        from cogs.llm_commands import LLMCommands # Import LLMCommands here to use its methods

        # from utils.chatbot_manager import chatbot_manager # Already imported above

        guild_id = message.guild.id
        channel_id = message.channel.id
        
        # Get channel configuration
        channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
        
        # Get LLM cog to use existing LLM functionality
        llm_cog: LLMCommands = bot.get_cog('LLMCommands') # Type hint for better IDE support
        if not llm_cog:
            logger.error("LLMCommands cog not found for chatbot response")
            return

        # Check if LLM is online (uses the LLMCommands cog's check logic)
        # Pass guild_id to check_llm_status if it's a local LLM
        current_llm_config = llm_cog.get_llm_config(guild_id) # Get LLM config for this guild
        current_provider = current_llm_config.get("provider", "local")

        is_online = False
        if current_provider == "local":
             is_online = await llm_cog.check_llm_status(guild_id) # Check local LLM status
        elif current_provider == "google_ai":
             is_online = llm_cog.is_online # Check Google AI status held by the cog instance

        if not is_online:
            logger.debug(f"LLM not online for chatbot response in channel {channel_id}. Skipping response.")
            # await message.reply("I'm sorry, but my AI brain is currently offline. Please try again later.") # Avoid spamming offline message
            return

        # Apply response delay
        if channel_config.response_delay_seconds > 0:
            await asyncio.sleep(channel_config.response_delay_seconds)
        
        # Show typing indicator
        async with message.channel.typing():
            try:
                # Get prioritized context messages
                context_messages = chatbot_manager.get_prioritized_context(guild_id, channel_id, message.author.id)
                # Format all context (channel info, user info, conversation history, pinned messages) into a single string
                full_context_string = chatbot_manager.format_context_for_llm(context_messages, guild_id, channel_id)
                
                # Load system prompt (this loads from file and applies thinking mode if configured)
                system_prompt_for_llm = llm_cog.load_system_prompt(guild_id, thinking=False) # Chatbot typically doesn't show thinking
                
                # The raw user message content
                user_prompt_content = message.content
                
                # Remove bot mention from the user's prompt if present, so LLM doesn't see it as part of the query
                # This helps prevent the LLM from talking *about* being mentioned.
                # Re-implementing this here specifically for the *current* prompt being sent to make_llm_request.
                # The history already has mentions processed by _convert_discord_format_to_llm_readable.
                if bot.user and bot.user.mentioned_in(message):
                     # Use a regex to remove all mentions of the bot itself
                     bot_mention_pattern = re.compile(r'<@!?' + str(bot.user.id) + r'>')
                     user_prompt_content = bot_mention_pattern.sub('', user_prompt_content).strip()
                     logger.debug(f"Removed bot mention from user's prompt: '{user_prompt_content[:50]}...'")


                # Debug: Output the prompts to a file for inspection
                debug_dir = "llm_data/debug_prompts"
                os.makedirs(debug_dir, exist_ok=True)
                
                debug_filename = f"{debug_dir}/chatbot_prompt.txt"
                try:
                    with open(debug_filename, 'w', encoding='utf-8') as debug_file:
                        #debug_file.write("=== SYSTEM PROMPT ===\n")
                        debug_file.write((system_prompt_for_llm or "None") + "\n\n")
                        #debug_file.write("=== FULL CONTEXT (from chatbot_manager) ===\n")
                        debug_file.write((full_context_string or "None") + "\n\n")
                        #debug_file.write("=== USER'S CURRENT PROMPT (cleaned) ===\n")
                        debug_file.write((user_prompt_content or "None") + "\n")
                        #debug_file.write("=== RAW DISCORD MESSAGE CONTENT ===\n")
                        debug_file.write(message.content or "None")
                        #debug_file.write("\n\n--- END OF DEBUG ---\n")

                    logger.debug(f"Debug chatbot prompts written to: {debug_filename}")
                except Exception as debug_e:
                    logger.warning(f"Failed to write debug prompts to file: {debug_e}")


                response_text, performance_metrics = await llm_cog.make_llm_request(
                    #prompt=user_prompt_content,  # The current user's message content
                    system_prompt=system_prompt_for_llm, # The loaded system prompt
                    context=full_context_string, # The combined dynamic context
                    max_tokens=min(channel_config.max_response_length, 2000), # Limit response length (Discord limit is 2000)
                    guild_id=guild_id
                )

                if response_text:
                    # Note: Chatbot mode typically doesn't display thinking tokens to the user.
                    # We still strip them here to ensure the final response is clean.
                    cleaned_response, thinking_content = llm_cog.strip_thinking_tokens(response_text)

                    # Ensure response doesn't exceed Discord's character limit (2000)
                    if len(cleaned_response) > 2000:
                        logger.warning(f"LLM response ({len(cleaned_response)} chars) exceeds Discord limit (2000). Truncating.")
                        cleaned_response = cleaned_response[:1997] + "..."

                    # Send the response as a reply
                    sent_message = await message.reply(cleaned_response)

                    # Add the bot's response to conversation history
                    chatbot_manager.add_message_to_conversation(guild_id, channel_id, sent_message, bot.user.id) # Pass bot.user.id
                    
                    logger.info(f"Sent chatbot response to message {message.id} in channel {channel_id}")
                else:
                    await message.reply("I'm having trouble generating a response right now. Please try again.")
                    
            except Exception as llm_error:
                logger.error(f"Error generating LLM response for chatbot: {llm_error}")
                await message.reply("I encountered an error while thinking of a response. Please try again.")
        
    except Exception as e:
        logger.error(f"Error handling chatbot response: {e}")
        try:
            # await message.reply("I encountered an unexpected error. Please try again.") # Avoid excessive error messages
            pass
        except:
            pass  # Ignore if we can't even send error message

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
