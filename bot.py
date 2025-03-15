import json
import os
import discord
import pytesseract
from discord.ext import commands
import re  # Import the regular expressions module
import asyncio
import aiohttp
from PIL import Image
import time
import io
import subprocess
import tempfile
import logging
import colorlog
import sys
from datetime import datetime
import requests
import platform
from functools import wraps  # Add this import for better decorators
if platform.system() == 'Windows':
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add a custom filter to filter out Discord reconnection errors
class DiscordReconnectFilter(logging.Filter):
    """
    Filter to remove Discord's reconnection error messages and tracebacks from logs
    """
    def __init__(self):
        super().__init__()
        self.is_in_traceback = False
        
    def filter(self, record):
        # Skip reconnection messages from discord.client
        if record.name == 'discord.client' and 'Attempting a reconnect in' in record.getMessage():
            return False
        
        # Get the log message
        message = record.getMessage()
        
        # Skip empty error messages or direct cause messages
        if message.strip() == '' or 'The above exception was the direct cause of the following exception:' in message:
            return False
            
        # Detect if we're entering a traceback
        if 'Traceback (most recent call last):' in message:
            self.is_in_traceback = True
            return False
        
        # Continue filtering if we're in a traceback
        if self.is_in_traceback:
            # Check if this is a continuation of the traceback
            if message.strip() == '' or not any([
                '  File "' in message,  # Line showing file location
                '    ' in message,      # Indented code line
                'Error:' in message,    # Error type declaration
                'Exception:' in message,# Exception type declaration
                'The above exception was' in message, # Chained exception message
                message.strip() == ''   # Empty line in traceback
            ]):
                # We've exited the traceback
                self.is_in_traceback = False
            else:
                # Still in traceback, filter it out
                return False
        
        # Skip specific error patterns
        if any(msg in message for msg in [
            'getaddrinfo failed',
            'ClientConnectorError', 
            'Cannot connect to host gateway', 
            'WebSocket closed with 1000',
            'ConnectionClosed',
            'socket.gaierror',
            'aiohttp.client_exceptions',
        ]):
            return False
            
        return True

class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            # Skip lines that appear to be already formatted discord log messages
            if 'discord.' in line and ('[INFO' in line or '[ERROR' in line or '[DEBUG' in line or '[WARNING' in line):
                continue
            # Check if the line already contains log level indicators
            #logging.info(f'{line}')
            if '[INFO' in line or '[ERROR' in line:
                # Write directly to handlers to avoid double formatting
                for handler in self.logger.handlers:
                    handler.stream.write(line + '\n')
            else:
                # Use logger's formatting
                self.logger.log(self.log_level, line.rstrip())

        #for line in buf.rstrip().splitlines():
        #    cleaned_line = re.sub(r'^.*?\[INFO\s+\]\s+', '', line)
        #    cleaned_line = re.sub(r'^.*?\[ERROR\s+\]\s+', '', cleaned_line)
        #    self.logger.log(self.log_level, cleaned_line.rstrip())


    def flush(self):
        pass

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the logging level

# Create handlers for both file and console
log_filename = datetime.now().strftime('bot_%Y-%m-%d.log')
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setLevel(logging.DEBUG) 
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO) 

# Create a formatter and set it for both handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Create a colored formatter for the console handler using colorlog
console_formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(message)s',
    datefmt=None,
    reset=False,
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    },
    secondary_log_colors={},
    style='%'
)
console_handler.setFormatter(console_formatter)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Add the reconnect filter to the handlers
reconnect_filter = DiscordReconnectFilter()
file_handler.addFilter(reconnect_filter)
console_handler.addFilter(reconnect_filter)

# Configure the root discord logger to capture all discord.py modules
discord_logger = logging.getLogger('discord')
discord_logger.handlers = []  # Remove any existing handlers
discord_logger.setLevel(logging.DEBUG)
discord_logger.addHandler(file_handler)
discord_logger.addHandler(console_handler)
discord_logger.propagate = False  # Prevent double logging


# Redirect stdout and stderr to the logging system
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    config_file.close()
ocr_read_channels = config['ocr_read_channels']
ocr_response_channels = config['ocr_response_channels']
ocr_response_fallback = config['ocr_response_fallback']
# Add command permissions dict, defaulting to empty if not present
command_permissions = config.get('command_permissions', {})
# Add server prefixes dict, defaulting to empty if not present
server_prefixes = config.get('server_prefixes', {})

# Add at the top of the file with other global variables
SYSTEM_COMMANDS = ['shutdown', 'reload_patterns']  # Commands that only the owner can use

