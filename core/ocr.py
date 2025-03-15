import discord
import pytesseract
from PIL import Image
import time
import io
import aiohttp
import requests
from datetime import datetime
from utils.logging_setup import get_logger
from core.pattern_manager import match_patterns
from utils.stats_tracker import OCRTimingContext

logger = get_logger()

async def process_pics(bot, message):
    """Process images in a message for OCR"""
    if message.attachments:
        attachment = message.attachments[0]
        logger.debug(f"Received a help request:\nServer: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + (f" Parent:{message.channel.parent}" if message.channel.type == 'public_thread' or message.channel.type == 'private_thread' else ""))
        logger.info(f'Received an attachment of size: {attachment.size}')
        if attachment.size < 500000 and attachment.content_type.startswith('image/'):
            if (attachment.width > 300 and attachment.height > 200):
                logger.info(f'URL: {attachment.url}')
                start_time = time.time()
                await pytess(bot, message, attachment, start_time)
            else:
                await respond_to_ocr(bot, message, 'Images must be at least 300x200 pixels.')
        else:
            await respond_to_ocr(bot, message, 'Please attach an image(no GIFs) with a size less than 500KB.')
    else:
        # Extract first URL from the message if no attachments are found
        import re
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
                if width > 300 and height > 200:
                    logger.info("Content type is image")
                    attachment = type('FakeAttachment', (object,), {'url': urls[0], 'size': 999999, 'content_type': content_type})  # Fake attachment object
                    await pytess(bot, message, attachment, start_time)

async def pytess(bot, message, attachment, start_time):
    """Process image with pytesseract OCR"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    data = io.BytesIO(await resp.read())
                    image = Image.open(data)
                    with OCRTimingContext():
                        text = pytesseract.image_to_string(image, 'eng')
                        logger.info(f"Transcription took {time.time() - start_time} seconds.")
                    if text.strip():
                        await analyze_and_respond(bot, message, text, start_time)
                    else:
                        logger.debug("No text found in image")
    except Exception as e:
        logger.error(f"Error processing image with OCR: {e}")

async def analyze_and_respond(bot, message, text, start_time):
    """Analyze OCR text and respond with appropriate patterns"""
    logger.info(f'Analyzing text')
    
    # Try to match patterns
    matched_response = match_patterns(message.guild.id, text)
    
    if matched_response:
        logger.info(f"Pattern found: Response ID: {matched_response['response_id']}")
        
        # Log the match
        with open('logs/matches.log', 'a', encoding='utf-8') as log:
            log.write(f'{datetime.now().strftime("%d-%m-%Y %H:%M:%S")} - {message.author.name} - {matched_response.get("response_id", "unknown")}\n')
            log.write(f'Response: {matched_response["response"]}\n')
            log.write(f'{text}\n\n')
        
        # Send the response
        await respond_to_ocr(bot, message, matched_response["response"])
    else:
        logger.info(f'No pattern found')
        await respond_to_ocr(bot, message, text)
    
    logger.info(f"Total time taken: {time.time() - start_time} seconds.")

def check_image_dimensions(image_path):
    """Check dimensions of an image"""
    with Image.open(image_path) as img:
        width, height = img.size
        return width, height

async def respond_to_ocr(bot, message, response):
    """Route the OCR response to the appropriate channel"""
    if not response:
        logger.error('No response message found')
        return
        
    config = bot.config
    response_channel = None
    guild_id = str(message.guild.id)
    
    # Check if we should reply in the same channel
    if guild_id in config['ocr_response_channels'] and message.channel.id in config['ocr_response_channels'][guild_id]:
        await msg_reply(message, text=response)
    else:
        # Initialize response channels if needed
        if guild_id not in config['ocr_response_channels']:
            logger.info(f'No response channel found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
            config['ocr_response_channels'][guild_id] = []
            from config.config_manager import save_config
            save_config(config)
        
        # Look for a response channel that's not also a read channel
        for channel_id in config['ocr_response_channels'][guild_id]:
            if channel_id not in config['ocr_read_channels'].get(guild_id, []):
                response_channel = bot.get_channel(channel_id)
                break
        
        # Send to response channel or fallback
        original_message_link = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}'
        if response_channel:
            sent_message = await response_channel.send(original_message_link)
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if hasattr(sent_message.channel, 'type') and sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
            logger.debug(f"Response: {sent_message.content}")
            await msg_reply(sent_message, text=response)
        else:
            logger.error('No response channel found. Using fallback channel.')
            fallback_channels = config['ocr_response_fallback'].get(guild_id)
            if fallback_channels:
                sent_message = await bot.get_channel(fallback_channels[0]).send(original_message_link)
                logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if hasattr(sent_message.channel, 'type') and sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
                logger.debug(f"Response: {sent_message.content}")
                await msg_reply(sent_message, text=response)
            else:
                logger.error('No OCR response fallback channel configured for this server.')
                return

async def msg_reply(message, text):
    """Reply to a message with text, handling text that's too long"""
    if len(text) == 0:
        logger.error('No text found to reply')
        return
        
    # Log the full message once before splitting
    #logger.debug(f"Server: {message.guild.name}:{message.guild.id}, Channel: {message.channel.name}:{message.channel.id}," + 
    #            (f" Parent:{message.channel.parent}" if message.channel.type == 'public_thread' or message.channel.type == 'private_thread' else ""))
    #logger.info(f"Response: {text}")

    if len(text) > 2000:
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            await message.reply(chunk)
    else:
        await message.reply(text)
