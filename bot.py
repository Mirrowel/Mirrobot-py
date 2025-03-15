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
SYSTEM_COMMANDS = ['shutdown']  # Commands that only the owner can use

# Function to get the prefix for a server
def get_prefix(bot, message):
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

patterns = [
    {"name": "1087", "pattern": re.compile(".*invalid.parameter.handler.*1087|.*1087.*invalid.parameter",re.DOTALL), "response": "!1087"},
    {"name": "152", "pattern": re.compile(".*on.game.start.*callback.add.*",re.DOTALL), "response": "!152"},
    {"name": "k98", "pattern": re.compile(".ead(.|..)amage(.|..)20"), "response": "!k98"},
    {"name": "omod", "pattern": re.compile(".*OMODFramework|(.*fail.*load.*omod.dll)",re.DOTALL | re.IGNORECASE), "response": "!omod"},
    {"name": "EOF", "pattern": re.compile(".*while reading sideband packet.*",re.DOTALL), "response": "!v6fix"},
    {"name": "unblock", "pattern": re.compile(".*dll’ file is blocked.*",re.DOTALL), "response": "!unblock"},
    {"name": "fullSave", "pattern": re.compile(r".*Unspecified error.*appdata\\savedgames.*",re.DOTALL), "response": "!full"},
    {"name": "strexplode", "pattern": re.compile(".*str.explode",re.DOTALL), "response": "!strexplode"},
    {"name": "dest", "pattern": re.compile(".*Dest string less.*",re.DOTALL), "response": "!dest"},
    {"name": "resolution", "pattern": re.compile("u[i|l]_options\.script:\s?1649",re.DOTALL), "response": "!resolution"},
    {"name": "ini1", "pattern": re.compile(r"(Cannot open instance Portable|ModOrganizer\.ini|game managed by)"), "response": "!ini"},
    {"name": "atmos", "pattern": re.compile("ssfx_rain_mcm\.script:\s?10",re.DOTALL), "response": "!atmos"},
    {"name": "monster", "pattern": re.compile(".*base_monster.*1050.*",re.DOTALL), "response": "Update your modded exes"},
    {"name": "toolong", "pattern": re.compile(".ilename.too..ong"), "response": "!ini"},
    {"name": "opyat", "pattern": re.compile(".*take.item..nim.*compare", re.DOTALL), "response": "!опять or !disabled"},
    {"name": "adminAND", "pattern": re.compile("(.*Set-ItemProperty.*PermissionDenied.*)",re.DOTALL), "response": "!admin"},
    #{"name": "adminOR", "pattern": re.compile(r"(Set-ItemProperty|PermissionDenied)",re.DOTALL), "response": "!admin"},
    {"name": "ownershipGIT", "pattern": re.compile("(.*detect(.*dubious|.*ownership))",re.DOTALL), "response": "!ownership"},
    {"name": "win1873", "pattern": re.compile("(.*find model file.*wpn_win.873_world.*)"), "response": "!manual https://www.moddb.com/addons/start/259315"},
    {"name": "GetDeviceRemovedReason", "pattern": re.compile("(GetDeviceRemove.Rea.on)",re.IGNORECASE), "response": "!dx9 or !dx8. But first reboot your PC"},
    {"name": "bizonfix", "pattern": re.compile("(.*find model file.*wpn_bizon_lazer_hud.*)",re.DOTALL), "response": "!v6fix if the launcher version is up to date. !bas is the easiest solution"},
    {"name": "v6fixACC", "pattern": re.compile(r"(fatal: unable to access|SSL/TLS connection failed)",re.DOTALL), "response": "!v6fix"},
    {"name": "v6fixGIT", "pattern": re.compile("(.*fatal(.*not|.*git).*repo)",re.DOTALL | re.IGNORECASE), "response": "!v6fix"},
    {"name": "hostsJAM", "pattern": re.compile(".*jam.animations.*get.jammed",re.DOTALL), "response": "!hosts"},
    {"name": "verify", "pattern": re.compile(".*AnomalyDX.*AnomalyDX(.|..)AVX.*", re.DOTALL | re.IGNORECASE), "response": "!verify"},
    #{"name": "ace", "pattern": re.compile(".*up.*g.*ace.*", re.DOTALL), "response": "!update or !full"},
    {"name": "dedsave", "pattern": re.compile("ui.st.invalid.saved.game"), "response": "Save game is invalid. Your saves are probably dead: if they dont load as well - start new game."},
    {"name": "ini2", "pattern": re.compile(".*Cannot start.*AnomalyLauncher.*",re.DOTALL), "response": "!ini"},
    {"name": "BarArena", "pattern": re.compile(".*.hrase.*arena.manager.*",re.DOTALL), "response": "Dont fight mutants in the bar arena and then stalkers in the bar. It's bugged. Reload to an older save."},
    {"name": "OpenALCreate", "pattern": re.compile(".*OpenAL.*create.*",re.DOTALL | re.IGNORECASE), "response": "!openal"},
    {"name": "dick", "pattern": re.compile(".*model.*day.*trader.*",re.DOTALL), "response": "!dick, unless you got HD models"},
    #{"name": "65k", "pattern": re.compile(".*100(.*not.*|.*ID.*)",re.DOTALL), "response": "!65k"},
    {"name": "aborting", "pattern": re.compile(".*aborting.*",re.IGNORECASE), "response": "!aborting"},
    {"name": "surge", "pattern": re.compile(".*262.*surge.*rush.*", re.DOTALL), "response": "!surgecrash / !surgefix if first didnt help"},
    {"name": "pkpsiber", "pattern": re.compile(".*266.*pkp.*", re.DOTALL), "response": "!realv6"},
    {"name": "ishCamp", "pattern": re.compile(".*ish.*fire.*", re.DOTALL), "response": "!yacs - incorrectly disabled yacs"},
    {"name": "sksv6", "pattern": re.compile(".*sks.*pu*(.|..)ud.*", re.DOTALL), "response": "!v6fix"},
    {"name": "virtualCall", "pattern": re.compile(".*035.*irtua.*", re.DOTALL), "response": "!surgefix but first - !backup in #bot-commands"},
    {"name": "amb", "pattern": re.compile(".*find.*amb17.*", re.DOTALL), "response": "!realv6"},
    {"name": "solving", "pattern": re.compile(".*instr.*olvin.*", re.DOTALL), "response": "!solving"},
    {"name": "pdaboard", "pattern": re.compile(".*270.*pda.*", re.DOTALL), "response": "!hosts/!full if launcher is updated"},
    {"name": "newsBounty", "pattern": re.compile(".*news.*lura.*", re.DOTALL), "response": "!bounty"},
    {"name": "smrloot", "pattern": re.compile(".*smr..oot.*se(.|..)tem", re.DOTALL), "response": "!smrloot"},
    {"name": "taskFunctor", "pattern": re.compile(".*task(.|..)unct", re.DOTALL), "response": "!semenov"},
    {"name": "ui_mcm", "pattern": re.compile(".*LUA.*ui.m.m", re.DOTALL |re.IGNORECASE), "response": "!update"},
    {"name": "arith", "pattern": re.compile(".*ui(.|..)options.*rith", re.DOTALL), "response": "!arith"},
    {"name": "hiddenThreat", "pattern": re.compile(".*idde.*hrea", re.DOTALL), "response": "!full if your launcher version is up to date"},
    {"name": "vicShitFix", "pattern": re.compile(".*zaz|.*veh", re.DOTALL), "response": "!veh"},
    {"name": "shortcut", "pattern": re.compile(".*Unable to save shortcut", re.DOTALL | re.IGNORECASE), "response": "!shortcut"},
    {"name": "stealth", "pattern": re.compile(".*isual.*tealt", re.DOTALL), "response": "!stealth"},
    {"name": "nightMutants", "pattern": re.compile(".*night.*mutant", re.DOTALL), "response": "!mutants"},
    {"name": "livingLegend", "pattern": re.compile(".*living.*legend", re.DOTALL), "response": "!livinglegend"},
    {"name": "mortalSin", "pattern": re.compile(".*mortal.*sin", re.DOTALL), "response": "!mortalsin"},
    {"name": "assert", "pattern": re.compile(".*10.*assert", re.DOTALL), "response": "!dx9 / complete the task and revert back to dx11"},
    {"name": "adar", "pattern": re.compile(".*adar2", re.DOTALL), "response": "!v6"},
    
    ]

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