# Function to get the prefix for a server
def get_prefix(bot, message):
    # Default prefix is '!'
    default_prefix = config.get('command_prefix', '!')
    
    # Create list of prefixes - always include the bot mention as a universal prefix
    # This will allow users to use @Mirrobot command in any server
    prefixes = [f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']  # Bot mentions with space after
    
    # If in a DM or no guild, use the default prefix
    if message.guild is None:
        return default_prefix
    
    # Get server-specific prefix if it exists
    guild_id = str(message.guild.id)
    server_prefix = server_prefixes.get(guild_id, default_prefix)
    prefixes.append(server_prefix)
    
    return prefixes

def get_server_prefix(bot, message):
    # Default prefix is '!'
    default_prefix = config.get('command_prefix', '!')
    
    # If in a DM or no guild, use the default prefix
    if message.guild is None:
        return default_prefix
    
    # Get server-specific prefix if it exists
    guild_id = str(message.guild.id)
    return server_prefixes.get(guild_id, default_prefix)

# Create a custom check for command permissions
def has_command_permission():
    async def predicate(ctx):
        # System commands can only be used by the bot owner
        if ctx.command.name in SYSTEM_COMMANDS:
            try:
                app_info = await bot.application_info()
                return ctx.author.id == app_info.owner.id
            except Exception as e:
                logger.error(f"Error checking owner for system command: {e}")
                return False

        # Bot owner always has permission
        try:
            app_info = await bot.application_info()
            if ctx.author.id == app_info.owner.id:
                return True
        except Exception as e:
            logger.error(f"Error checking owner: {e}")
        
        # Server admins always have permission
        if ctx.guild and (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
            return True
        
        # Check if the user has permission
        if ctx.guild:
            guild_id = str(ctx.guild.id)
            user_id_str = str(ctx.author.id)
            user_roles = [str(role.id) for role in ctx.author.roles]
            
            # Check if user has specific permission as bot manager
            if guild_id in command_permissions and "users" in command_permissions[guild_id]:
                if "*" in command_permissions[guild_id]["users"] and user_id_str in command_permissions[guild_id]["users"]["*"]:
                    return True
            
            # Check for manager roles that have access to all commands
            if guild_id in command_permissions and "*" in command_permissions[guild_id]:
                manager_roles = command_permissions[guild_id]["*"]
                for role_id in manager_roles:
                    if role_id in user_roles:
                        return True
            
            # Check for specific command permission
            command_name = ctx.command.name
            
            # Check for specific user command permission
            if (guild_id in command_permissions and 
                "users" in command_permissions[guild_id] and 
                command_name in command_permissions[guild_id]["users"] and 
                user_id_str in command_permissions[guild_id]["users"][command_name]):
                return True
            
            # Check for specific role command permission
            if guild_id in command_permissions and command_name in command_permissions[guild_id]:
                allowed_roles = command_permissions[guild_id][command_name]
                for role_id in allowed_roles:
                    if role_id in user_roles:
                        return True
        
        # No permission found
        if ctx.guild:
            logger.debug(f"Permission denied: {ctx.author} tried to use {ctx.command}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        else:
            logger.debug(f"Permission denied: {ctx.author} tried to use {ctx.command} in DMs")
        return False
    
    return commands.check(predicate)

# Replace the command_category function with this improved version using functools.wraps
def command_category(category):
    """
    Decorator to add a category to a command.
    Properly handles coroutines and command objects.
    """
    def decorator(func):
        # If it's already a Command object
        if isinstance(func, commands.Command):
            func.category = category
            if hasattr(func, 'callback'):
                func.callback.category = category
            return func
        
        # For normal coroutine functions
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            
            # Set category on wrapper
            wrapper.category = category
            return wrapper
        else:
            # For regular functions
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            # Set category on wrapper
            wrapper.category = category
            return wrapper
    
    return decorator

# Remove default help command before bot setup
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# Map of regex flag strings to their actual values
REGEX_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
    "MULTILINE": re.MULTILINE,
    "ASCII": re.ASCII,
    "VERBOSE": re.VERBOSE,
    "UNICODE": re.UNICODE
}

# Global dictionary to store compiled responses with their patterns for each server
server_patterns = {}

def load_patterns():
    """Load patterns from the patterns.json file"""
    try:
        with open('patterns.json', 'r', encoding='utf-8') as f:
            pattern_data = json.load(f)
        
        # Compile regex patterns for each server
        for server_id, responses_list in pattern_data.items():
            server_patterns[server_id] = []
            for response_info in responses_list:
                response_id = response_info.get("response_id", 0)
                response_text = response_info.get("response", "")
                name = response_info.get("name", "")  # Add name field
                note = response_info.get("note", "")
                
                # Create a response object with compiled patterns
                response_obj = {
                    "response_id": response_id,
                    "response": response_text,
                    "name": name,  # Include name in response object
                    "note": note,
                    "patterns": []
                }
                
                # Compile each pattern for this response
                for pattern_info in response_info.get("patterns", []):
                    pattern_id = pattern_info.get("id", 0)
                    pattern_name = pattern_info.get("name", f"pattern_{pattern_id}")
                    pattern_str = pattern_info.get("pattern", "")
                    flags_str = pattern_info.get("flags", "")
                    url = pattern_info.get("url", "")
                    
                    # Parse and combine regex flags
                    flag_value = 0
                    if flags_str:
                        for flag in flags_str.split('|'):
                            if flag in REGEX_FLAGS:
                                flag_value |= REGEX_FLAGS[flag]
                    
                    # Compile the pattern
                    try:
                        compiled_pattern = re.compile(pattern_str, flag_value)
                        
                        # Add the compiled pattern to the response's patterns list
                        response_obj["patterns"].append({
                            "id": pattern_id,
                            "name": pattern_name,
                            "pattern": compiled_pattern,
                            "url": url
                        })
                    except re.error as e:
                        logger.error(f"Error compiling pattern {pattern_name} for response {response_id}: {e}")
                        
                # Only add responses that have at least one valid pattern
                if response_obj["patterns"]:
                    server_patterns[server_id].append(response_obj)
        
        logger.info(f"Successfully loaded patterns for {len(pattern_data)} servers")
        return True
    except Exception as e:
        logger.error(f"Error loading patterns: {e}")
        # If there's an error, initialize with empty patterns
        server_patterns.clear()
        return False

def save_patterns():
    """Save patterns back to the patterns.json file"""
    try:
        # Convert compiled patterns back to serializable format
        serializable_patterns = {}
        for server_id, responses_list in server_patterns.items():
            serializable_patterns[server_id] = []
            for response_info in responses_list:
                # Create a serializable response object
                serializable_response = {
                    "response_id": response_info["response_id"],
                    "response": response_info["response"],
                    "name": response_info.get("name", ""),  # Include name when saving
                    "note": response_info.get("note", ""),
                    "patterns": []
                }
                
                # Convert each pattern to serializable format
                for pattern_info in response_info["patterns"]:
                    # Get the pattern string and flags from the compiled regex
                    pattern_obj = pattern_info["pattern"]
                    pattern_str = pattern_obj.pattern
                    
                    # Determine flags
                    flags = []
                    if pattern_obj.flags & re.IGNORECASE:
                        flags.append("IGNORECASE")
                    if pattern_obj.flags & re.DOTALL:
                        flags.append("DOTALL")
                    if pattern_obj.flags & re.MULTILINE:
                        flags.append("MULTILINE")
                    if pattern_obj.flags & re.ASCII:
                        flags.append("ASCII")
                    if pattern_obj.flags & re.VERBOSE:
                        flags.append("VERBOSE")
                    if pattern_obj.flags & re.UNICODE:
                        flags.append("UNICODE")
                    
                    serializable_response["patterns"].append({
                        "id": pattern_info["id"],
                        "name": pattern_info["name"],
                        "pattern": pattern_str,
                        "flags": "|".join(flags),
                        "url": pattern_info.get("url", "")
                    })
                
                serializable_patterns[server_id].append(serializable_response)
        
        with open('patterns.json', 'w', encoding='utf-8') as f:
            json.dump(serializable_patterns, f, indent=2)
        
        logger.info(f"Successfully saved patterns for {len(serializable_patterns)} servers")
        return True
    except Exception as e:
        logger.error(f"Error saving patterns: {e}")
        return False

# Add helper function to find a response by ID or name
def find_response(server_id, response_id_or_name):
    """Find a response by ID or name in a server's patterns"""
    if server_id not in server_patterns:
        return None
    
    # Try to interpret as an integer (ID)
    try:
        response_id = int(response_id_or_name)
        # Search by ID
        for r in server_patterns[server_id]:
            if r["response_id"] == response_id:
                return r
    except ValueError:
        pass  # Not an integer, continue to name search
    
    # Search by name (case insensitive)
    for r in server_patterns[server_id]:
        if r.get("name", "").lower() == str(response_id_or_name).lower():
            return r
    
    return None

def get_server_patterns(server_id):
    """Get responses with patterns for a specific server with fallback to default patterns"""
    server_id_str = str(server_id)
    
    # If server has specific patterns, use those
    if server_id_str in server_patterns:
        return server_patterns[server_id_str]
    
    # Otherwise use default patterns
    if "default" in server_patterns:
        return server_patterns["default"]
    
    # If no patterns are found, return an empty list
    return []

def get_next_response_id(server_id):
    """Get the next available response ID for a server"""
    patterns = get_server_patterns(server_id)
    if not patterns:
        return 1
    
    # Find the highest response_id and add 1
    return max(response.get("response_id", 0) for response in patterns) + 1

def get_next_pattern_id(response):
    """Get the next available pattern ID within a response"""
    if not response.get("patterns"):
        return 1
    
    # Find the highest pattern ID and add 1
    return max(pattern.get("id", 0) for pattern in response["patterns"]) + 1

# Load patterns when the bot starts
load_patterns()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}!')

@bot.event
async def on_message(message):
    if str(message.guild.id) not in ocr_read_channels:
            logger.info(f'No read channels found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
            ocr_read_channels[str(message.guild.id)] = []
            with open('config.json', 'w') as config_file:
                config['ocr_read_channels'] = ocr_read_channels
                json.dump(config, config_file, indent=4)
                config_file.truncate()
    if message.author.bot:
        return
    #logger.debug(f"Server: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + (f" Parent:{message.channel.parent}" if message.channel.type == 'public_thread' or message.channel.type == 'private_thread' else ""))
    #logger.info(f'{message.author}:{message.content}')
    
    if message.channel.id in ocr_read_channels[str(message.guild.id)]:
        await process_pics(message)  # Ignore messages not in designated channels or threads

    await bot.process_commands(message)

async def process_pics(message):
    if message.attachments:
        attachment = message.attachments[0]
        logger.debug(f"Received a help request:\nServer: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + (f" Parent:{message.channel.parent}" if message.channel.type == 'public_thread' or message.channel.type == 'private_thread' else ""))
        logger.info(f'Received an attachment of size: {attachment.size}')
        if attachment.size < 500000 and attachment.content_type.startswith('image/'):
            if (attachment.width > 300 and attachment.height > 200):
                logger.info(f'URL: {attachment.url}')
                start_time = time.time()

                #await sniperTess(message, attachment, start_time)
                #start_time = time.time()
                await pytess(message, attachment, start_time)
            else:
                await respond_to_ocr(message, 'Images must be at least 300x200 pixels.')
        else:
            await respond_to_ocr(message, 'Please attach an image(no GIFs) with a size less than 500KB.')
    else:
        # Extract first URL from the message if no attachments are found
        urls = re.findall(r'(https?://\S+)', message.content)
        if urls:
            start_time = time.time()
            # Assume the first URL is the image link
            logger.info(f'Grabbing first URL: {urls[0]}')
            response = requests.head(urls[0])
            content_type = response.headers.get('content-type')
            if content_type is not None and content_type.startswith('image/'):
                image_response = requests.get(urls[0])
                width, height = check_image_dimensions(io.BytesIO(image_response.content))
                if width > 200 and height > 100:
                    logger.info("Content type is image")
                    attachment = type('FakeAttachment', (object,), {'url': urls[0], 'size': 999999, 'content_type': content_type})  # Fake attachment object
                    await pytess(message, attachment, start_time)
                #else:
                    #response = 'Please attach an image with dimensions larger than 200x100.'
                    #await respond_to_ocr(message, response)
            #else:
                #response = 'Please attach an image with text to extract the text from the image.'
                #await respond_to_ocr(message, response)

async def respond_to_ocr(message, response):
    if not response:
        logger.error('No response message found')
        return
    response_channel = None
    if str(message.guild.id) in ocr_response_channels and message.channel.id in ocr_response_channels[str(message.guild.id)]:
        await msg_reply(message,text=response)
    else:
        if str(message.guild.id) not in ocr_response_channels:
            logger.info(f'No response channel found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
            ocr_response_channels[str(message.guild.id)] = []
            with open('config.json', 'w') as config_file:
                config['ocr_response_channels'] = ocr_response_channels
                json.dump(config, config_file, indent=4)
                config_file.truncate()
        for channel_id in ocr_response_channels[str(message.guild.id)]:
            if channel_id not in ocr_read_channels[str(message.guild.id)]:
                response_channel = bot.get_channel(channel_id)
                break
        original_message_link = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}'
        if response_channel:
            sent_message = await response_channel.send(original_message_link)
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
            logger.debug(f"Response: {sent_message.content}")
            await msg_reply(sent_message, text=response)
        else:
            logger.error('No response channel found. Using fallback channel.')
            fallback_channels = ocr_response_fallback.get(str(message.guild.id))
            if fallback_channels:
                sent_message = await bot.get_channel(fallback_channels[0]).send(original_message_link)
                logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
                logger.debug(f"Response: {sent_message.content}")
                await msg_reply(sent_message, text=response)
            else:
                logger.error('No OCR response fallback channel configured for this server.')
                return

async def msg_reply(message, text):
    if len(text) == 0:
        logger.error('No text found to reply')
        return
        
    # Log the full message once before splitting
    logger.debug(f"Server: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + 
                (f" Parent:{message.channel.parent}" if message.channel.type == 'public_thread' or message.channel.type == 'private_thread' else ""))
    logger.info(f"Response: {text}")

    if len(text) > 2000:
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            await message.reply(chunk)
    else:
        await message.reply(text)

async def sniperTess(message, attachment, start_time):
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            if resp.status == 200:
                data = await resp.read()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    tmp_file.write(data)
                    tmp_file_path = tmp_file.name
                        # Call TesseractTesting.exe with the image file path
                result = subprocess.run(['TesseractTesting.exe', tmp_file_path], capture_output=True, text=True)
                text = result.stdout  # Assuming TesseractTesting.exe outputs the OCR text to stdout
                logger.info(f"Transcription took {time.time() - start_time} seconds.")
                await analyze_and_respond(message, text,start_time)
    await session.close()

async def pytess(message, attachment, start_time):
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            if resp.status == 200:
                data = io.BytesIO(await resp.read())
                image = Image.open(data)
                text = pytesseract.image_to_string(image,'eng')
                logger.info(f"Transcription took {time.time() - start_time} seconds.")
                await analyze_and_respond(message, text,start_time)

async def analyze_and_respond(message, text, start_time):
    logger.info(f'Analyzing text')
    pattern_found = False
    
    # Get responses with patterns for this server
    responses = get_server_patterns(message.guild.id)
    
    # For each response, check all its patterns
    for response in responses:
        for pattern in response["patterns"]:
            if pattern["pattern"].search(text):
                pattern_found = True
                logger.info(f'Pattern found: {pattern["name"]} (Response ID: {response["response_id"]})')
                
                # Log the match
                with open('succ.log', 'a', encoding='utf-8') as log:
                    log.write(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {message.author.name} - {response.get("response_id", "unknown")}-{pattern.get("name", "unnamed")}\n')
                    log.write(f'Response: {response["response"]}\n')
                    log.write(f'{text}\n')
                    log.close()
                
                # Send the response
                await respond_to_ocr(message, response["response"])
                logger.info(f"Total time taken: {time.time() - start_time} seconds.")
                return
    
    if not pattern_found:
        logger.info(f'No pattern found')
        await respond_to_ocr(message, text)
    logger.info(f"Total time taken: {time.time() - start_time} seconds.")

def check_image_dimensions(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
        return width, height

# Add this utility function before the commands
async def create_embed_response(ctx, title, description, fields, footer_text=None, thumbnail_url=None, footer_icon_url=None, url=None, author_name=None, author_icon_url=None, author_url=None):
    """
    Create a standardized embed response with proper formatting.
    
    Args:
        ctx: The command context
        title: The title of the embed
        description: The description text
        fields: List of dictionaries with 'name', 'value', and 'inline' keys
        footer_text: Optional text for the footer
        thumbnail_url: Optional URL for the thumbnail
        footer_icon_url: Optional URL for the footer icon
        url: Optional URL for the embed title hyperlink
        author_name: Optional custom author name for the embed
        author_icon_url: Optional custom author icon URL for the embed
        author_url: Optional custom author URL for the embed
    """
    embed_color = discord.Color.blue()
    
    # Create the embed with title and description
    embed = discord.Embed(title=title, url=url, description=description, color=embed_color)
    
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url, url=author_url)

    # Add thumbnail if provided
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    elif ctx.guild and ctx.guild.me.avatar:
        embed.set_thumbnail(url=ctx.guild.me.avatar.url)
    elif bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
        
    # Add all fields
    for field in fields:
        name = field.get('name', '')
        value = field.get('value', '')
        inline = field.get('inline', False)
        
        # Skip empty fields
        if not value:
            continue
            
        # Handle fields that are too long
        if len(value) > 1024:
            # Split into multiple fields
            parts = []
            current_part = ""
            lines = value.split('\n')
            for line in lines:
                if len(current_part + line + '\n') > 1024:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            if current_part:
                parts.append(current_part)
                
            # Add the parts as separate fields
            for i, part in enumerate(parts):
                if i == 0:
                    embed.add_field(name=name, value=part, inline=inline)
                else:
                    embed.add_field(name=f"{name} (continued)", value=part, inline=inline)
        else:
            embed.add_field(name=name, value=value, inline=inline)
    
    # Add footer if provided
    if footer_text:
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)
        
    await ctx.send(embed=embed)

@bot.command(name='add_ocr_read_channel', help='Add a channel where bot will scan images for OCR processing.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_read_channel 123456789012345678 or !add_ocr_read_channel #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def add_ocr_read_channel(ctx, channel_id: int):
    global ocr_read_channels  # Declare ocr_read_channels as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    # Check if the guild ID is in the config, if not, initialize it
    if guild_id not in ocr_read_channels:
        ocr_read_channels[guild_id] = []

    # Check if the channel ID already exists in the guild's OCR read channels
    if channel_id in ocr_read_channels[guild_id]:
        response = f'Channel {channel.mention} is already in the OCR read channels list for this server.'
    else:
        # Add the channel ID to the guild's OCR read channels
        ocr_read_channels[guild_id].append(channel_id)
        # Save the updated configuration
        with open('config.json', 'w') as config_file:
            config['ocr_read_channels'] = ocr_read_channels
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} added to OCR reading channels for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='remove_ocr_read_channel', help='Remove a channel from the OCR reading list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_read_channel 123456789012345678 or !remove_ocr_read_channel #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def remove_ocr_read_channel(ctx, channel_id: int):
    global ocr_read_channels  # Declare ocr_read_channels as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    if guild_id in ocr_read_channels and channel_id in ocr_read_channels[guild_id]:
        ocr_read_channels[guild_id].remove(channel_id)
        with open('config.json', 'w') as config_file:
            config['ocr_read_channels'] = ocr_read_channels
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} removed from OCR reading channels for this server.'
    else:
        response = f'Channel {channel.mention} is not in the OCR reading channels list for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='add_ocr_response_channel', help='Add a channel where bot will post OCR analysis results.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_response_channel 123456789012345678 or !add_ocr_response_channel #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def add_ocr_response_channel(ctx, channel_id: int):
    global ocr_response_channels  # Declare ocr_response_channels as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    # Check if the guild ID is in the config, if not, initialize it
    if guild_id not in ocr_response_channels:
        ocr_response_channels[guild_id] = []

    # Check if the channel ID already exists in the guild's OCR response channels
    if channel_id in ocr_response_channels[guild_id]:
        response = f'Channel {channel.mention} is already in the OCR response channels list for this server.'
    else:
        # Add the channel ID to the guild's OCR response channels
        ocr_response_channels[guild_id].append(channel_id)
        # Save the updated configuration
        with open('config.json', 'w') as config_file:
            config['ocr_response_channels'] = ocr_response_channels
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} added to OCR response channels for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='remove_ocr_response_channel', help='Remove a channel from the OCR response list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_response_channel 123456789012345678 or !remove_ocr_response_channel #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def remove_ocr_response_channel(ctx, channel_id: int):
    global ocr_response_channels  # Declare ocr_response_channels as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    if guild_id in ocr_response_channels and channel_id in ocr_response_channels[guild_id]:
        ocr_response_channels[guild_id].remove(channel_id)
        with open('config.json', 'w') as config_file:
            config['ocr_response_channels'] = ocr_response_channels
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} removed from OCR response channels for this server.'
    else:
        response = f'Channel {channel.mention} is not in the OCR response channels list for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='add_ocr_response_fallback', help='Add a fallback channel for OCR responses if no regular response channel is available.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_response_fallback 123456789012345678 or !add_ocr_response_fallback #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def add_ocr_response_fallback(ctx, channel_id: int):
    global ocr_response_fallback  # Declare ocr_response_fallback as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    # Check if the guild ID is in the config, if not, initialize it
    if guild_id not in ocr_response_fallback:
        ocr_response_fallback[guild_id] = []

    # Check if the channel ID already exists in the guild's OCR response fallback
    if channel_id in ocr_response_fallback[guild_id]:
        response = f'Channel {channel.mention} is already in the OCR response fallback list for this server.'
    else:
        # Add the channel ID to the guild's OCR response fallback
        ocr_response_fallback[guild_id].append(channel_id)
        # Save the updated configuration
        with open('config.json', 'w') as config_file:
            config['ocr_response_fallback'] = ocr_response_fallback
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} added to OCR response fallback for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='remove_ocr_response_fallback', help='Remove a channel from the OCR response fallback list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_response_fallback 123456789012345678 or !remove_ocr_response_fallback #channel-name')
@has_command_permission()
@command_category("OCR Configuration")
async def remove_ocr_response_fallback(ctx, channel_id: int):
    global ocr_response_fallback  # Declare ocr_response_fallback as global
    
    channel = bot.get_channel(channel_id)
    if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
        response = f'Channel ID {channel_id} is invalid'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    if guild_id in ocr_response_fallback and channel_id in ocr_response_fallback[guild_id]:
        ocr_response_fallback[guild_id].remove(channel_id)
        with open('config.json', 'w') as config_file:
            config['ocr_response_fallback'] = ocr_response_fallback
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        response = f'Channel {channel.mention} removed from OCR response fallback for this server.'
    else:
        response = f'Channel {channel.mention} is not in the OCR response fallback list for this server.'
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

