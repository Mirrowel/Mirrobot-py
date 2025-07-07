"""
OCR processing module for Mirrobot.

This module contains the core OCR (Optical Character Recognition) functionality
for processing images in Discord messages, extracting text, and matching patterns
to provide automated responses.
"""

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
from utils.stats_tracker import OCRTimingContext, get_ocr_stats
from utils.discord_utils import reply_or_send

logger = get_logger()

async def process_pics(bot, message):
    """
    Process all images in a Discord message for OCR analysis.
    
    This function is the main entry point for processing images attached to messages.
    It extracts text from each image and analyzes it using pattern matching.
    
    Args:
        bot (discord.Bot): The Discord bot instance
        message (discord.Message): The Discord message containing attachments
        
    Returns:
        bool: True if any images were processed, False otherwise
    """
    with OCRTimingContext() as timing:
        successful = False
        
        # Get OCR language for this channel
        lang = get_ocr_language(bot, message.guild.id, message.channel.id)
        logger.debug(f"Using OCR language: {lang} for channel {message.channel.id}")
        
        # Process the message that has already been validated in process_message
        if message.attachments:
            # Process the first valid attachment
            attachment = message.attachments[0]
            await pytess(bot, message, attachment, lang)
            successful = True
        else:
            # Extract URL from the message which was already validated
            import re
            urls = re.findall(r'(https?://\S+)', message.content)
            if urls:
                # The URL was already validated in process_message
                url = urls[0]
                content_type = None
                content_length = 0
                
                try:
                    response = requests.head(url)
                    content_type = response.headers.get('content-type')
                    content_length = int(response.headers.get('content-length', 0))
                except:
                    pass
                    
                # Create a fake attachment object with the URL
                attachment = type('FakeAttachment', (object,), {'url': url, 'size': content_length, 'content_type': content_type})
                await pytess(bot, message, attachment, lang)
                successful = True
                
        if successful:
            timing.mark_successful()

    # Log processing time after completion
    status_msg = "successfully" if timing.successful else "with no results"
    
    stats = get_ocr_stats()
    logger.info(f"OCR processing completed {status_msg} in {timing.elapsed:.2f} seconds (avg: {stats['avg_time']:.2f}s over {stats['total_processed']} successful operations)")

def get_ocr_language(bot, guild_id, channel_id):
    """
    Get the OCR language setting for a specific channel.
    
    Args:
        bot (discord.Bot): The Discord bot instance
        guild_id (int): The Discord server (guild) ID
        channel_id (int): The Discord channel ID
        
    Returns:
        str: Language code (e.g., 'eng', 'rus') to use for OCR,
             defaults to 'eng' if not specified
    """
    config = bot.config
    
    # Default to English if no configuration is found
    if 'ocr_channel_config' not in config:
        return "eng"
        
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)
    
    # Get guild configuration
    guild_config = config.get('ocr_channel_config', {}).get(guild_id_str, {})
    
    # Get channel configuration
    channel_config = guild_config.get(channel_id_str, {})
    
    # Return language or default to English
    return channel_config.get('lang', 'eng')

