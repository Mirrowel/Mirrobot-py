import discord
from discord.ext import commands
from utils.discord_utils import reply_or_send
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category, check_target_permissions
from config.config_manager import save_config

logger = get_logger()

class OCRConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='add_ocr_read_channel', help='Add a channel where bot will scan images for OCR processing.\nArguments: channel - The channel to add (mention, ID, or name)\n           [language] (str) - Optional language code for OCR (default: eng, options: eng, rus)\nExample: !add_ocr_read_channel #general rus')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_read_channel(self, ctx, channel: discord.abc.GuildChannel, language: str = "eng"):
        config = self.bot.config
        
        # Validate language
        valid_languages = ["eng", "rus"]
        if language.lower() not in valid_languages:
            await reply_or_send(ctx, f"Invalid language code. Supported languages: {', '.join(valid_languages)}")
            return
            
        # Convert to lowercase for consistency
        language = language.lower()
        
        # Initialize structure if needed
        if 'ocr_channel_config' not in config:
            config['ocr_channel_config'] = {}
        
        # Ensure backward compatibility
        if 'ocr_read_channels' not in config:
            config['ocr_read_channels'] = {}
        
        ocr_read_channels = config['ocr_read_channels']
        ocr_channel_config = config['ocr_channel_config']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return
        
        if str(channel.type) not in ['text', 'public_thread', 'private_thread']:
            response = f'Channel {channel.mention} is not a valid text channel or thread'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(
            channel, 
            ["view_channel", "read_message_history", "read_messages", "send_messages"], 
            ctx
        )
        if not has_perms:
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        
        # Initialize guild entries if needed
        if guild_id not in ocr_read_channels:
            ocr_read_channels[guild_id] = []
        if guild_id not in ocr_channel_config:
            ocr_channel_config[guild_id] = {}
            
        # Check if channel is already added
        if channel_id in ocr_read_channels[guild_id]:
            # Update language if channel exists
            ocr_channel_config[guild_id][str(channel_id)] = {"lang": language}
            save_config(config)
            language_name = "English" if language == "eng" else "Russian"
            response = f'Channel {channel.mention} is already in the OCR read channels list. Updated language to {language_name}.'
        else:
            # Add channel and language
            ocr_read_channels[guild_id].append(channel_id)
            ocr_channel_config[guild_id][str(channel_id)] = {"lang": language}
            save_config(config)
            language_name = "English" if language == "eng" else "Russian"
            response = f'Channel {channel.mention} added to OCR reading channels with language: {language_name}'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

    @commands.command(name='set_ocr_language', help='Set the OCR language for a channel.\nArguments: channel - The channel to configure (mention, ID, or name)\n           language (str) - Language code for OCR (options: eng, rus)\nExample: !set_ocr_language #general rus')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def set_ocr_language(self, ctx, channel: discord.abc.GuildChannel, language: str):
        config = self.bot.config
        
        # Validate language
        valid_languages = ["eng", "rus"]
        if language.lower() not in valid_languages:
            await reply_or_send(ctx, f"Invalid language code. Supported languages: {', '.join(valid_languages)}")
            return
            
        # Convert to lowercase for consistency
        language = language.lower()
        
        # Initialize structure if needed
        if 'ocr_channel_config' not in config:
            config['ocr_channel_config'] = {}
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            await reply_or_send(ctx, response)
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        channel_in_read = False
        channel_in_response = False
        
        # Check if channel is in read channels and update if needed
        if guild_id in config['ocr_read_channels'] and channel_id in config['ocr_read_channels'][guild_id]:
            channel_in_read = True
            
        # Check if channel is in response channels and update if needed
        if guild_id in config['ocr_response_channels'] and channel_id in config['ocr_response_channels'][guild_id]:
            channel_in_response = True
            
        # Initialize guild entry if needed
        if guild_id not in config['ocr_channel_config']:
            config['ocr_channel_config'][guild_id] = {}
            
        # Update based on channel type
        updates = []
        channel_str_id = str(channel_id)
        
        if channel_in_read:
            config['ocr_channel_config'][guild_id][channel_str_id] = {"lang": language}
            updates.append("read")
            
        if channel_in_response:
            # Make sure to create a new dict to avoid modifying the same reference
            config['ocr_channel_config'][guild_id][channel_str_id] = {"lang": language}
            updates.append("response")
            
        if not updates:
            await reply_or_send(ctx, f'Channel {channel.mention} is not configured as an OCR read or response channel.')
            return
            
        save_config(config)
        language_name = "English" if language == "eng" else "Russian"
        response = f'Updated OCR language to {language_name} for channel {channel.mention}'
        
        await reply_or_send(ctx, response)

    # Modify server_info command in bot_config.py to show language settings
    # This would be in bot_config.py but showing a sample here
    def get_language_display(self, config, guild_id, channel_id):
        """Helper method to get language display name for a channel"""
        channel_config = config.get('ocr_channel_config', {}).get(guild_id, {}).get(str(channel_id), {})
        lang = channel_config.get('lang', 'eng')
        return "Russian" if lang == "rus" else "English"

    @commands.command(name='remove_ocr_read_channel', help='Remove a channel from the OCR reading list.\nArguments: channel - The channel to remove (mention, ID, or name)\nExample: !remove_ocr_read_channel #general')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_read_channel(self, ctx, channel: discord.abc.GuildChannel):
        config = self.bot.config
        ocr_read_channels = config['ocr_read_channels']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(channel, ["view_channel"], ctx)
        if not has_perms:
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        if guild_id in ocr_read_channels and channel_id in ocr_read_channels[guild_id]:
            ocr_read_channels[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR reading channels for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR reading channels list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

    @commands.command(name='add_ocr_response_channel', help='Add a channel where bot will post OCR analysis results.\nArguments: channel - The channel to add (mention, ID, or name)\n           [language] (str) - Optional language code for OCR (default: eng, options: eng, rus)\nExample: !add_ocr_response_channel #results rus')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_response_channel(self, ctx, channel: discord.abc.GuildChannel, language: str = "eng"):
        config = self.bot.config
        
        # Validate language
        valid_languages = ["eng", "rus"]
        if language.lower() not in valid_languages:
            await reply_or_send(ctx, f"Invalid language code. Supported languages: {', '.join(valid_languages)}")
            return
            
        # Convert to lowercase for consistency
        language = language.lower()
        
        # Initialize structure if needed
        if 'ocr_channel_config' not in config:
            config['ocr_channel_config'] = {}
        
        ocr_response_channels = config['ocr_response_channels']
        ocr_channel_config = config['ocr_channel_config']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return
        
        if str(channel.type) not in ['text', 'public_thread', 'private_thread']:
            response = f'Channel {channel.mention} is not a valid text channel or thread'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(
            channel, 
            ["view_channel", "send_messages", "embed_links"], 
            ctx
        )
        if not has_perms:
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        if guild_id not in ocr_response_channels:
            ocr_response_channels[guild_id] = []
            
        # Initialize guild entries if needed
        if guild_id not in ocr_channel_config:
            ocr_channel_config[guild_id] = {}

        if channel_id in ocr_response_channels[guild_id]:
            # Update language if channel exists
            ocr_channel_config[guild_id][str(channel_id)] = {"lang": language}
            save_config(config)
            language_name = "English" if language == "eng" else "Russian"
            response = f'Channel {channel.mention} is already in the OCR response channels list. Updated language to {language_name}.'
        else:
            ocr_response_channels[guild_id].append(channel_id)
            ocr_channel_config[guild_id][str(channel_id)] = {"lang": language}
            save_config(config)
            language_name = "English" if language == "eng" else "Russian"
            response = f'Channel {channel.mention} added to OCR response channels with language: {language_name}'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

    @commands.command(name='remove_ocr_response_channel', help='Remove a channel from the OCR response list.\nArguments: channel - The channel to remove (mention, ID, or name)\nExample: !remove_ocr_response_channel #results')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_response_channel(self, ctx, channel: discord.abc.GuildChannel):
        config = self.bot.config
        ocr_response_channels = config['ocr_response_channels']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(channel, ["view_channel"], ctx)
        if not has_perms:
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        if guild_id in ocr_response_channels and channel_id in ocr_response_channels[guild_id]:
            ocr_response_channels[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR response channels for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR response channels list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

    @commands.command(name='add_ocr_response_fallback', help='Add a fallback channel for OCR responses if no regular response channel is available.\nArguments: channel - The channel to add (mention, ID, or name)\nExample: !add_ocr_response_fallback #fallback-channel')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_ocr_response_fallback(self, ctx, channel: discord.abc.GuildChannel):
        config = self.bot.config
        ocr_response_fallback = config['ocr_response_fallback']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return
        
        if str(channel.type) not in ['text', 'public_thread', 'private_thread']:
            response = f'Channel {channel.mention} is not a valid text channel or thread'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        if guild_id not in ocr_response_fallback:
            ocr_response_fallback[guild_id] = []

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(
            channel, 
            ["view_channel", "read_message_history", "read_messages", "send_messages"], 
            ctx
        )
        if not has_perms:
            return

        if channel_id in ocr_response_fallback[guild_id]:
            response = f'Channel {channel.mention} is already in the OCR response fallback list for this server.'
        else:
            ocr_response_fallback[guild_id].append(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} added to OCR response fallback for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

    @commands.command(name='remove_ocr_response_fallback', help='Remove a channel from the OCR response fallback list.\nArguments: channel - The channel to remove (mention, ID, or name)\nExample: !remove_ocr_response_fallback #fallback-channel')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_ocr_response_fallback(self, ctx, channel: discord.abc.GuildChannel):
        config = self.bot.config
        ocr_response_fallback = config['ocr_response_fallback']
        
        if channel.guild.id != ctx.guild.id:
            response = f'Channel {channel.mention} is not in this server'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await reply_or_send(ctx, response)
            return

        # Check if the bot has required permissions in the channel
        has_perms, _, _ = check_target_permissions(channel, ["view_channel"], ctx)
        if not has_perms:
            return

        guild_id = str(ctx.guild.id)
        channel_id = channel.id
        if guild_id in ocr_response_fallback and channel_id in ocr_response_fallback[guild_id]:
            ocr_response_fallback[guild_id].remove(channel_id)
            save_config(config)
            response = f'Channel {channel.mention} removed from OCR response fallback for this server.'
        else:
            response = f'Channel {channel.mention} is not in the OCR response fallback list for this server.'
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await reply_or_send(ctx, response)

async def setup(bot):
    await bot.add_cog(OCRConfigCog(bot))