# Define a command to shut down the bot
@bot.command(name='shutdown', help='Shut down the bot completely (owner only).\nNo arguments required.\nExample: !shutdown')
@commands.is_owner()  # Only the bot owner can use this command
@command_category("System")
async def shutdown(ctx):
    response ="Shutting down."
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.info(f"Response: {response}")
    await ctx.reply(response)
    await bot.close()  # Gracefully close the bot

@bot.command(name='set_prefix', help='Change the command prefix for this server.\nArguments: prefix (str) - The new prefix to use\nExample: !set_prefix $ or !set_prefix >')
@has_command_permission()
@command_category("Bot Configuration")
async def set_prefix(ctx, prefix: str):
    global server_prefixes
    
    if not ctx.guild:
        await ctx.reply("This command can only be used in a server.")
        return
    
    # Limit prefix length to prevent abuse
    if len(prefix) > 5:
        await ctx.reply("Prefix must be 5 characters or less.")
        return
    
    guild_id = str(ctx.guild.id)
    old_prefix = server_prefixes.get(guild_id, get_server_prefix(bot, ctx.message))
    server_prefixes[guild_id] = prefix
    
    # Save the updated configuration
    with open('config.json', 'w') as config_file:
        config['server_prefixes'] = server_prefixes
        json.dump(config, config_file, indent=4)
        config_file.truncate()
    
    response = f"Command prefix for this server has been changed from `{old_prefix}` to `{prefix}`"
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='reset_prefix', help='Reset the command prefix for this server to the default (!).\nNo additional arguments required.\nExample: {prefix}reset_prefix')
@has_command_permission()
@command_category("Bot Configuration")
async def reset_prefix(ctx):
    global server_prefixes
    
    if not ctx.guild:
        await ctx.reply("This command can only be used in a server.")
        return
    
    guild_id = str(ctx.guild.id)
    
    if guild_id in server_prefixes:
        old_prefix = server_prefixes[guild_id]
        del server_prefixes[guild_id]
        
        # Save the updated configuration
        with open('config.json', 'w') as config_file:
            config['server_prefixes'] = server_prefixes
            json.dump(config, config_file, indent=4)
            config_file.truncate()
        
        response = f"Command prefix for this server has been reset from `{old_prefix}` to the default `!`"
    else:
        response = f"Command prefix for this server is already set to the default `!`"
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

