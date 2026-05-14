import discord
from discord import app_commands
from discord.ext import commands

from config.config_manager import save_config
from utils.embed_helper import create_embed_response
from utils.logging_setup import get_logger
from utils.permissions import (
    command_category,
    get_categories,
    has_command_permission,
    normalize_command_lock_name,
)

logger = get_logger()


class CommandLocksCog(commands.Cog, name="Command Locks"):
    """Manage server blacklists for commands and categories."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _locks(self):
        locks = self.bot.config.setdefault(
            "command_server_locks", {"commands": {}, "categories": {}}
        )
        locks.setdefault("commands", {})
        locks.setdefault("categories", {})
        return locks

    def _guild_id(self, ctx: commands.Context, guild_id: str = None):
        if guild_id:
            return str(guild_id)
        if ctx.guild:
            return str(ctx.guild.id)
        return None

    def _locks_active(self):
        locks = self._locks()
        return bool(locks.get("commands") or locks.get("categories"))

    def _find_command_name(self, command_name: str):
        wanted = normalize_command_lock_name(command_name)
        for command in self.bot.walk_commands():
            names = {command.name}
            qualified_name = getattr(command, "qualified_name", None)
            if qualified_name:
                names.add(qualified_name)
            if wanted in {normalize_command_lock_name(name) for name in names}:
                return qualified_name or command.name
        return None

    def _find_category_name(self, category_name: str):
        wanted = normalize_command_lock_name(category_name)
        for category in get_categories():
            if normalize_command_lock_name(category) == wanted:
                return category
        return None

    async def _defer_if_interaction(self, ctx: commands.Context):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()

    async def _sync_slash_commands(self, guild_id: str, locks_were_active: bool, locks_are_active: bool):
        from core.bot import cleanup_stale_commands

        if locks_were_active and locks_are_active:
            await cleanup_stale_commands(
                self.bot,
                initial_delay=False,
                guild_ids=[guild_id],
            )
        else:
            await cleanup_stale_commands(self.bot, initial_delay=False)

    async def _send_group_help(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Command Lock Help",
            description=(
                "Disable commands or whole categories in specific servers. Listed servers "
                "cannot use that command/category and slash visibility is resynced per guild."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Commands",
            value=(
                "`!command_lock command add <command_name> [guild_id]`\n"
                "`!command_lock command remove <command_name> [guild_id]`\n"
                "`!command_lock category add <category_name> [guild_id]`\n"
                "`!command_lock category remove <category_name> [guild_id]`\n"
                "`!command_lock list [guild_id]`"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_group(
        name="command_lock",
        help="Manage server blacklists for bot commands and command categories.",
    )
    @has_command_permission()
    @command_category("Bot Configuration")
    async def command_lock(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_group_help(ctx)

    @command_lock.group(name="command", help="Manage locks for individual commands.")
    @has_command_permission()
    async def command_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_group_help(ctx)

    @command_group.command(name="add", help="Disable a command in a specific server.")
    @has_command_permission()
    @app_commands.describe(
        command_name="Command name, such as ask or role_share.",
        guild_id="Server ID. Defaults to the current server.",
    )
    async def add_command_lock(
        self, ctx: commands.Context, command_name: str, guild_id: str = None
    ):
        target_guild_id = self._guild_id(ctx, guild_id)
        if not target_guild_id:
            await create_embed_response(
                ctx,
                title="Command Lock Error",
                description="Provide a guild ID or run this command in a server.",
                color=discord.Color.red(),
            )
            return

        matched_name = self._find_command_name(command_name)
        if not matched_name:
            await create_embed_response(
                ctx,
                title="Command Lock Error",
                description=f"Command `{command_name}` was not found.",
                color=discord.Color.red(),
            )
            return

        locks = self._locks()
        locks_were_active = self._locks_active()
        key = normalize_command_lock_name(matched_name)
        blocked_guilds = locks["commands"].setdefault(key, [])
        if target_guild_id not in [str(guild_id) for guild_id in blocked_guilds]:
            await self._defer_if_interaction(ctx)
            blocked_guilds.append(target_guild_id)
            save_config(self.bot.config)
            await self._sync_slash_commands(
                target_guild_id,
                locks_were_active,
                self._locks_active(),
            )

        await create_embed_response(
            ctx,
            title="Command Lock Updated",
            description=f"`{matched_name}` is now disabled in server `{target_guild_id}`.",
            color=discord.Color.green(),
        )

    @command_group.command(name="remove", help="Re-enable a command in a specific server.")
    @has_command_permission()
    @app_commands.describe(
        command_name="Command name, such as ask or role_share.",
        guild_id="Server ID. Defaults to the current server.",
    )
    async def remove_command_lock(
        self, ctx: commands.Context, command_name: str, guild_id: str = None
    ):
        target_guild_id = self._guild_id(ctx, guild_id)
        if not target_guild_id:
            await create_embed_response(
                ctx,
                title="Command Lock Error",
                description="Provide a guild ID or run this command in a server.",
                color=discord.Color.red(),
            )
            return

        matched_name = self._find_command_name(command_name) or command_name
        locks = self._locks()
        locks_were_active = self._locks_active()
        key = normalize_command_lock_name(matched_name)
        blocked_guilds = locks["commands"].get(key, [])
        before = len(blocked_guilds)
        locks["commands"][key] = [
            str(guild_id) for guild_id in blocked_guilds if str(guild_id) != target_guild_id
        ]
        if not locks["commands"][key]:
            del locks["commands"][key]

        if len(locks["commands"].get(key, [])) != before:
            await self._defer_if_interaction(ctx)
            save_config(self.bot.config)
            await self._sync_slash_commands(
                target_guild_id,
                locks_were_active,
                self._locks_active(),
            )

        await create_embed_response(
            ctx,
            title="Command Lock Updated",
            description=f"`{matched_name}` is now enabled in server `{target_guild_id}`.",
            color=discord.Color.green(),
        )

    @command_lock.group(name="category", help="Manage locks for command categories.")
    @has_command_permission()
    async def category_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_group_help(ctx)

    @category_group.command(name="add", help="Disable a category in a specific server.")
    @has_command_permission()
    @app_commands.describe(
        category_name="Category name, such as AI Assistant or Role Sharing.",
        guild_id="Server ID. Defaults to the current server.",
    )
    async def add_category_lock(
        self, ctx: commands.Context, category_name: str, guild_id: str = None
    ):
        target_guild_id = self._guild_id(ctx, guild_id)
        matched_name = self._find_category_name(category_name)
        if not target_guild_id or not matched_name:
            await create_embed_response(
                ctx,
                title="Command Lock Error",
                description="Provide a valid category and guild ID/current server.",
                color=discord.Color.red(),
            )
            return

        locks = self._locks()
        locks_were_active = self._locks_active()
        key = normalize_command_lock_name(matched_name)
        blocked_guilds = locks["categories"].setdefault(key, [])
        if target_guild_id not in [str(guild_id) for guild_id in blocked_guilds]:
            await self._defer_if_interaction(ctx)
            blocked_guilds.append(target_guild_id)
            save_config(self.bot.config)
            await self._sync_slash_commands(
                target_guild_id,
                locks_were_active,
                self._locks_active(),
            )

        await create_embed_response(
            ctx,
            title="Command Lock Updated",
            description=f"Category `{matched_name}` is now disabled in server `{target_guild_id}`.",
            color=discord.Color.green(),
        )

    @category_group.command(name="remove", help="Re-enable a category in a specific server.")
    @has_command_permission()
    @app_commands.describe(
        category_name="Category name, such as AI Assistant or Role Sharing.",
        guild_id="Server ID. Defaults to the current server.",
    )
    async def remove_category_lock(
        self, ctx: commands.Context, category_name: str, guild_id: str = None
    ):
        target_guild_id = self._guild_id(ctx, guild_id)
        matched_name = self._find_category_name(category_name) or category_name
        if not target_guild_id:
            await create_embed_response(
                ctx,
                title="Command Lock Error",
                description="Provide a guild ID or run this command in a server.",
                color=discord.Color.red(),
            )
            return

        locks = self._locks()
        locks_were_active = self._locks_active()
        key = normalize_command_lock_name(matched_name)
        blocked_guilds = locks["categories"].get(key, [])
        before = len(blocked_guilds)
        locks["categories"][key] = [
            str(guild_id) for guild_id in blocked_guilds if str(guild_id) != target_guild_id
        ]
        if not locks["categories"][key]:
            del locks["categories"][key]

        if len(locks["categories"].get(key, [])) != before:
            await self._defer_if_interaction(ctx)
            save_config(self.bot.config)
            await self._sync_slash_commands(
                target_guild_id,
                locks_were_active,
                self._locks_active(),
            )

        await create_embed_response(
            ctx,
            title="Command Lock Updated",
            description=f"Category `{matched_name}` is now enabled in server `{target_guild_id}`.",
            color=discord.Color.green(),
        )

    @command_lock.command(name="list", help="List configured command and category locks.")
    @has_command_permission()
    @app_commands.describe(guild_id="Optional server ID to filter results.")
    async def list_locks(self, ctx: commands.Context, guild_id: str = None):
        target_guild_id = str(guild_id) if guild_id else None
        locks = self._locks()
        fields = []

        for lock_type, entries in locks.items():
            lines = []
            for name, guild_ids in sorted(entries.items()):
                normalized_guilds = [str(guild_id) for guild_id in guild_ids]
                if target_guild_id and target_guild_id not in normalized_guilds:
                    continue
                lines.append(f"`{name}`: {', '.join(normalized_guilds)}")
            fields.append(
                {
                    "name": lock_type.capitalize(),
                    "value": "\n".join(lines) if lines else "No locks configured.",
                    "inline": False,
                }
            )

        await create_embed_response(
            ctx,
            title="Command Server Blacklists",
            fields=fields,
            color=discord.Color.blue(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLocksCog(bot))