async def pytess(bot, message, attachment, lang="eng"):
    """
    Extract text from an image using Tesseract OCR.
    
    Args:
        bot (discord.Bot): The Discord bot instance
        message (discord.Message): The Discord message containing the attachment
        attachment (discord.Attachment): The image attachment to process
        lang (str, optional): Language code for OCR. Defaults to "eng".
        
    Returns:
        str: Extracted text from the image, or empty string if processing failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    data = io.BytesIO(await resp.read())
                    image = Image.open(data)
                    
                    # Use the specified language for OCR
                    text = pytesseract.image_to_string(image, lang)
                    
                    language_name = "English" if lang == "eng" else "Russian"
                    logger.info(f"Transcription completed using {language_name}")
                    
                    if text.strip():
                        await analyze_and_respond(bot, message, text)
                    else:
                        logger.debug("No text found in image")
    except Exception as e:
        logger.error(f"Error processing image with OCR: {e}")

async def analyze_and_respond(bot, message, text):
    """
    Analyze extracted text from an image and respond if patterns match.
    
    Args:
        bot (discord.Bot): The Discord bot instance
        message (discord.Message): The Discord message containing the image
        text (str): Extracted text from the image
        
    Returns:
        bool: True if a response was sent, False otherwise
    """
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

def check_image_dimensions(image_path):
    """
    Check if an image's dimensions are within acceptable limits.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        bool: True if dimensions are acceptable, False otherwise
    """
    with Image.open(image_path) as img:
        width, height = img.size
        return width, height

async def respond_to_ocr(bot, message, response):
    """
    Send a response to a message based on OCR results.
    
    Args:
        bot (discord.Bot): The Discord bot instance
        message (discord.Message): The original message to respond to
        response (dict): Response data containing the text to send
        
    Returns:
        bool: True if response was sent successfully, False otherwise
    """
    if not response:
        logger.error('No response message found')
        return
        
    config = bot.config
    response_channel = None
    guild_id = str(message.guild.id)
    
    # Get the language of the source channel
    source_lang = get_ocr_language(bot, message.guild.id, message.channel.id)
    
    # Check if we should reply in the same channel
    if guild_id in config['ocr_response_channels'] and message.channel.id in config['ocr_response_channels'][guild_id]:
        await reply_or_send(message, content=response)
    else:
        # Initialize response channels if needed
        if guild_id not in config['ocr_response_channels']:
            logger.info(f'No response channel found for server {message.guild.name}:{message.guild.id}. CREATING NEW CHANNEL LIST')
            config['ocr_response_channels'][guild_id] = []
            from config.config_manager import save_config
            save_config(config)
        
        # Find a response channel with matching language
        response_channel_id = None
        same_lang_response_channel_id = None
        
        # Look for response channels that aren't also read channels
        for channel_id in config['ocr_response_channels'][guild_id]:
            if channel_id not in config['ocr_read_channels'].get(guild_id, []):
                channel_lang = get_ocr_language(bot, message.guild.id, channel_id)
                
                # First priority: matching language
                if channel_lang == source_lang:
                    same_lang_response_channel_id = channel_id
                    break  # Found a perfect match
        
        # Use the channel we found
        if same_lang_response_channel_id is not None:
            response_channel_id = same_lang_response_channel_id
            logger.debug(f"Using language-matched response channel: {response_channel_id}")
            
        # Get the actual channel object
        if response_channel_id is not None:
            response_channel = bot.get_channel(response_channel_id)
        
        # Send to response channel or fallback
        original_message_link = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}'
        if response_channel:
            sent_message = await response_channel.send(original_message_link)
            logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if hasattr(sent_message.channel, 'type') and sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
            logger.debug(f"Response: {sent_message.content}")
            await reply_or_send(sent_message, content=response)
        else:
            logger.error('No response channel found. Using fallback channel.')
            fallback_channels = config['ocr_response_fallback'].get(guild_id)
            if fallback_channels:
                sent_message = await bot.get_channel(fallback_channels[0]).send(original_message_link)
                logger.debug(f"Server: {message.guild.name}:{sent_message.guild.id}, Channel: {sent_message.channel.name}:{sent_message.channel.id}," + (f" Parent:{sent_message.channel.parent}" if hasattr(sent_message.channel, 'type') and sent_message.channel.type in ['public_thread', 'private_thread'] else ""))
                logger.debug(f"Response: {sent_message.content}")
                await reply_or_send(sent_message, content=response)
            else:
                logger.error('No OCR response fallback channel configured for this server.')
                return
 
def check_image_dimensions(image_path):
    """
    Check if an image's dimensions are within acceptable limits.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        bool: True if dimensions are acceptable, False otherwise
    """
    with Image.open(image_path) as img:
        width, height = img.size
        return width, height