# Utility function to handle permission targets (either users or roles)
async def get_permission_target(ctx, target):
    """
    Convert a mention/ID to either a Role or User object.
    Returns a tuple of (target_object, target_id_str, is_role)
    """
    # First try to interpret as a role
    try:
        # Check if it's a role mention or ID
        role = await commands.RoleConverter().convert(ctx, target)
        return role, str(role.id), True
    except commands.RoleNotFound:
        # Not a role, try to interpret as a user
        try:
            # Check if it's a user mention or ID
            user = await commands.UserConverter().convert(ctx, target)
            return user, str(user.id), False
        except commands.UserNotFound:
            # Neither a role nor a user
            return None, None, None

@bot.command(name='add_command_role', help='Give a role or user permission to use a specific bot command.\nArguments: target (mention or ID) - The role/user to grant permission to\n           command_name (str) - The name of the command\nExample: !add_command_role @Moderators add_ocr_read_channel or !add_command_role @username add_ocr_read_channel')
@has_command_permission()
@command_category("Permissions")
async def add_command_role(ctx, target, command_name: str):
    global command_permissions  # Declare command_permissions as global
    
    # Get the target (either role or user)
    target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
    
    # Check if target is valid
    if not target_obj:
        response = f'Could not find role or user "{target}"'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return
    
    # Verify the command exists
    if command_name not in [cmd.name for cmd in bot.commands]:
        response = f'Command {command_name} does not exist'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    
    # Initialize the command_permissions structure as needed
    if guild_id not in command_permissions:
        command_permissions[guild_id] = {}
    
    if is_role:
        # Handle role permissions
        if command_name not in command_permissions[guild_id]:
            command_permissions[guild_id][command_name] = []
            
        # Check if the role ID already exists for this command
        if target_id_str in command_permissions[guild_id][command_name]:
            response = f'Role {target_obj.name} already has permission to use the {command_name} command.'
        else:
            # Add the role ID to the command's permissions
            command_permissions[guild_id][command_name].append(target_id_str)
            response = f'Role {target_obj.name} added to permissions for the {command_name} command.'
    else:
        # Handle user permissions
        if "users" not in command_permissions[guild_id]:
            command_permissions[guild_id]["users"] = {}
            
        if command_name not in command_permissions[guild_id]["users"]:
            command_permissions[guild_id]["users"][command_name] = []
            
        # Check if the user ID already exists for this command
        if target_id_str in command_permissions[guild_id]["users"][command_name]:
            response = f'User {target_obj.name} already has permission to use the {command_name} command.'
        else:
            # Add the user ID to the command's permissions
            command_permissions[guild_id]["users"][command_name].append(target_id_str)
            response = f'User {target_obj.name} added to permissions for the {command_name} command.'
    
    # Save the updated configuration
    with open('config.json', 'w') as config_file:
        config['command_permissions'] = command_permissions
        json.dump(config, config_file, indent=4)
        config_file.truncate()
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='add_bot_manager', help='Add a role or user as a bot manager with access to all non-system commands.\nArguments: target (mention or ID) - The role/user to designate as bot manager\nExample: !add_bot_manager @Admins or !add_bot_manager @username')
@has_command_permission()
@command_category("Permissions")
async def add_bot_manager(ctx, target):
    global command_permissions  # Declare command_permissions as global
    
    # Get the target (either role or user)
    target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
    
    # Check if target is valid
    if not target_obj:
        response = f'Could not find role or user "{target}"'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return
    
    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    
    # Initialize the command_permissions structure as needed
    if guild_id not in command_permissions:
        command_permissions[guild_id] = {}
    
    if is_role:
        # Handle role manager permissions
        if "*" not in command_permissions[guild_id]:
            command_permissions[guild_id]["*"] = []
            
        # Check if the role ID already exists for manager role
        if target_id_str in command_permissions[guild_id]["*"]:
            response = f'Role {target_obj.name} is already a bot manager with access to all commands.'
        else:
            # Add the role ID to the manager list
            command_permissions[guild_id]["*"].append(target_id_str)
            response = f'Role {target_obj.name} has been added as a bot manager with access to all non-system commands.'
    else:
        # Handle user manager permissions
        if "users" not in command_permissions[guild_id]:
            command_permissions[guild_id]["users"] = {}
            
        if "*" not in command_permissions[guild_id]["users"]:
            command_permissions[guild_id]["users"]["*"] = []
            
        # Check if the user ID already exists for manager
        if target_id_str in command_permissions[guild_id]["users"]["*"]:
            response = f'User {target_obj.name} is already a bot manager with access to all commands.'
        else:
            # Add the user ID to the manager list
            command_permissions[guild_id]["users"]["*"].append(target_id_str)
            response = f'User {target_obj.name} has been added as a bot manager with access to all non-system commands.'
    
    # Save the updated configuration
    with open('config.json', 'w') as config_file:
        config['command_permissions'] = command_permissions
        json.dump(config, config_file, indent=4)
        config_file.truncate()
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='remove_command_role', help='Remove a role or user\'s permission to use a specific bot command.\nArguments: target (mention or ID) - The role/user to remove permission from\n           command_name (str) - The name of the command\nExample: !remove_command_role @Moderators add_ocr_read_channel or !remove_command_role @username add_ocr_read_channel')
@has_command_permission()
@command_category("Permissions")
async def remove_command_role(ctx, target, command_name: str):
    global command_permissions  # Declare command_permissions as global
    
    # Get the target (either role or user)
    target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
    
    # Check if target is valid
    if not target_obj:
        response = f'Could not find role or user "{target}"'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return
    
    # Verify the command exists
    if command_name not in [cmd.name for cmd in bot.commands]:
        response = f'Command {command_name} does not exist'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return

    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    
    if is_role:
        # Check if the role has any permissions for this command
        if (guild_id in command_permissions and 
            command_name in command_permissions[guild_id] and 
            target_id_str in command_permissions[guild_id][command_name]):
            
            # Remove the role ID from the command's permissions
            command_permissions[guild_id][command_name].remove(target_id_str)
            
            # If there are no more roles for this command, remove the command entry
            if not command_permissions[guild_id][command_name]:
                del command_permissions[guild_id][command_name]
            
            response = f'Role {target_obj.name} no longer has specific permission to use the {command_name} command.'
        else:
            response = f'Role {target_obj.name} does not have specific permission for the {command_name} command.'
    else:
        # Check if the user has any permissions for this command
        if (guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and
            command_name in command_permissions[guild_id]["users"] and 
            target_id_str in command_permissions[guild_id]["users"][command_name]):
            
            # Remove the user ID from the command's permissions
            command_permissions[guild_id]["users"][command_name].remove(target_id_str)
            
            # If there are no more users for this command, remove the command entry
            if not command_permissions[guild_id]["users"][command_name]:
                del command_permissions[guild_id]["users"][command_name]
                
                # If the users dict is empty, remove it
                if not command_permissions[guild_id]["users"]:
                    del command_permissions[guild_id]["users"]
            
            response = f'User {target_obj.name} no longer has specific permission to use the {command_name} command.'
        else:
            response = f'User {target_obj.name} does not have specific permission for the {command_name} command.'
    
    # Save the updated configuration
    with open('config.json', 'w') as config_file:
        config['command_permissions'] = command_permissions
        json.dump(config, config_file, indent=4)
        config_file.truncate()
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='remove_bot_manager', help='Remove a role or user from bot managers, revoking access to all commands.\nArguments: target (mention or ID) - The role/user to remove from manager status\nExample: !remove_bot_manager @Admins or !remove_bot_manager @username')
@has_command_permission()
@command_category("Permissions")
async def remove_bot_manager(ctx, target):
    global command_permissions  # Declare command_permissions as global
    
    # Get the target (either role or user)
    target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
    
    # Check if target is valid
    if not target_obj:
        response = f'Could not find role or user "{target}"'
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
        return
    
    guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
    
    if is_role:
        # Check if the role is a bot manager
        if (guild_id in command_permissions and 
            "*" in command_permissions[guild_id] and 
            target_id_str in command_permissions[guild_id]["*"]):
            
            # Remove the role ID from the manager list
            command_permissions[guild_id]["*"].remove(target_id_str)
            
            # If there are no more manager roles, remove the entry
            if not command_permissions[guild_id]["*"]:
                del command_permissions[guild_id]["*"]
            
            response = f'Role {target_obj.name} has been removed from bot managers and no longer has access to all commands.'
        else:
            response = f'Role {target_obj.name} is not a bot manager.'
    else:
        # Check if the user is a bot manager
        if (guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and
            "*" in command_permissions[guild_id]["users"] and 
            target_id_str in command_permissions[guild_id]["users"]["*"]):
            
            # Remove the user ID from the manager list
            command_permissions[guild_id]["users"]["*"].remove(target_id_str)
            
            # If there are no more manager users, remove the entry
            if not command_permissions[guild_id]["users"]["*"]:
                del command_permissions[guild_id]["users"]["*"]
                
                # If the users dict is empty, remove it
                if not command_permissions[guild_id]["users"]:
                    del command_permissions[guild_id]["users"]
            
            response = f'User {target_obj.name} has been removed from bot managers and no longer has access to all commands.'
        else:
            response = f'User {target_obj.name} is not a bot manager.'
    
    # Save the updated configuration
    with open('config.json', 'w') as config_file:
        config['command_permissions'] = command_permissions
        json.dump(config, config_file, indent=4)
        config_file.truncate()
    
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.debug(f"Response: {response}")
    await ctx.reply(response)