async def analyze_and_respond(message, text,start_time):
    logger.info(f'Analyzing text')
    pattern_found = False
    #logger.debug(f'Text: {text}')
    for pattern in patterns:
        #logger.debug(f'Checking pattern: {str(pattern["pattern"].pattern)}')
        if pattern["pattern"].search(text):
            pattern_found = True
            logger.info(f'Pattern found: {pattern["name"]}')
            response = pattern["response"]
            with open('succ.log', 'a', encoding='utf-8') as log:
                log.write(f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {message.author.name} - {pattern["name"]}\n')
                log.write(f'{text}\n')
                log.close()
            await respond_to_ocr(message, response)
            break
    if not pattern_found:
        logger.info(f'No pattern found')
        #await respond_to_ocr(message, 'No known issues found.')
        await respond_to_ocr(message, text)
    logger.info(f"Total time taken: {time.time() - start_time} seconds.")

def check_image_dimensions(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
        return width, height

# Add this utility function before the commands
async def create_embed_response(ctx, title, description, fields, footer_text=None, thumbnail_url=None):
    """
    Create a standardized embed response with proper formatting.
    
    Args:
        ctx: The command context
        title: The title of the embed
        description: The description text
        fields: List of dictionaries with 'name', 'value', and 'inline' keys
        footer_text: Optional text for the footer
        thumbnail_url: Optional URL for the thumbnail
    """
    embed_color = discord.Color.blue()
    
    # Create the embed with title and description
    embed = discord.Embed(title=title, description=description, color=embed_color)
    
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
        embed.set_footer(text=footer_text)
        
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
    old_prefix = server_prefixes.get(guild_id, get_prefix(bot, ctx.message))
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

@bot.command(name='help', help='Show help for bot commands.\nArguments: [command] (optional) - Get detailed help on a specific command\nExample: !help or !help server_info')
@commands.cooldown(1, 3, commands.BucketType.user)  # Prevent spam
@command_category("System")
async def help_command(ctx, command_name=None):
    """Display help information about the bot and its commands"""
    prefix = get_prefix(bot, ctx.message)
    
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
    description = f"Use `{prefix}help <command>` for detailed information on a command.\n\n" \
                  f"**Current prefix:** `{prefix}`\n\n" \
                  f"**Note:** You only see commands you have permission to use."
    
    # Define fields
    fields = []
    
    # Add bot info section
    fields.append({
        "name": "📝 About", 
        "value": "Mirrobot is an OCR (Optical Character Recognition) bot that scans images for text " \
                 "patterns and provides automatic responses to common issues.",
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
    footer_text = f"Mirrobot v0.1 | Type {prefix}help <command> for more info"
    
    # Send the response
    await create_embed_response(
        ctx=ctx,
        title="Mirrobot Help",
        description=description,
        fields=fields,
        footer_text=footer_text
    )

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