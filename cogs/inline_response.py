import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, Union

from utils.chatbot.persistence import JsonStorageManager
from utils.inline_response import InlineResponseManager, split_message, InlineResponseConfig
from utils import embed_helper
from utils.logging_setup import get_logger
from utils.chatbot.manager import chatbot_manager
from cogs.llm_commands import LLMCommands
from utils.permissions import command_category, has_command_permission

logger = get_logger()


class InlineResponseCog(commands.Cog, name="Inline Response"):
    """Cog for handling inline responses based on message content."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        storage_manager = JsonStorageManager()
        self.manager = InlineResponseManager(storage_manager)

    async def _resolve_target(self, ctx: commands.Context, target_str: str) -> Union[discord.TextChannel, discord.Thread, str, None]:
        """Resolves a string to a channel, thread, or 'server'."""
        if target_str is None:
            return ctx.channel
        if target_str.lower() == 'server':
            return 'server'
        try:
            return await commands.converter.TextChannelConverter().convert(ctx, target_str)
        except commands.ChannelNotFound:
            try:
                return await commands.converter.ThreadConverter().convert(ctx, target_str)
            except commands.ChannelNotFound:
                await embed_helper.create_embed_response(ctx, title="❌ Error", description=f"Target '{target_str}' not found.", color=discord.Color.red())
                return None

    async def _send_subcommand_help(self, ctx: commands.Context):
        """Sends a detailed help embed for a specific subcommand."""
        help_embed = discord.Embed(
            title=f"Help for: `!inline {ctx.command.name}`",
            description=ctx.command.help,
            color=discord.Color.orange()
        )
        await ctx.send(embed=help_embed)

    @commands.hybrid_group(name="inline", help="""
    Manages the Inline Response feature, which allows the bot to reply to mentions.
    This command group provides tools to enable/disable the feature, configure its trigger behavior, set the LLM model, and define the context parameters for generating responses.
    You can apply settings server-wide or for specific channels/threads.
    Usage: `!inline <subcommand> [value] [target]`
    Target can be 'server', a #channel, or a thread. If omitted, applies to the current channel.
    """)
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def inline(self, ctx: commands.Context):
        """Manages the Inline Response feature. Use without a subcommand to see help."""
        if ctx.invoked_subcommand is None:
            help_embed = discord.Embed(
                title="Inline Response Feature Help",
                description=self.inline.help,
                color=discord.Color.blue()
            )
            for command in self.inline.commands:
                signature = f"`!inline {command.name}"
                for param in command.clean_params.values():
                    signature += f" <{param.name}>"
                signature += "`"
                help_embed.add_field(name=f"**{command.name.capitalize()}**", value=f"{signature}\n{command.help}", inline=False)
            await ctx.send(embed=help_embed)

    @inline.command(name="status", help="""
    Displays the configuration for the Inline Response feature.
    Shows the effective settings for the specified target, indicating whether they are inherited from the server or set directly.
    Usage: `!inline status [target]`
    Target can be 'server', a #channel/thread, or a channel/thread ID. If omitted, shows status for the current channel.
    """)
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def status(self, ctx: commands.Context, target: str = None):
        """Display the current inline response settings for a target."""
        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        guild_id = ctx.guild.id
        
        if resolved_target == 'server':
            # For server status, we get the config as if it were a channel to see the defaults merged in.
            config = self.manager.get_channel_config(guild_id, 0)
            title = "Inline Response Server-wide Settings"
        else:
            config = self.manager.get_channel_config(guild_id, resolved_target.id)
            title = f"Inline Response Status for #{resolved_target.name}"

        server_conf_raw = self.manager.config_cache.get("servers", {}).get(str(guild_id), {}).get("server_settings", {})
        
        status_embed = discord.Embed(title=title, color=discord.Color.blue())

        def get_source(key):
            # For a specific channel, check if it has its own override
            if resolved_target != 'server' and str(resolved_target.id) in self.manager.config_cache.get("servers", {}).get(str(guild_id), {}).get("channels", {}):
                 if key in self.manager.config_cache["servers"][str(guild_id)]["channels"][str(resolved_target.id)]:
                    return "(Channel Specific)"
            # Check if it's set at the server level
            if key in server_conf_raw:
                return "(Server Default)"
            # Otherwise, it's the hardcoded default
            return "(Bot Default)"

        status_embed.add_field(name="Feature Enabled", value=f"✅ Yes {get_source('enabled')}" if config.enabled else f"❌ No {get_source('enabled')}", inline=False)
        status_embed.add_field(name="Mention Trigger", value=f"{'Message Start' if config.trigger_on_start_only else 'Anywhere in Message'} {get_source('trigger_on_start_only')}", inline=False)
        status_embed.add_field(name="LLM Model", value=f"`{config.model_type}` {get_source('model_type')}", inline=False)
        status_embed.add_field(name="Channel Context", value=f"`{config.context_messages}` messages {get_source('context_messages')}", inline=True)
        status_embed.add_field(name="User Context", value=f"`{config.user_context_messages}` messages {get_source('user_context_messages')}", inline=True)
        
        await ctx.send(embed=status_embed)

    @inline.command(name="toggle", help="""
    Enables or disables the Inline Response feature for a target.
    Usage: `!inline toggle <on|off> [target]`
    Target can be 'server', a #channel/thread, or a channel/thread ID.
    """)
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(enabled="Set to 'on' or 'off'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def toggle(self, ctx: commands.Context, enabled: Literal['on', 'off'] = None, target: str = None):
        """Enable or disable the inline response feature for a target."""
        if enabled is None:
            await self._send_subcommand_help(ctx)
            return
            
        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        config_to_modify = self.manager.get_specific_config(ctx.guild.id, target_id)
        
        new_status = enabled.lower() == 'on'
        config_to_modify.enabled = new_status
        
        if self.manager.set_config(ctx.guild.id, config_to_modify, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Inline responses have been **{'enabled' if new_status else 'disabled'}** for {target_name}.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="trigger", help="""
    Configures how the bot detects a mention to trigger a response for a target.
    Usage: `!inline trigger <start|anywhere> [target]`
    Target can be 'server', a #channel/thread, or a channel/thread ID.
    """)
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(behavior="Set to 'start' or 'anywhere'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def trigger(self, ctx: commands.Context, behavior: Literal['start', 'anywhere'] = None, target: str = None):
        """Configure the mention trigger behavior for a target."""
        if behavior is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        config_to_modify = self.manager.get_specific_config(ctx.guild.id, target_id)
        
        new_behavior = behavior.lower() == 'start'
        config_to_modify.trigger_on_start_only = new_behavior
        
        if self.manager.set_config(ctx.guild.id, config_to_modify, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Mention trigger for {target_name} set to **{behavior}**.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="model", help="""
    Sets the LLM model for inline responses for a target.
    Usage: `!inline model <ask|think|chat> [target]`
    Target can be 'server', a #channel/thread, or a channel/thread ID.
    """)
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(model_type="Choose 'ask', 'think', or 'chat'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def model(self, ctx: commands.Context, model_type: Literal['ask', 'think', 'chat'] = None, target: str = None):
        """Set the LLM model type for a target."""
        if model_type is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        config_to_modify = self.manager.get_specific_config(ctx.guild.id, target_id)
        
        config_to_modify.model_type = model_type.lower()
        
        if self.manager.set_config(ctx.guild.id, config_to_modify, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"LLM model for {target_name} set to `{model_type}`.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="context", help="""
    Configures context message counts for a target.
    Usage: `!inline context <channel_msgs> <user_msgs> [target]`
    Target can be 'server', a #channel/thread, or a channel/thread ID.
    """)
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(channel_messages="Number of recent channel messages.", user_messages="Number of recent user messages.", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def context(self, ctx: commands.Context, channel_messages: int = None, user_messages: int = None, target: str = None):
        """Configure context-building parameters for a target."""
        if channel_messages is None or user_messages is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        config_to_modify = self.manager.get_specific_config(ctx.guild.id, target_id)
        
        config_to_modify.context_messages = channel_messages
        config_to_modify.user_context_messages = user_messages
        
        if self.manager.set_config(ctx.guild.id, config_to_modify, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Context for {target_name} updated:\n• Channel Messages: `{channel_messages}`\n• User Messages: `{user_messages}`", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages to determine if an inline response should be triggered."""
        # 1a. Ignore self
        if message.author == self.bot.user:
            return

        # 1b. Ignore DMs
        if not message.guild:
            return

        # 1c. Check for mention
        if self.bot.user not in message.mentions:
            return

        # 1d. Check chatbot status (must be disabled)
        if chatbot_manager.is_chatbot_enabled(message.guild.id, message.channel.id):
            return

        # 1e. Check inline mode status (must be enabled)
        config = self.manager.get_channel_config(message.guild.id, message.channel.id)
        if not config.enabled:
            return

        # 1f. Check trigger setting
        mention_content = self.bot.user.mention
        # For slash commands, the mention is <@USER_ID>, but for messages it's <@!USER_ID>
        # We check for both to be safe.
        legacy_mention_content = mention_content.replace('<@', '<@!')

        is_mentioned_at_start = message.content.startswith(mention_content) or message.content.startswith(legacy_mention_content)

        if config.trigger_on_start_only and not is_mentioned_at_start:
            return
        
        # If all conditions are met, build the context and log it.
        logger.info(f"Inline response triggered for message {message.id} in channel {message.channel.id}")

        # 2. Build context and perform on-the-fly indexing
        context_messages = []
        try:
            # Step 2a: Build the context. This is critical for a quality response.
            context_messages = await self.manager.build_context(message)
            logger.info(f"Built context with {len(context_messages)} messages for inline response to {message.id}.")
        except Exception as e:
            logger.error(f"Failed to build context for inline response to message {message.id}. Aborting. Error: {e}", exc_info=True)
            await message.reply("Sorry, I had trouble gathering context to respond. Please try again.", delete_after=10)
            return

        # Step 2b: Perform non-critical on-the-fly indexing.
        # A failure here should be logged but not prevent the bot from responding.
        try:
            # Index the current channel.
            await chatbot_manager.index_manager.update_channel_index(message.channel)

            # Bulk index all unique users from the context.
            if context_messages:
                unique_users = list({msg.author for msg in context_messages if not msg.author.bot})
                if unique_users:
                    await chatbot_manager.index_manager.update_users_bulk(message.guild.id, unique_users, is_message_author=True)
                    logger.info(f"On-the-fly indexing complete for channel {message.channel.id} and {len(unique_users)} users.")
        except Exception as e:
            logger.warning(f"Non-critical error during on-the-fly indexing for message {message.id}: {e}", exc_info=True)
            # Do not abort; proceed with the response using the built context.


        # 3. Format the context for the LLM
        static_context, history = chatbot_manager.formatter.format_context_for_llm(
            messages=context_messages,
            guild_id=message.guild.id,
            channel_id=message.channel.id
        )

        # 4. Make the LLM request
        llm_cog: LLMCommands = self.bot.get_cog("LLMCommands")
        if not llm_cog:
            logger.error("LLMCommands cog not found, cannot make inline response.")
            return

        # The prompt is the trigger message with the mention removed.
        prompt = message.content.replace(self.bot.user.mention, "", 1).replace(legacy_mention_content, "", 1).strip()

        try:
            async with message.channel.typing():
                response_text, _ = await llm_cog.make_llm_request(
                    prompt=prompt,
                    model_type=config.model_type,
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    context=static_context,
                    history=history
                )

            # 5. Process and send the response
            cleaned_response = chatbot_manager.formatter.format_llm_output_for_discord(
                response_text,
                message.guild.id,
                self.bot.user.id,
                [self.bot.user.name, self.bot.user.display_name]
            )

            response_chunks = split_message(cleaned_response)

            if not response_chunks:
                logger.warning(f"LLM response for message {message.id} was empty after cleaning.")
                return

            # Send the first chunk as a reply
            await message.reply(response_chunks[0])

            # Send subsequent chunks as regular messages
            if len(response_chunks) > 1:
                for chunk in response_chunks[1:]:
                    await message.channel.send(chunk)
            
            logger.info(f"Successfully sent inline response to message {message.id} in {len(response_chunks)} chunks.")

        except Exception as e:
            logger.error(f"Error during inline LLM request for message {message.id}: {e}", exc_info=True)
            await message.reply("Sorry, I encountered an error while trying to respond.", delete_after=10)


async def setup(bot: commands.Bot):
    """Set up the InlineResponseCog."""
    await bot.add_cog(InlineResponseCog(bot))