@bot.command(name='server_info', help='Display all bot configuration settings for this server.\nNo additional arguments required.\nExample: !server_info')
@has_command_permission()
@command_category("Bot Configuration")
async def server_info(ctx):
    if not ctx.guild:
        await ctx.reply("This command can only be used in a server.")
        return
    
    guild_id = str(ctx.guild.id)
    
    # Get current prefix
    current_prefix = server_prefixes.get(guild_id, config.get('command_prefix', '!'))
    
    # Get server icon URL for the thumbnail
    thumbnail_url = None
    if ctx.guild and ctx.guild.icon:
        thumbnail_url = ctx.guild.icon.url
    elif ctx.guild and ctx.guild.me.avatar:  # Fallback to bot's server avatar if no server icon
        thumbnail_url = ctx.guild.me.avatar.url
    elif bot.user.avatar:  # Fallback to bot's global avatar if no server icon
        thumbnail_url = bot.user.avatar.url
    
    # Create description with server prefix info
    description = f"Server configuration for **{ctx.guild.name}**\n\n**Current prefix:** `{current_prefix}`"
    
    # Build the fields
    fields = []
    
    # OCR Read Channels field
    ocr_read_value = ""
    if guild_id in ocr_read_channels and ocr_read_channels[guild_id]:
        for channel_id in ocr_read_channels[guild_id]:
            channel = bot.get_channel(channel_id)
            channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
            ocr_read_value += f"• {channel_name}\n"
    else:
        ocr_read_value = "No OCR read channels configured."
    fields.append({"name": "📷 OCR Read Channels", "value": ocr_read_value, "inline": False})
    
    # OCR Response Channels field
    ocr_response_value = ""
    if guild_id in ocr_response_channels and ocr_response_channels[guild_id]:
        for channel_id in ocr_response_channels[guild_id]:
            channel = bot.get_channel(channel_id)
            channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
            ocr_response_value += f"• {channel_name}\n"
    else:
        ocr_response_value = "No OCR response channels configured."
    fields.append({"name": "💬 OCR Response Channels", "value": ocr_response_value, "inline": False})
    
    # OCR Fallback Channels field
    ocr_fallback_value = ""
    if guild_id in ocr_response_fallback and ocr_response_fallback[guild_id]:
        for channel_id in ocr_response_fallback[guild_id]:
            channel = bot.get_channel(channel_id)
            channel_name = channel.mention if channel else f"Unknown Channel ({channel_id})"
            ocr_fallback_value += f"• {channel_name}\n"
    else:
        ocr_fallback_value = "No OCR fallback channels configured."
    fields.append({"name": "🔄 OCR Fallback Channels", "value": ocr_fallback_value, "inline": False})
    
    # Manager Roles field
    manager_roles_value = ""
    if guild_id in command_permissions and "*" in command_permissions[guild_id] and command_permissions[guild_id]["*"]:
        for role_id in command_permissions[guild_id]["*"]:
            role = ctx.guild.get_role(int(role_id))
            role_name = role.mention if role else f"Unknown Role ({role_id})"
            manager_roles_value += f"• {role_name}\n"
    else:
        manager_roles_value = "No bot manager roles configured."
    fields.append({"name": "👑 Bot Manager Roles", "value": manager_roles_value, "inline": False})
    
    # Manager Users field
    manager_users_value = ""
    if (guild_id in command_permissions and 
        "users" in command_permissions[guild_id] and 
        "*" in command_permissions[guild_id]["users"] and 
        command_permissions[guild_id]["users"]["*"]):
        for user_id in command_permissions[guild_id]["users"]["*"]:
            user = await bot.fetch_user(int(user_id))
            user_name = f"@{user.name}" if user else f"Unknown User ({user_id})"
            manager_users_value += f"• {user_name}\n"
    if not manager_users_value:
        manager_users_value = "No bot manager users configured."
    fields.append({"name": "👤 Bot Manager Users", "value": manager_users_value, "inline": False})
    
    # Command-specific permissions fields - Roles
    cmd_roles_value = ""
    if guild_id in command_permissions:
        for cmd_name, roles in sorted(command_permissions[guild_id].items()):
            if cmd_name not in ["*", "users"] and roles:  # Skip wildcard and users entries
                cmd_roles_value += f"**{cmd_name}**\n"
                for role_id in roles:
                    role = ctx.guild.get_role(int(role_id))
                    role_name = role.mention if role else f"Unknown Role ({role_id})"
                    cmd_roles_value += f"• {role_name}\n"
                cmd_roles_value += "\n"
    if not cmd_roles_value:
        cmd_roles_value = "No command-specific role permissions configured."
    fields.append({"name": "🔐 Command Role Permissions", "value": cmd_roles_value, "inline": False})
    
    # Command-specific permissions - Users
    cmd_users_value = ""
    if guild_id in command_permissions and "users" in command_permissions[guild_id]:
        for cmd_name, users in sorted(command_permissions[guild_id]["users"].items()):
            if cmd_name != "*" and users:  # Skip the wildcard entry
                cmd_users_value += f"**{cmd_name}**\n"
                for user_id in users:
                    try:
                        user = await bot.fetch_user(int(user_id))
                        user_name = f"@{user.name}" if user else f"Unknown User ({user_id})"
                        cmd_users_value += f"• {user_name}\n"
                    except:
                        cmd_users_value += f"• Unknown User ({user_id})\n"
                cmd_users_value += "\n"
    if not cmd_users_value:
        cmd_users_value = "No command-specific user permissions configured."
    fields.append({"name": "👤 Command User Permissions", "value": cmd_users_value, "inline": False})
    
    # Add footer
    footer_text = f"{ctx.guild.name} | Server ID: {ctx.guild.id}"
    
    # Use the universal embed response function
    await create_embed_response(
        ctx=ctx,
        title="Server Configuration",
        description=description,
        fields=fields,
        footer_text=footer_text,
        thumbnail_url=thumbnail_url
    )

