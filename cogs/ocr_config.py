import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from config.config_manager import save_config

logger = get_logger()

class OCRConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='add_ocr_read_channel', help='Add a channel where bot will scan images for OCR processing.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_read_channel 123456789012345678 or !add_ocr_read_channel #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_read_channel(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_read_channels = config['ocr_read_channels']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id not in ocr_read_channels:
            ocr_read_channels[guild_id] = []

        if channel_id in ocr_read_channels[guild_id]:
            response = f'Channel {channel.mention} is already in the OCR read channels list for this server.'
        else:
            ocr_read_channels[guild_id].append(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} added to OCR reading channels for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_ocr_read_channel', help='Remove a channel from the OCR reading list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_read_channel 123456789012345678 or !remove_ocr_read_channel #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_read_channel(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_read_channels = config['ocr_read_channels']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id in ocr_read_channels and channel_id in ocr_read_channels[guild_id]:
            ocr_read_channels[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR reading channels for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR reading channels list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='add_ocr_response_channel', help='Add a channel where bot will post OCR analysis results.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_response_channel 123456789012345678 or !add_ocr_response_channel #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_response_channel(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_response_channels = config['ocr_response_channels']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id not in ocr_response_channels:
            ocr_response_channels[guild_id] = []

        if channel_id in ocr_response_channels[guild_id]:
            response = f'Channel {channel.mention} is already in the OCR response channels list for this server.'
        else:
            ocr_response_channels[guild_id].append(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} added to OCR response channels for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_ocr_response_channel', help='Remove a channel from the OCR response list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_response_channel 123456789012345678 or !remove_ocr_response_channel #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_response_channel(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_response_channels = config['ocr_response_channels']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id in ocr_response_channels and channel_id in ocr_response_channels[guild_id]:
            ocr_response_channels[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR response channels for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR response channels list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='add_ocr_response_fallback', help='Add a fallback channel for OCR responses if no regular response channel is available.\nArguments: channel_id (int) - ID of the channel to add\nExample: !add_ocr_response_fallback 123456789012345678 or !add_ocr_response_fallback #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_response_fallback(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_response_fallback = config['ocr_response_fallback']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id not in ocr_response_fallback:
            ocr_response_fallback[guild_id] = []

        if channel_id in ocr_response_fallback[guild_id]:
            response = f'Channel {channel.mention} is already in the OCR response fallback list for this server.'
        else:
            ocr_response_fallback[guild_id].append(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} added to OCR response fallback for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_ocr_response_fallback', help='Remove a channel from the OCR response fallback list.\nArguments: channel_id (int) - ID of the channel to remove\nExample: !remove_ocr_response_fallback 123456789012345678 or !remove_ocr_response_fallback #channel-name')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_response_fallback(self, ctx, channel_id: int):
        config = self.bot.config
        ocr_response_fallback = config['ocr_response_fallback']
        
        channel = self.bot.get_channel(channel_id)
        if channel is None or str(channel.type) not in ['text', 'public_thread', 'private_thread'] or channel.guild.id != ctx.guild.id:
            response = f'Channel ID {channel_id} is invalid'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)
        if guild_id in ocr_response_fallback and channel_id in ocr_response_fallback[guild_id]:
            ocr_response_fallback[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR response fallback for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR response fallback list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)
