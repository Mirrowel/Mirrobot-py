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
#if platform.system() == 'Windows':
#	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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

bot = commands.Bot(command_prefix=config['command_prefix'], intents=intents)

patterns = [
    {"name": "1087", "pattern": re.compile(".*invalid_parameter_handler.*1087.*|.*1087.*invalid_parameter_handler.*",re.DOTALL), "response": "!1087"},
    {"name": "152", "pattern": re.compile(".*on.game.start.*callback.add.*",re.DOTALL), "response": "!152"},
    {"name": "k98", "pattern": re.compile(".ead(.|..)amage(.|..)20"), "response": "!k98"},
    {"name": "omod", "pattern": re.compile(".*OMODFramework.*",re.DOTALL), "response": "!omod"},
    {"name": "EOF", "pattern": re.compile(".*while reading sideband packet.*",re.DOTALL), "response": "!v6fix"},
    {"name": "unblock", "pattern": re.compile(".*dll’ file is blocked.*",re.DOTALL), "response": "!unblock"},
    {"name": "fullSave", "pattern": re.compile(r".*Unspecified error.*appdata\\savedgames.*",re.DOTALL), "response": "!full"},
    {"name": "strexplode", "pattern": re.compile(".*str_explode.*",re.DOTALL), "response": "!strexplode"},
    {"name": "dest", "pattern": re.compile(".*Dest string less.*",re.DOTALL), "response": "!dest"},
    {"name": "resolution", "pattern": re.compile("u[i|l]_options\.script:\s?1649",re.DOTALL), "response": "!resolution"},
    {"name": "ini1", "pattern": re.compile(r"(Cannot open instance Portable|ModOrganizer\.ini|game managed by)"), "response": "!ini"},
    {"name": "atmos", "pattern": re.compile("ssfx_rain_mcm\.script:\s?10",re.DOTALL), "response": "!atmos"},
    {"name": "monster", "pattern": re.compile(".*base_monster.*1050.*",re.DOTALL), "response": "Update your modded exes"},
    {"name": "toolong", "pattern": re.compile(".ilename.too..ong"), "response": "!ini"},
    {"name": "opyat", "pattern": re.compile(".*take.item..nim.*compare", re.DOTALL), "response": "!опять or !disabled"},
    {"name": "adminAND", "pattern": re.compile("(.*Set-ItemProperty.*PermissionDenied.*)",re.DOTALL), "response": "!admin"},
    {"name": "adminOR", "pattern": re.compile(r"(Set-ItemProperty|PermissionDenied)",re.DOTALL), "response": "!admin"},
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
    {"name": "65k", "pattern": re.compile(".*100(.*not.*|.*ID.*)",re.DOTALL), "response": "!65k"},
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
        if attachment.size < 1000000 and attachment.content_type.startswith('image/'):
            if (attachment.width > 200 and attachment.height > 100):
                logger.info(f'URL: {attachment.url}')
                start_time = time.time()

                #await sniperTess(message, attachment, start_time)
                #start_time = time.time()
                await pytess(message, attachment, start_time)
            else:
                response = 'Images must be at least 200x100 pixels.'
                await respond_to_ocr(message, response)
        #else:
            #response = 'Please attach an image(no GIFs) with a size less than 1MB.'
            #await respond_to_ocr(message, response)
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
                else:
                    response = 'Please attach an image with dimensions larger than 200x100.'
                    await respond_to_ocr(message, response)
            else:
                response = 'Please attach an image with text to extract the text from the image.'
                await respond_to_ocr(message, response)

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
        if response_channel:
            original_message_link = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}'
            sent_message = await response_channel.send(f'{original_message_link}')
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type == 'public_thread' or sent_message.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {sent_message.content}")
            await msg_reply(sent_message,text=response)
        elif not response_channel:
            original_message_link = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}'
            sent_message = await bot.get_channel(ocr_response_fallback[str(message.guild.id)][0]).send(f'{original_message_link}')
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type == 'public_thread' or sent_message.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {sent_message.content}")
            await msg_reply(sent_message,text=response)
        else:
            logger.error('No response channel found')
            return 

async def msg_reply(message,text):
    if len(text) > 2000:
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            sent_message = await message.reply(chunk)
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type == 'public_thread' or sent_message.channel.type == 'private_thread' else ""))
            logger.info(f"Response: {sent_message.content}")
    elif len(text) > 0 and len(text) <= 2000:
        sent_message = await message.reply(text)
        logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if sent_message.channel.type == 'public_thread' or sent_message.channel.type == 'private_thread' else ""))
        logger.info(f"Response: {sent_message.content}")
    else:
        logger.error('No text found to reply')
        return
        


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
@bot.command(name='add_ocr_read_channel', help='Add a channel to the OCR read channels list for this server.')
@commands.is_owner()
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

@bot.command(name='remove_ocr_read_channel', help='Remove a channel from the OCR read channels list for this server.')
@commands.is_owner()
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

@bot.command(name='add_ocr_response_channel', help='Add a channel to the OCR response channels list for this server.')
@commands.is_owner()
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

@bot.command(name='remove_ocr_response_channel', help='Remove a channel from the OCR response channels list for this server.')
@commands.is_owner()
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

@bot.command(name='add_ocr_response_fallback', help='Add a channel to the OCR response fallback list for this server.')
@commands.is_owner()
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

@bot.command(name='remove_ocr_response_fallback', help='Remove a channel from the OCR response fallback list for this server.')
@commands.is_owner()
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
@bot.command(name='shutdown')
@commands.is_owner()  # This check ensures only the bot owner can use this command
async def shutdown(ctx):
    # Before shutting down, perform necessary cleanup
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    await asyncio.gather(*tasks, return_exceptions=False)
    
    response ="Shutting down."
    logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    logger.info(f"Response: {response}")
    await ctx.reply(response)
    await bot.close()  # Gracefully close the bot
    # Delay the closure of the event loop to allow tasks to clean up
    await asyncio.sleep(1)  # Adjust the delay as needed

    # Stop the event loop
    loop = asyncio.get_running_loop()
    if not loop.is_closed():
        loop.stop()

# Error handling for the shutdown command
@shutdown.error
async def shutdown_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        response ="You do not have permission to shut down the bot."
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.error(f"Response: {response}")
        #await ctx.reply(response)


# Assuming your bot instance is named 'bot' and is an instance of commands.Bot or commands.AutoShardedBot
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Log the error and send a user-friendly message
        logger.debug(f"Unknown command: {ctx.message.content}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        #logger.debug(f"Unknown command: {ctx.message.content}")
        #await ctx.send("Sorry, I didn't recognize that command. Try `!help` for a list of available commands.")
    else:
        # Handle other types of errors here
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.error(f"Error in command '{ctx.command}': {error}")
        #await ctx.send("Oops! Something went wrong while processing your command.")

bot.run(config['token'])