@bot.command(name='help', aliases=['info'], help='Show info about the bot and its features.\nArguments: [command] (optional) - Get detailed help on a specific command\nExample: !help, !info or !help server_info')
@commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
@command_category("System")
async def help_command(ctx, command_name=None):
    """Display help information about the bot and its commands"""
    prefix = get_server_prefix(bot, ctx.message)
    
    # If a specific command is requested, show detailed help for that command
    if command_name:
        cmd = bot.get_command(command_name)
        if cmd:
            # Check if user has permission to use this command
            try:
                can_run = await cmd.can_run(ctx)
            except:
                can_run = False
                
            if not can_run:
                await ctx.send(f"You don't have permission to use the `{command_name}` command.")
                return
            
            # Build fields for specific command help    
            fields = []
            
            # Add category if available
            if hasattr(cmd, 'category'):
                fields.append({"name": "Category", "value": cmd.category, "inline": True})
            
            # Check for required arguments in the command signature
            signature = cmd.signature
            if signature:
                fields.append({"name": "Usage", "value": f"`{prefix}{cmd.name} {signature}`", "inline": False})
            else:
                fields.append({"name": "Usage", "value": f"`{prefix}{cmd.name}`", "inline": False})
                
            # Add aliases if any exist
            if cmd.aliases:
                aliases = ", ".join([f"{prefix}{alias}" for alias in cmd.aliases])
                fields.append({"name": "Aliases", "value": aliases, "inline": False})
            
            await create_embed_response(
                ctx=ctx,
                title=f"Command: {prefix}{cmd.name}",
                description=cmd.help or "No description available",
                fields=fields,
                footer_text=f"Type {prefix}help for a list of all commands"
            )
            return
        else:
            await ctx.send(f"No command called '{command_name}' found.")
            return

    # Create main description
    description = f"Use `{prefix}help <command>` for detailed information on a command.\n" \
                  f"**Note:** You only see commands you have permission to use.\n\n" \
                  f"**Current prefix:** `{prefix}`"
    
    # Define fields
    fields = []
    
    # Add bot info section
    fields.append({
        "name": "📝 About", 
        "value": "Mirrobot is an open-source bot developed by @Mirrowel.\n" \
                 "It uses OCR (Optical Character Recognition) to scan images for text patterns and provide automatic responses to common issues.\n",
        "inline": False
    })

    # Dynamically organize commands by their categories
    categories = {}
    for cmd in bot.commands:
        # Skip commands the user can't use
        try:
            if not await cmd.can_run(ctx):
                continue
        except:
            continue  # Skip if can_run raises an exception
        
        # Get the command's category (or "Miscellaneous" if not set)
        category = getattr(cmd, 'category', "Miscellaneous")
        
        # Add command to its category
        if category not in categories:
            categories[category] = []
        categories[category].append(cmd)
    
    # Process categories and add fields
    for category_name, cmds in sorted(categories.items()):
        if cmds:
            # Sort commands by name
            sorted_cmds = sorted(cmds, key=lambda x: x.name)
            
            # Format command list with brief descriptions
            command_entries = []
            for cmd in sorted_cmds:
                brief_desc = cmd.help.split('\n')[0] if cmd.help else "No description"
                command_entries.append(f"• `{prefix}{cmd.name}` - {brief_desc}")
            
            # Combine entries and check length
            category_value = "\n".join(command_entries)
            
            # If value is too long, break it into multiple fields
            if len(category_value) > 1024:
                # Calculate how to split entries into multiple fields
                parts = []
                current_part = []
                current_length = 0
                
                for entry in command_entries:
                    if current_length + len(entry) + 1 > 1024:  # +1 for the newline
                        parts.append("\n".join(current_part))
                        current_part = [entry]
                        current_length = len(entry) + 1
                    else:
                        current_part.append(entry)
                        current_length += len(entry) + 1
                        
                if current_part:
                    parts.append("\n".join(current_part))
                
                # Create multiple fields with proper naming
                for i, part in enumerate(parts):
                    field_name = f"📋 {category_name}"
                    if len(parts) > 1:
                        field_name += f" ({i+1}/{len(parts)})"
                    
                    fields.append({
                        "name": field_name,
                        "value": part,
                        "inline": False
                    })
            else:
                fields.append({
                    "name": f"📋 {category_name}",
                    "value": category_value,
                    "inline": False
                })
                
    # Add footer text
    footer_text = f"Mirrobot v0.15 | Type {prefix}help <command> for more info"
    
    # Send the response
    await create_embed_response(
        ctx=ctx,
        title="Mirrobot",
        url="https://github.com/Mirrowel/Mirrobot-py",  # clickable title
        author_name="Mirrowel",
        author_url="https://github.com/Mirrowel",
        author_icon_url="https://avatars.githubusercontent.com/u/28632877",
        description=description,
        fields=fields,
        footer_text=footer_text,
        footer_icon_url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
    )
    
@bot.command(name='reload_patterns', help='Reload pattern configurations from the patterns.json file.\nNo arguments required.\nExample: !reload_patterns')
@commands.is_owner()  # Only the bot owner can use this command
@command_category("System")
async def reload_patterns(ctx):
    """Reload patterns from the patterns.json file"""
    if load_patterns():
        await ctx.reply("Successfully reloaded pattern configurations.")
    else:
        await ctx.reply("Error loading pattern configurations. Check the log for details.")

