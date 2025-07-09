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
from utils.discord_utils import reply_or_send

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
    This command group provides tools to enable/disable the feature, configure its trigger behavior, set the LLM model, define context parameters, and manage permissions for who can use the feature.
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
    @has_command_permission('manage_guild')
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
        
        # Permissions
        perm_lines = []
        everyone_role_id = ctx.guild.default_role.id
        
        # Check for 'everyone' in the effective whitelist
        everyone_whitelisted = everyone_role_id in config.role_whitelist

        # Determine permission source for improved status command
        channel_conf_raw = {}
        if resolved_target != 'server':
            channel_conf_raw = self.manager.config_cache.get("servers", {}).get(str(guild_id), {}).get("channels", {}).get(str(resolved_target.id), {})
        
        has_channel_perms = any(key in channel_conf_raw for key in ['role_whitelist', 'member_whitelist', 'role_blacklist', 'member_blacklist'])
        has_server_perms = any(key in server_conf_raw for key in ['role_whitelist', 'member_whitelist', 'role_blacklist', 'member_blacklist'])

        perm_source_text = ""
        if has_channel_perms and has_server_perms:
            perm_source_text = "(Channel & Server Combined)"
        elif has_channel_perms:
            perm_source_text = "(Channel Specific)"
        elif has_server_perms:
            perm_source_text = "(Server Inherited)"
        else:
            perm_source_text = "(Bot Default)"


        if everyone_whitelisted:
            perm_lines.append("• **Access Mode**: ✅ Everyone Allowed (except blacklisted)")
        else:
            perm_lines.append("• **Access Mode**: 🔒 Restricted to Whitelist")

        # Role Whitelist (show only if not everyone)
        if not everyone_whitelisted and config.role_whitelist:
            role_wl_names = [f"`@{ctx.guild.get_role(r_id).name}`" for r_id in config.role_whitelist if ctx.guild.get_role(r_id)]
            if role_wl_names:
                perm_lines.append(f"• **Whitelisted Roles**: {', '.join(role_wl_names)}")

        # Member Whitelist
        if config.member_whitelist:
            member_wl_names = []
            for m_id in config.member_whitelist:
                try:
                    member = ctx.guild.get_member(m_id) or await self.bot.fetch_user(m_id)
                    member_wl_names.append(f"`{member.name}`")
                except discord.NotFound:
                    member_wl_names.append(f"`Unknown User ({m_id})`")
            if member_wl_names:
                perm_lines.append(f"• **Whitelisted Members**: {', '.join(member_wl_names)}")

        # Role Blacklist
        if config.role_blacklist:
            role_bl_names = [f"`@{ctx.guild.get_role(r_id).name}`" for r_id in config.role_blacklist if ctx.guild.get_role(r_id)]
            if role_bl_names:
                perm_lines.append(f"• **Blacklisted Roles**: {', '.join(role_bl_names)}")

        # Member Blacklist
        if config.member_blacklist:
            member_bl_names = []
            for m_id in config.member_blacklist:
                try:
                    member = ctx.guild.get_member(m_id) or await self.bot.fetch_user(m_id)
                    member_bl_names.append(f"`{member.name}`")
                except discord.NotFound:
                    member_bl_names.append(f"`Unknown User ({m_id})`")
            if member_bl_names:
                perm_lines.append(f"• **Blacklisted Members**: {', '.join(member_bl_names)}")

        if not perm_lines and not everyone_whitelisted:
            perm_lines.append("• No permissions configured. Access is denied by default.")

        status_embed.add_field(name=f"Permissions {perm_source_text}", value="\n".join(perm_lines), inline=False)
        
        await ctx.send(embed=status_embed)

    @inline.command(name="toggle", help="""
     Enables or disables the Inline Response feature for a target.
     Note: This does not affect permissions. Use `!inline permissions` to manage access.
     Usage: `!inline toggle <on|off> [target]`
     Target can be 'server', a #channel/thread, or a channel/thread ID.
     """)
    @has_command_permission('manage_guild')
    @app_commands.describe(enabled="Set to 'on' or 'off'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def toggle(self, ctx: commands.Context, enabled: Literal['on', 'off'] = None, target: str = None):
        """Enable or disable the inline response feature for a target."""
        if enabled is None:
            await self._send_subcommand_help(ctx)
            return
            
        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        new_status = enabled.lower() == 'on'
        
        if self.manager.set_config(ctx.guild.id, {'enabled': new_status}, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Inline responses have been **{'enabled' if new_status else 'disabled'}** for {target_name}.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="trigger", help="""
     Configures how the bot detects a mention to trigger a response for a target.
     Note: This does not affect permissions. Use `!inline permissions` to manage access.
     Usage: `!inline trigger <start|anywhere> [target]`
     Target can be 'server', a #channel/thread, or a channel/thread ID.
     """)
    @has_command_permission('manage_guild')
    @app_commands.describe(behavior="Set to 'start' or 'anywhere'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def trigger(self, ctx: commands.Context, behavior: Literal['start', 'anywhere'] = None, target: str = None):
        """Configure the mention trigger behavior for a target."""
        if behavior is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        new_behavior = behavior.lower() == 'start'

        if self.manager.set_config(ctx.guild.id, {'trigger_on_start_only': new_behavior}, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Mention trigger for {target_name} set to **{behavior}**.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="model", help="""
     Sets the LLM model for inline responses for a target.
     Note: This does not affect permissions. Use `!inline permissions` to manage access.
     Usage: `!inline model <ask|think|chat> [target]`
     Target can be 'server', a #channel/thread, or a channel/thread ID.
     """)
    @has_command_permission('manage_guild')
    @app_commands.describe(model_type="Choose 'ask', 'think', or 'chat'", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def model(self, ctx: commands.Context, model_type: Literal['ask', 'think', 'chat'] = None, target: str = None):
        """Set the LLM model type for a target."""
        if model_type is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        
        if self.manager.set_config(ctx.guild.id, {'model_type': model_type.lower()}, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"LLM model for {target_name} set to `{model_type}`.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    @inline.command(name="context", help="""
     Configures context message counts for a target.
     Note: This does not affect permissions. Use `!inline permissions` to manage access.
     Usage: `!inline context <channel_msgs> <user_msgs> [target]`
     Target can be 'server', a #channel/thread, or a channel/thread ID.
     """)
    @has_command_permission('manage_guild')
    @app_commands.describe(channel_messages="Number of recent channel messages.", user_messages="Number of recent user messages.", target="Optional: 'server', a #channel/thread, or a channel/thread ID.")
    async def context(self, ctx: commands.Context, channel_messages: int = None, user_messages: int = None, target: str = None):
        """Configure context-building parameters for a target."""
        if channel_messages is None or user_messages is None:
            await self._send_subcommand_help(ctx)
            return

        resolved_target = await self._resolve_target(ctx, target)
        if resolved_target is None and target is not None: return

        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        new_settings = {
            'context_messages': channel_messages,
            'user_context_messages': user_messages
        }
        
        if self.manager.set_config(ctx.guild.id, new_settings, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Settings Updated", description=f"Context for {target_name} updated:\n• Channel Messages: `{channel_messages}`\n• User Messages: `{user_messages}`", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update settings.", color=discord.Color.red())

    async def _update_permissions(self, ctx: commands.Context, action: Literal['add', 'remove'], list_type: Literal['whitelist', 'blacklist'], entity_str: str, target_str: str):
        """Helper function to add/remove entities from permission lists."""
        # Step 1: Resolve the target for the permission change (server, channel, or thread).
        resolved_target = await self._resolve_target(ctx, target_str)
        if resolved_target is None and target_str is not None: return

        # Step 2: Get the specific configuration for the target.
        # If target_id is None, it fetches the server-wide configuration.
        target_id = resolved_target.id if isinstance(resolved_target, (discord.TextChannel, discord.Thread)) else None
        # Get a mutable copy of the specific raw config dict
        config_to_modify = self.manager.get_specific_config(ctx.guild.id, target_id)
        # We need to wrap it in the dataclass to ensure lists are present
        config_obj = InlineResponseConfig(**config_to_modify)

        # Step 3: Identify the entity (role or member) to be added or removed.
        entity_id = None
        entity_type = None
        entity_name = ""
        
        # The input `entity_str` can be a name, ID, or mention. We try to convert it.
        entity_to_process = None
        if entity_str.lower() == 'everyone':
            # Special case for the @everyone role.
            if list_type == 'blacklist':
                await embed_helper.create_embed_response(ctx, title="❌ Error", description="You cannot add `@everyone` to the blacklist.", color=discord.Color.red())
                return
            entity_to_process = ctx.guild.default_role
            entity_name = "@everyone"
        else:
            # Try to resolve as a role first, then as a member.
            try:
                entity_to_process = await commands.RoleConverter().convert(ctx, entity_str)
            except commands.RoleNotFound:
                try:
                    entity_to_process = await commands.MemberConverter().convert(ctx, entity_str)
                except commands.MemberNotFound:
                    await embed_helper.create_embed_response(ctx, title="❌ Error", description=f"Could not find a role or member named `{entity_str}`.", color=discord.Color.red())
                    return

        # Step 4: Extract ID, type, and name from the resolved discord entity.
        if isinstance(entity_to_process, discord.Role):
            if entity_to_process.is_default() and list_type == 'blacklist':
                await embed_helper.create_embed_response(ctx, title="❌ Error", description="You cannot add the `@everyone` role to the blacklist.", color=discord.Color.red())
                return
            entity_id = entity_to_process.id
            entity_type = 'role'
            entity_name = f"@{entity_to_process.name}"
        elif isinstance(entity_to_process, discord.Member):
            entity_id = entity_to_process.id
            entity_type = 'member'
            entity_name = entity_to_process.name

        if not entity_id:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="An unknown error occurred while processing the entity.", color=discord.Color.red())
            return

        # Step 5: Get the correct permission list from the config object.
        # e.g., 'role_whitelist', 'member_blacklist', etc.
        perm_list_name = f"{entity_type}_{list_type}"
        perm_list = getattr(config_obj, perm_list_name)

        # Step 6: Perform the add or remove action.
        if action == 'add':
            if entity_id not in perm_list:
                perm_list.append(entity_id)
                action_text = "added to"
            else:
                await embed_helper.create_embed_response(ctx, title="ℹ️ Info", description=f"`{entity_name}` is already in the {list_type}.", color=discord.Color.blue())
                return
        else: # remove
            if entity_id in perm_list:
                perm_list.remove(entity_id)
                action_text = "removed from"
            else:
                await embed_helper.create_embed_response(ctx, title="ℹ️ Info", description=f"`{entity_name}` is not in the {list_type}.", color=discord.Color.blue())
                return

        # Step 7: Save the updated configuration and notify the user.
        # We only want to save the permission lists, not the entire object
        updated_perms = {
            "role_whitelist": config_obj.role_whitelist,
            "member_whitelist": config_obj.member_whitelist,
            "role_blacklist": config_obj.role_blacklist,
            "member_blacklist": config_obj.member_blacklist,
        }
        if self.manager.set_config(ctx.guild.id, updated_perms, target_id):
            target_name = "the server" if resolved_target == 'server' else resolved_target.mention
            await embed_helper.create_embed_response(ctx, title="✅ Permissions Updated", description=f"`{entity_name}` has been {action_text} the {list_type} for {target_name}.", color=discord.Color.green())
        else:
            await embed_helper.create_embed_response(ctx, title="❌ Error", description="Failed to update permissions.", color=discord.Color.red())

    @inline.group(name="permissions", help="""
    Manages the permission system for who can trigger an inline response.

    **Permission Logic:**
    The system uses a default-deny model with whitelists and blacklists. The rules are checked in this order:
    1.  **Blacklist:** If a user or any of their roles are on the blacklist, they are **always** denied access. This check is absolute.
    2.  **Whitelist:** If not blacklisted, the user must be on the whitelist to get access.
        - Adding the `@everyone` role to the whitelist grants access to all non-blacklisted users.
        - Otherwise, the user must be individually whitelisted or have a whitelisted role.
    3.  **Default:** If a user is not on the blacklist or the whitelist, access is **denied**.

    **Configuration Scope:**
    Permissions can be set server-wide or for specific channels/threads. Channel settings are **combined** with server settings. For example, if you set a whitelist for a channel, its members are added to the server's whitelist for that specific channel. The same applies to blacklists.
    """)
    @has_command_permission('manage_guild')
    async def permissions(self, ctx: commands.Context):
        """Manages inline response permissions."""
        if ctx.invoked_subcommand is None:
            await self._send_subcommand_help(ctx)

    @permissions.command(name="whitelist", help="""
    Manages the whitelist of users and roles allowed to trigger inline responses.

    **Arguments:**
    - `action`: `add` or `remove`.
    - `entity`: The role or member to add/remove. Can be a name, ID, or mention. Use `everyone` for the @everyone role.
    - `target` (Optional): The scope of the change. Can be `server`, a #channel/thread, or a channel/thread ID. Defaults to the current channel.

    **Usage Examples:**
    - `!inline permissions whitelist add everyone server` - Allows everyone (not on a blacklist) to use inline responses server-wide.
    - `!inline permissions whitelist add "Cool People"` - Adds the 'Cool People' role to the whitelist for the current channel.
    - `!inline permissions whitelist remove @SomeUser #general` - Removes a specific user from the whitelist for the #general channel.
    """)
    @has_command_permission('manage_guild')
    @app_commands.describe(
        action="Choose whether to 'add' or 'remove' from the whitelist.",
        entity="The name, ID, or mention of the role/member, or the word 'everyone'.",
        target="Optional: 'server', a #channel/thread, or a channel/thread ID."
    )
    async def permissions_whitelist(self, ctx: commands.Context, action: Literal['add', 'remove'] = None, entity: str = None, target: str = None):
        """Adds or removes an entity from the whitelist."""
        if action is None or entity is None:
            await self._send_subcommand_help(ctx)
            return
        # This command delegates the core logic to the _update_permissions helper function.
        await self._update_permissions(ctx, action, 'whitelist', entity, target)

    @permissions.command(name="blacklist", help="""
    Manages the blacklist of users and roles explicitly denied from triggering inline responses.
    - The blacklist **always** takes priority over the whitelist.

    **Arguments:**
    - `action`: `add` or `remove`.
    - `entity`: The role or member to add/remove. Can be a name, ID, or mention. You cannot blacklist `everyone`.
    - `target` (Optional): The scope of the change. Can be `server`, a #channel/thread, or a channel/thread ID. Defaults to the current channel.

    **Usage Examples:**
    - `!inline permissions blacklist add "Known Spammers" server` - Blacklists the 'Known Spammers' role server-wide.
    - `!inline permissions blacklist remove @AnnoyingUser` - Removes a user from the blacklist in the current channel.
    """)
    @has_command_permission('manage_guild')
    @app_commands.describe(
        action="Choose whether to 'add' or 'remove' from the blacklist.",
        entity="The name, ID, or mention of the role/member. You cannot blacklist @everyone.",
        target="Optional: 'server', a #channel/thread, or a channel/thread ID."
    )
    async def permissions_blacklist(self, ctx: commands.Context, action: Literal['add', 'remove'] = None, entity: str = None, target: str = None):
        """Adds or removes an entity from the blacklist."""
        if action is None or entity is None:
            await self._send_subcommand_help(ctx)
            return
        # This command delegates the core logic to the _update_permissions helper function.
        await self._update_permissions(ctx, action, 'blacklist', entity, target)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages to determine if an inline response should be triggered."""
        # 1a. Ignore self
        if message.author == self.bot.user:
            return


        # 1b. Ignore DMs
        if not message.guild:
            return

        # 1c. Check for an explicit mention in the message content.
        # This is to distinguish from implicit mentions from replies.
        mention_content = self.bot.user.mention
        legacy_mention_content = mention_content.replace('<@', '<@!')
        if mention_content not in message.content and legacy_mention_content not in message.content:
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

        # 1g. Check permissions
        author = message.author
        # Make sure author is a Member object to get roles
        if not isinstance(author, discord.Member):
            try:
                author = await message.guild.fetch_member(author.id)
            except discord.NotFound:
                logger.warning(f"Could not find member {author.id} in guild {message.guild.id} to check permissions.")
                return

        author_role_ids = {role.id for role in author.roles}
        
        # 1. Blacklist check (absolute priority)
        if author.id in config.member_blacklist:
            logger.debug(f"User {author.id} is in member blacklist for channel {message.channel.id}. Ignoring trigger.")
            return
        if not author_role_ids.isdisjoint(config.role_blacklist):
            logger.debug(f"User {author.id} has a blacklisted role for channel {message.channel.id}. Ignoring trigger.")
            return

        # 2. Whitelist check
        everyone_role_id = message.guild.default_role.id
        is_everyone_whitelisted = everyone_role_id in config.role_whitelist
        
        is_whitelisted = False
        if is_everyone_whitelisted:
            is_whitelisted = True
        elif author.id in config.member_whitelist:
            is_whitelisted = True
        elif not author_role_ids.isdisjoint(config.role_whitelist):
            is_whitelisted = True

        # If not whitelisted, deny access
        if not is_whitelisted:
            logger.debug(f"User {author.id} is not whitelisted for inline responses in channel {message.channel.id}. Ignoring trigger.")
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
            await reply_or_send(message, "Sorry, I had trouble gathering context to respond. Please try again.", delete_after=10)
            return

        # Step 2b: Perform non-critical on-the-fly indexing.
        # A failure here should be logged but not prevent the bot from responding.
        try:
            # Index the current channel.
            await chatbot_manager.index_manager.update_channel_index(message.channel)

            # Bulk index all unique users from the context.
            if context_messages:
                unique_users = list({msg.author for msg in context_messages if not msg.is_bot_response and msg.author})
                if unique_users:
                    await chatbot_manager.index_manager.update_users_bulk(message.guild.id, unique_users, is_message_author=True)
                    logger.info(f"On-the-fly indexing complete for channel {message.channel.id} and {len(unique_users)} users.")
        except Exception as e:
            logger.warning(f"Non-critical error during on-the-fly indexing for message {message.id}: {e}", exc_info=True)
            # Do not abort; proceed with the response using the built context.


        # 3. Format the context for the LLM
        static_context, history = await chatbot_manager.formatter.format_context_for_llm(
            messages=context_messages,
            guild_id=message.guild.id,
            channel_id=message.channel.id
        )

        # 4. Make the LLM request
        llm_cog: LLMCommands = self.bot.get_cog("LLMCommands")
        if not llm_cog:
            logger.error("LLMCommands cog not found, cannot make inline response.")
            return

        # The history from the formatter now includes the trigger message, fully formatted.
        # We need to separate it to avoid duplication.
        if not history:
            logger.error(f"History is empty for message {message.id}, cannot generate response.")
            return

        # The last message in the history is our trigger message.
        trigger_message_content = history[-1]['content']
        
        # The rest of the history is the actual context.
        context_history = history[:-1]

        # Extract image URLs from the trigger message content if it's a list of parts
        image_urls = []
        if isinstance(trigger_message_content, list):
            for part in trigger_message_content:
                if part.get("type") == "image_url":
                    image_urls.append(part.get("image_url", {}).get("url"))

        try:
            async with message.channel.typing():
                response_text, _ = await llm_cog.make_llm_request(
                    prompt=trigger_message_content, # The fully formatted message is the prompt
                    model_type=config.model_type,
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    context=static_context,
                    history=context_history, # Pass the history without the trigger message
                    image_urls=image_urls
                )
            
            logger.debug(f"Raw LLM response_text for message {message.id}: '{response_text[:500]}...' (truncated)")

            # 5. Process and send the response
            cleaned_response = await chatbot_manager.formatter.format_llm_output_for_discord(
                response_text,
                message.guild.id,
                self.bot.user.id,
                [self.bot.user.name, self.bot.user.display_name]
            )
            logger.debug(f"Cleaned LLM response_text for message {message.id}: '{cleaned_response[:500]}...' (truncated)")

            response_chunks = split_message(cleaned_response)
            logger.debug(f"Response chunks length for message {message.id}: {len(response_chunks)}")
            if response_chunks:
                logger.debug(f"First response chunk for message {message.id}: '{response_chunks[0][:500]}...' (truncated)")


            if not response_chunks or not response_chunks[0].strip(): # Added check for empty string after stripping whitespace
                logger.warning(f"LLM response for message {message.id} was empty or whitespace-only after cleaning and splitting. Raw: '{response_text[:100]}', Cleaned: '{cleaned_response[:100]}'")
                return
 
            # Send the first chunk as a reply
            await reply_or_send(message, response_chunks[0])
 
            # Send subsequent chunks as regular messages
            if len(response_chunks) > 1:
                for chunk in response_chunks[1:]:
                    await message.channel.send(chunk)
            
            logger.info(f"Successfully sent inline response to message {message.id} in {len(response_chunks)} chunks.")
 
        except Exception as e:
            logger.error(f"Error during inline LLM request for message {message.id}: {e}", exc_info=True)
            await reply_or_send(message, "Sorry, I encountered an error while trying to respond.", delete_after=10)


async def setup(bot: commands.Bot):
    """Set up the InlineResponseCog."""
    await bot.add_cog(InlineResponseCog(bot))