@bot.command(name='list_patterns', help='List all pattern responses for this server.\nArguments: [detailed] (optional) - Show detailed pattern info\nExample: !list_patterns or !list_patterns detailed')
@has_command_permission()
@command_category("OCR Configuration")
async def list_patterns(ctx, option=None):
    """List all patterns for this server"""
    server_id = str(ctx.guild.id)
    
    server_specific = []
    default = []
    
    # Get server-specific patterns
    if server_id in server_patterns:
        server_specific = server_patterns[server_id]
    
    # Get default patterns
    if "default" in server_patterns:
        default = server_patterns["default"]
    
    if not server_specific and not default:
        await ctx.reply("No patterns found.")
        return
    
    # Determine if detailed view is requested
    detailed = option and option.lower() == "detailed"
    
    # Build fields for the embed response
    all_fields = []
    
    # Add server-specific patterns section
    if server_specific:
        # For keeping track of continuation fields
        server_patterns_continuation = 0
        server_patterns_value = ""
        
        for resp in server_specific:
            # Build response line
            resp_line = f"• ID {resp['response_id']}"
            if resp.get("name"):
                resp_line += f" [`{resp['name']}`]"
            resp_line += f": `{resp['response']}`"
            if resp.get("note"):
                resp_line += f" - {resp['note']}"
            resp_line += f" ({len(resp['patterns'])} patterns)\n"
            
            # Check if adding this line would exceed field value limit
            if len(server_patterns_value) + len(resp_line) > 1000:
                # Create field name based on whether this is the first field or a continuation
                field_name = "🔹 Server-specific responses"
                if server_patterns_continuation > 0:
                    field_name += f" (continued {server_patterns_continuation})"
                
                all_fields.append({"name": field_name, "value": server_patterns_value, "inline": False})
                server_patterns_continuation += 1
                server_patterns_value = resp_line
            else:
                server_patterns_value += resp_line
            
            # Add pattern details if detailed view is requested
            if detailed:
                pattern_details = ""
                for pattern in resp['patterns']:
                    pattern_str = pattern['pattern'].pattern
                    # Truncate pattern if too long
                    if len(pattern_str) > 40:
                        pattern_str = pattern_str[:37] + "..."
                    
                    pattern_line = f"  ↪ Pattern {pattern['id']}: `{pattern_str}`\n"
                    
                    if len(server_patterns_value + pattern_details + pattern_line) > 1000:
                        # Save current details and start a new field
                        if pattern_details:  # Add accumulated pattern details
                            server_patterns_value += pattern_details
                        
                        # Create field name with continuation indicator if needed
                        field_name = "🔹 Server-specific responses"
                        if server_patterns_continuation > 0:
                            field_name += f" (continued {server_patterns_continuation})"
                            
                        all_fields.append({"name": field_name, "value": server_patterns_value, "inline": False})
                        server_patterns_continuation += 1
                        server_patterns_value = ""
                        pattern_details = pattern_line
                    else:
                        pattern_details += pattern_line
                
                if pattern_details:
                    if len(server_patterns_value + pattern_details) > 1000:
                        # Create field name with continuation indicator if needed
                        field_name = "🔹 Server-specific responses"
                        if server_patterns_continuation > 0:
                            field_name += f" (continued {server_patterns_continuation})"
                            
                        all_fields.append({"name": field_name, "value": server_patterns_value, "inline": False})
                        server_patterns_continuation += 1
                        server_patterns_value = pattern_details
                    else:
                        server_patterns_value += pattern_details
        
        # Add remaining server patterns
        if server_patterns_value:
            # Create field name with continuation indicator if needed
            field_name = "🔹 Server-specific responses"
            if server_patterns_continuation > 0:
                field_name += f" (continued {server_patterns_continuation})"
                
            all_fields.append({"name": field_name, "value": server_patterns_value, "inline": False})
    
    # Add default patterns section
    if default:
        if detailed:
            # For keeping track of continuation fields
            default_patterns_continuation = 0
            default_patterns_value = ""
            
            for resp in default:
                # Build response line
                resp_line = f"• ID {resp['response_id']}"
                if resp.get("name"):
                    resp_line += f" [`{resp['name']}`]"
                resp_line += f": `{resp['response']}`"
                if resp.get("note"):
                    resp_line += f" - {resp['note']}"
                resp_line += f" ({len(resp['patterns'])} patterns)\n"
                
                # Check if adding this line would exceed field value limit
                if len(default_patterns_value) + len(resp_line) > 1000:
                    # Create field name based on whether this is the first field or a continuation
                    field_name = "🔸 Default responses"
                    if default_patterns_continuation > 0:
                        field_name += f" (continued {default_patterns_continuation})"
                    
                    all_fields.append({"name": field_name, "value": default_patterns_value, "inline": False})
                    default_patterns_continuation += 1
                    default_patterns_value = resp_line
                else:
                    default_patterns_value += resp_line
            
            # Add remaining default patterns
            if default_patterns_value:
                # Create field name with continuation indicator if needed
                field_name = "🔸 Default responses"
                if default_patterns_continuation > 0:
                    field_name += f" (continued {default_patterns_continuation})"
                    
                all_fields.append({"name": field_name, "value": default_patterns_value, "inline": False})
        else:
            # Just show the summary count for default patterns
            all_fields.append({
                "name": "🔸 Default responses", 
                "value": f"*{len(default)} responses available* - Use `detailed` option to see more", 
                "inline": False
            })
    
    # Split into multiple embeds if we have too many fields
    # Each embed can have a maximum of 25 fields
    embeds_to_send = []
    current_fields = []
    
    for field in all_fields:
        if len(current_fields) >= 25:  # Max fields per embed
            embeds_to_send.append(current_fields.copy())
            current_fields = [field]
        else:
            current_fields.append(field)
    
    if current_fields:  # Add any remaining fields
        embeds_to_send.append(current_fields)
    
    # Description for the embeds
    description = f"Pattern responses available for this server"
    if detailed:
        description += " (detailed view)"
    
    # Send the embeds
    total_parts = len(embeds_to_send)
    
    for i, fields in enumerate(embeds_to_send, 1):
        # Only add part numbers if multiple parts
        footer_text = None
        if total_parts > 1:
            footer_text = f"Page {i} of {total_parts}"
        
        await create_embed_response(
            ctx=ctx,
            title="Pattern Responses",
            description=description,
            fields=fields,
            footer_text=footer_text
        )

@bot.command(name='add_response', help='Add a new response with optional name and note.\nArguments: response (str) - The response text\n           [name] (str) - Optional friendly name for the response\n           [note] (str) - Optional description or explanation\nExample: !add_response "!v6fix" "v6fix_command" "Common v6 connection issues"')
@has_command_permission()
@command_category("OCR Configuration")
async def add_response(ctx, response: str, name: str = "", *, note: str = ""):
    """Add a new response to the server configuration with optional name and note"""
    server_id = str(ctx.guild.id)
    
    # Initialize server responses list if needed
    if server_id not in server_patterns:
        server_patterns[server_id] = []
    
    # Check if name already exists if a name is provided
    if name:
        for existing_response in server_patterns[server_id]:
            if existing_response.get("name", "").lower() == name.lower():
                await ctx.reply(f"A response with name '{name}' already exists. Please choose a different name.")
                return
    
    # Get the next available response ID
    response_id = get_next_response_id(server_id)
    
    # Create the new response object
    new_response = {
        "response_id": response_id,
        "response": response,
        "name": name,
        "note": note,
        "patterns": []
    }
    
    # Add the new response
    server_patterns[server_id].append(new_response)
    
    # Save patterns to file
    if save_patterns():
        name_info = f" (Named: '{name}')" if name else ""
        await ctx.reply(f"Successfully added response ID {response_id}{name_info}: `{response}`\nUse `!add_pattern_to_response {response_id if not name else name} \"your_pattern_here\"` to add patterns to this response.")
    else:
        await ctx.reply("Response added to memory but could not be saved to file. Check logs for details.")

@bot.command(name='remove_response', help='Remove a response and all its patterns.\nArguments: response_id_or_name - ID number or name of the response\nExample: !remove_response 5 or !remove_response v6fix_command')
@has_command_permission()
@command_category("OCR Configuration")
async def remove_response(ctx, response_id_or_name: str):
    """Remove a response from the server configuration"""
    server_id = str(ctx.guild.id)
    
    if server_id not in server_patterns:
        await ctx.reply("This server has no custom responses.")
        return
    
    # Find the response to remove
    for i, response in enumerate(server_patterns[server_id]):
        if (str(response["response_id"]) == response_id_or_name or 
            response.get("name", "").lower() == response_id_or_name.lower()):
            removed_response = server_patterns[server_id].pop(i)
            
            # Save patterns to file
            if save_patterns():
                name_info = f" [{removed_response.get('name')}]" if removed_response.get("name") else ""
                await ctx.reply(f"Successfully removed response ID {removed_response['response_id']}{name_info}: `{removed_response['response']}` and all {len(removed_response['patterns'])} patterns.")
            else:
                await ctx.reply("Response removed from memory but could not update the file. Check logs for details.")
            return
    
    await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")

@bot.command(name='add_pattern_to_response', help='Add a pattern to an existing response.\nArguments: response_id_or_name - ID number or name of the response\n           pattern (str) - Regex pattern to match\n           [flags] (str) - Optional regex flags (e.g., "DOTALL|IGNORECASE")\n           [name] (str) - Optional friendly name for the pattern\n           [url] (str) - Optional screenshot URL\nExample: !add_pattern_to_response 5 ".*error.*message" "DOTALL" "error_pattern"\nExample: !add_pattern_to_response v6fix_command ".*error.*" "DOTALL"')
@has_command_permission()
@command_category("OCR Configuration")
async def add_pattern_to_response(ctx, response_id_or_name: str, pattern: str, flags: str = "", name: str = "", url: str = ""):
    """Add a pattern to an existing response"""
    server_id = str(ctx.guild.id)
    
    if server_id not in server_patterns:
        await ctx.reply("This server has no custom responses.")
        return
    
    # Find the response
    response = find_response(server_id, response_id_or_name)
            
    if not response:
        await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")
        return
    
    try:
        # Parse and combine regex flags
        flag_value = 0
        if flags:
            for flag in flags.split('|'):
                if flag in REGEX_FLAGS:
                    flag_value |= REGEX_FLAGS[flag]
                else:
                    await ctx.reply(f"Invalid flag: {flag}. Valid flags are: {', '.join(REGEX_FLAGS.keys())}")
                    return
        
        # Compile the pattern
        compiled_pattern = re.compile(pattern, flag_value)
        
        # Get the next pattern ID
        pattern_id = get_next_pattern_id(response)
        
        # Use a default name if none provided
        if not name:
            name = f"pattern_{pattern_id}"
        
        # Add the new pattern
        response["patterns"].append({
            "id": pattern_id,
            "name": name,
            "pattern": compiled_pattern,
            "url": url
        })
        
        # Save patterns to file
        if save_patterns():
            response_identifier = f"response ID {response['response_id']}"
            if response.get("name"):
                response_identifier += f" [{response['name']}]"
            await ctx.reply(f"Successfully added pattern {pattern_id} to {response_identifier}.")
        else:
            await ctx.reply("Pattern added to memory but could not be saved to file. Check logs for details.")
    
    except re.error as e:
        await ctx.reply(f"Error compiling regex pattern: {e}")
    except Exception as e:
        logger.error(f"Error adding pattern: {e}")
        await ctx.reply(f"Error adding pattern: {e}")

@bot.command(name='remove_pattern_from_response', help='Remove a pattern from a response.\nArguments: response_id_or_name - ID number or name of the response\n           pattern_id (int) - ID number of the pattern to remove\nExample: !remove_pattern_from_response 5 2\nExample: !remove_pattern_from_response v6fix_command 2')
@has_command_permission()
@command_category("OCR Configuration")
async def remove_pattern_from_response(ctx, response_id_or_name: str, pattern_id: int):
    """Remove a pattern from a response"""
    server_id = str(ctx.guild.id)
    
    if server_id not in server_patterns:
        await ctx.reply("This server has no custom responses.")
        return
    
    # Find the response
    response = find_response(server_id, response_id_or_name)
            
    if not response:
        await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")
        return
    
    # Find and remove the pattern
    pattern_found = False
    for i, pattern in enumerate(response["patterns"]):
        if pattern["id"] == pattern_id:
            del response["patterns"][i]
            pattern_found = True
            break
    
    if not pattern_found:
        await ctx.reply(f"No pattern found with ID {pattern_id} in response {response_id_or_name}.")
        return
        
    # Remove the response if no patterns left
    if not response["patterns"]:
        for i, r in enumerate(server_patterns[server_id]):
            if r["response_id"] == response["response_id"]:
                del server_patterns[server_id][i]
                response_identifier = f"response {response['response_id']}"
                if response.get("name"):
                    response_identifier += f" [{response['name']}]"
                await ctx.reply(f"Removed pattern {pattern_id} and also removed {response_identifier} as it no longer has any patterns.")
                break
    else:
        response_identifier = f"response {response['response_id']}"
        if response.get("name"):
            response_identifier += f" [{response.get('name')}]"
        await ctx.reply(f"Successfully removed pattern {pattern_id} from {response_identifier}.")
    
    # Save patterns to file
    if not save_patterns():
        await ctx.reply("Warning: Changes made in memory but could not be saved to file. Check logs for details.")

@bot.command(name='view_response', help='View details of a specific response.\nArguments: response_id_or_name - ID number or name of the response\nExample: !view_response 5\nExample: !view_response v6fix_command')
@has_command_permission()
@command_category("OCR Configuration")
async def view_response(ctx, response_id_or_name: str):
    """View details of a specific response"""
    server_id = str(ctx.guild.id)
    
    # Try server-specific patterns first
    response = None
    source = None
    
    # Check server-specific patterns
    if server_id in server_patterns:
        response = find_response(server_id, response_id_or_name)
        if response:
            source = "server"
                
    # If not found, check default patterns
    if not response and "default" in server_patterns:
        # Try to interpret as an integer (ID)
        try:
            response_id = int(response_id_or_name)
            # Search by ID
            for r in server_patterns["default"]:
                if r["response_id"] == response_id:
                    response = r
                    source = "default"
                    break
        except ValueError:
            # Search by name
            for r in server_patterns["default"]:
                if r.get("name", "").lower() == response_id_or_name.lower():
                    response = r
                    source = "default"
                    break
    
    if not response:
        await ctx.reply(f"No response found with ID or name '{response_id_or_name}'.")
        return
    
    # Build detailed response info
    response_text = f"**Response ID {response['response_id']}** ({source})"
    if response.get("name"):
        response_text += f" [{response['name']}]"
    response_text += f"\nText: `{response['response']}`\n"
    
    if response.get("note"):
        response_text += f"Note: {response['note']}\n"
    
    response_text += f"\n**Patterns ({len(response['patterns'])}):**\n"
    
    for pattern in response["patterns"]:
        response_text += f"- ID {pattern['id']}: "
        if pattern.get("name"):
            response_text += f"`{pattern['name']}` "
        
        # Get pattern string and flags
        pattern_str = pattern['pattern'].pattern
        flags = []
        if pattern['pattern'].flags & re.IGNORECASE:
            flags.append("IGNORECASE")
        if pattern['pattern'].flags & re.DOTALL:
            flags.append("DOTALL")
        if pattern['pattern'].flags & re.MULTILINE:
            flags.append("MULTILINE")
        
        # Truncate pattern if needed
        if len(pattern_str) > 50:
            pattern_str = pattern_str[:47] + "..."
        
        response_text += f"`{pattern_str}`"
        
        if flags:
            response_text += f" Flags: {', '.join(flags)}"
            
        if pattern.get("url"):
            response_text += f" [Screenshot]({pattern['url']})"
            
        response_text += "\n"
    
    # Split into chunks if needed
    if len(response_text) > 2000:
        chunks = [response_text[i:i+1990] for i in range(0, len(response_text), 1990)]
        for i, chunk in enumerate(chunks):
            await ctx.reply(f"{chunk}\n*Part {i+1}/{len(chunks)}*")
    else:
        await ctx.reply(response_text)

# Assuming your bot instance is named 'bot' and is an instance of commands.Bot or commands.AutoShardedBot
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Log the error and send a user-friendly message
        logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        # Handle other types of errors here
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.error(f"Error in command '{ctx.command}': {error}")
        await ctx.send(f"Error in command '{ctx.command}': {error}")

# Add this right before bot.run(config['token'])
# Apply categories to ensure they're set properly
for cmd in bot.commands:
    # Debug the current state
    if hasattr(cmd, 'category'):
        logger.debug(f"Command '{cmd.name}' has category: {cmd.category}")
    else:
        # Try to find category in callback
        if hasattr(cmd, 'callback') and hasattr(cmd.callback, 'category'):
            cmd.category = cmd.callback.category
            logger.debug(f"Applied category '{cmd.category}' from callback to command '{cmd.name}'")
        else:
            cmd.category = "Miscellaneous"
            logger.debug(f"Assigned default category 'Miscellaneous' to command '{cmd.name}'")

bot.run(config['token'])