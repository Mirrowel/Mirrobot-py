import datetime
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

from utils.embed_helper import create_embed_response
from utils.logging_setup import get_logger
from utils.permissions import (
    command_category,
    has_command_permission,
    is_command_available_in_guild,
)

logger = get_logger()

ROLE_SHARING_FILE = "data/role_sharing.json"


class RoleSharingCog(commands.Cog, name="Role Sharing"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        os.makedirs(os.path.dirname(ROLE_SHARING_FILE), exist_ok=True)
        self.data = self._load_data()

    def _load_data(self):
        try:
            if os.path.exists(ROLE_SHARING_FILE):
                with open(ROLE_SHARING_FILE, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                    if isinstance(loaded, dict):
                        loaded.setdefault("guilds", {})
                        return loaded
        except Exception as e:
            logger.error(f"Error loading role sharing data: {e}", exc_info=True)
        return {"guilds": {}}

    def _save_data(self):
        try:
            with open(ROLE_SHARING_FILE, "w", encoding="utf-8") as file:
                json.dump(self.data, file, indent=4)
            return True
        except Exception as e:
            logger.error(f"Error saving role sharing data: {e}", exc_info=True)
            return False

    def _guild_data(self, guild_id: int):
        guild_id = str(guild_id)
        guild_data = self.data.setdefault("guilds", {}).setdefault(guild_id, {})
        guild_data.setdefault("log_channel_id", None)
        guild_data.setdefault("rules", {})
        guild_data.setdefault("assignments", {})
        return guild_data

    async def _ensure_available(self, ctx: commands.Context):
        if not ctx.guild:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="This command can only be used in a server.",
                color=discord.Color.red(),
            )
            return False
        if not is_command_available_in_guild(ctx.command, ctx.guild.id, self.bot.config):
            await create_embed_response(
                ctx,
                title="Role Sharing Locked",
                description="This command is not available in this server.",
                color=discord.Color.red(),
            )
            return False
        return True

    async def _send_help(self, ctx: commands.Context):
        if not await self._ensure_available(ctx):
            return
        embed = discord.Embed(
            title="Role Sharing Help",
            description="Configure role delegation and let allowed roles share configured roles with other users.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Sharing",
            value=(
                "`!role_share give <member> <role> [reason]`\n"
                "`!role_share rules`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Management",
            value=(
                "`!role_share allow <applier_role> <target_role>`\n"
                "`!role_share disallow <applier_role> <target_role>`\n"
                "`!role_share revoke <member> <role> [reason]`\n"
                "`!role_share lookup <member> [role]`\n"
                "`!role_share log_channel <channel>`"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    def _can_author_share_role(self, author: discord.Member, role: discord.Role):
        guild_data = self._guild_data(author.guild.id)
        allowed_applier_roles = guild_data["rules"].get(str(role.id), [])
        author_roles = {str(role.id) for role in author.roles}
        return bool(author_roles.intersection({str(role_id) for role_id in allowed_applier_roles}))

    def _share_rule_status(self, author: discord.Member, role: discord.Role):
        guild_data = self._guild_data(author.guild.id)
        allowed_role_ids = [str(role_id) for role_id in guild_data["rules"].get(str(role.id), [])]
        author_role_ids = {str(author_role.id) for author_role in author.roles}
        matching_role_ids = [role_id for role_id in allowed_role_ids if role_id in author_role_ids]
        return {
            "configured": bool(allowed_role_ids),
            "allowed": bool(matching_role_ids),
            "allowed_role_ids": allowed_role_ids,
            "matching_role_ids": matching_role_ids,
        }

    def _format_role_list(self, guild: discord.Guild, role_ids):
        names = []
        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            names.append(role.mention if role else f"Unknown Role ({role_id})")
        return ", ".join(names) if names else "None"

    def _author_has_role(self, author: discord.Member, role: discord.Role):
        return any(author_role.id == role.id for author_role in author.roles)

    async def _is_privileged_revoker(self, ctx: commands.Context):
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        try:
            if self.bot.app_info is None:
                async with self.bot.app_info_lock:
                    if self.bot.app_info is None:
                        self.bot.app_info = await self.bot.application_info()
            if self.bot.app_info and ctx.author.id == self.bot.app_info.owner.id:
                return True
        except Exception as e:
            logger.error(f"Failed to check bot owner for role share revoke: {e}", exc_info=True)

        permissions = ctx.author.guild_permissions
        return permissions.administrator or permissions.manage_guild

    async def _send_share_log(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        reason: str,
        assigned_at: str,
    ):
        guild_data = self._guild_data(ctx.guild.id)
        channel_id = guild_data.get("log_channel_id")
        if not channel_id:
            return False

        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            return False

        embed = discord.Embed(
            title="Role Shared",
            color=discord.Color.green(),
            timestamp=datetime.datetime.fromisoformat(assigned_at),
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Recipient", value=member.mention, inline=True)
        embed.add_field(name="Shared By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        embed.set_footer(text=f"Guild ID: {ctx.guild.id}")

        try:
            await channel.send(embed=embed)
            return True
        except Exception as e:
            logger.error(f"Failed to send role sharing log to channel {channel_id}: {e}", exc_info=True)
            return False

    async def _send_revoke_log(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        reason: str,
        revoked_at: str,
        assignment: dict,
    ):
        guild_data = self._guild_data(ctx.guild.id)
        channel_id = guild_data.get("log_channel_id")
        if not channel_id:
            return False

        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            return False

        assigned_by_id = assignment.get("assigned_by")
        assigned_by = ctx.guild.get_member(int(assigned_by_id)) if assigned_by_id else None
        assigned_by_text = assigned_by.mention if assigned_by else f"Unknown User ({assigned_by_id})"

        embed = discord.Embed(
            title="Shared Role Revoked",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.fromisoformat(revoked_at),
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Recipient", value=member.mention, inline=True)
        embed.add_field(name="Revoked By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Originally Shared By", value=assigned_by_text, inline=True)
        embed.add_field(name="Revoke Reason", value=reason or "No reason provided.", inline=False)
        embed.set_footer(text=f"Guild ID: {ctx.guild.id}")

        try:
            await channel.send(embed=embed)
            return True
        except Exception as e:
            logger.error(f"Failed to send role sharing revoke log to channel {channel_id}: {e}", exc_info=True)
            return False

    async def _send_rule_log(
        self,
        ctx: commands.Context,
        action: str,
        applier_role: discord.Role,
        target_role: discord.Role,
    ):
        guild_data = self._guild_data(ctx.guild.id)
        channel_id = guild_data.get("log_channel_id")
        if not channel_id:
            return False

        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            return False

        is_added = action == "added"
        embed = discord.Embed(
            title=f"Role Sharing Rule {'Added' if is_added else 'Removed'}",
            color=discord.Color.green() if is_added else discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Sharer Role", value=applier_role.mention, inline=True)
        embed.add_field(name="Shareable Role", value=target_role.mention, inline=True)
        embed.add_field(name="Changed By", value=ctx.author.mention, inline=True)
        embed.set_footer(text=f"Guild ID: {ctx.guild.id}")

        try:
            await channel.send(embed=embed)
            return True
        except Exception as e:
            logger.error(f"Failed to send role sharing rule log to channel {channel_id}: {e}", exc_info=True)
            return False

    @commands.hybrid_group(
        name="role_share",
        help="Share configured roles with other users and manage role sharing rules.",
    )
    @command_category("Role Sharing")
    async def role_share(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_help(ctx)

    @role_share.command(name="give", help="Share a configured role with another user.")
    @app_commands.describe(
        member="The member receiving the role.",
        role="The configured role to share.",
        reason="Optional reason for the audit log.",
    )
    async def give(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        reason: str = None,
    ):
        if not await self._ensure_available(ctx):
            return
        if member.id == ctx.author.id:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="You can only share roles with other users.",
                color=discord.Color.red(),
            )
            return
        if role == ctx.guild.default_role or role.managed:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="That role cannot be shared by the bot.",
                color=discord.Color.red(),
            )
            return
        if role in member.roles:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description=f"{member.mention} already has {role.mention}.",
                color=discord.Color.red(),
            )
            return
        rule_status = self._share_rule_status(ctx.author, role)
        if not rule_status["configured"]:
            await create_embed_response(
                ctx,
                title="Role Sharing Denied",
                description=f"{role.mention} is not configured as a shareable role yet.",
                color=discord.Color.red(),
            )
            return
        if not rule_status["allowed"]:
            await create_embed_response(
                ctx,
                title="Role Sharing Denied",
                description=(
                    f"You cannot share {role.mention}. Allowed sharer roles: "
                    f"{self._format_role_list(ctx.guild, rule_status['allowed_role_ids'])}."
                ),
                color=discord.Color.red(),
            )
            return

        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_roles:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="I need the Manage Roles permission to share roles.",
                color=discord.Color.red(),
            )
            return
        if bot_member.top_role <= role:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description=f"My highest role must be above {role.mention}.",
                color=discord.Color.red(),
            )
            return

        assigned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await member.add_roles(role, reason=f"Role shared by {ctx.author} ({ctx.author.id}): {reason or 'No reason provided'}")

        guild_data = self._guild_data(ctx.guild.id)
        user_assignments = guild_data["assignments"].setdefault(str(member.id), {})
        user_assignments[str(role.id)] = {
            "assigned_by": str(ctx.author.id),
            "assigned_at": assigned_at,
            "reason": reason or "",
            "active": True,
        }
        self._save_data()

        logger.info(
            f"Role shared in {ctx.guild.name} ({ctx.guild.id}): {ctx.author} ({ctx.author.id}) "
            f"gave {role.name} ({role.id}) to {member} ({member.id}). Reason: {reason or 'No reason provided'}"
        )
        sent_log = await self._send_share_log(ctx, member, role, reason, assigned_at)
        log_note = "" if sent_log else "\nNo role sharing log channel is configured or reachable."

        await create_embed_response(
            ctx,
            title="Role Shared",
            description=f"Shared {role.mention} with {member.mention}.{log_note}",
            color=discord.Color.green(),
        )

    @role_share.command(name="allow", help="Allow one role to share another role.")
    @has_command_permission()
    @app_commands.describe(
        applier_role="Role whose members can share the target role.",
        target_role="Role that can be shared.",
    )
    async def allow(
        self,
        ctx: commands.Context,
        applier_role: discord.Role,
        target_role: discord.Role,
    ):
        if not ctx.guild:
            return
        if target_role == ctx.guild.default_role or target_role.managed:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="That target role cannot be shared by the bot.",
                color=discord.Color.red(),
            )
            return
        if not self._author_has_role(ctx.author, target_role):
            await create_embed_response(
                ctx,
                title="Role Sharing Denied",
                description=f"You must have {target_role.mention} to configure sharing for it.",
                color=discord.Color.red(),
            )
            return

        guild_data = self._guild_data(ctx.guild.id)
        allowed_roles = guild_data["rules"].setdefault(str(target_role.id), [])
        changed = False
        if str(applier_role.id) not in allowed_roles:
            allowed_roles.append(str(applier_role.id))
            self._save_data()
            changed = True

        if changed:
            logger.info(
                f"Role sharing rule added in {ctx.guild.name} ({ctx.guild.id}): {ctx.author} ({ctx.author.id}) "
                f"allowed {applier_role.name} ({applier_role.id}) to share {target_role.name} ({target_role.id})."
            )
            sent_log = await self._send_rule_log(ctx, "added", applier_role, target_role)
            log_note = "" if sent_log else "\nNo role sharing log channel is configured or reachable."
        else:
            log_note = "\nThat rule already existed."

        await create_embed_response(
            ctx,
            title="Role Sharing Rule Added",
            description=f"Members with {applier_role.mention} can now share {target_role.mention}.{log_note}",
            color=discord.Color.green(),
        )

    @role_share.command(name="disallow", help="Remove a role sharing rule.")
    @has_command_permission()
    @app_commands.describe(
        applier_role="Role to remove from the target role's allowed sharers.",
        target_role="Shared role to update.",
    )
    async def disallow(
        self,
        ctx: commands.Context,
        applier_role: discord.Role,
        target_role: discord.Role,
    ):
        if not ctx.guild:
            return
        if not self._author_has_role(ctx.author, target_role):
            await create_embed_response(
                ctx,
                title="Role Sharing Denied",
                description=f"You must have {target_role.mention} to configure sharing for it.",
                color=discord.Color.red(),
            )
            return
        guild_data = self._guild_data(ctx.guild.id)
        allowed_roles = guild_data["rules"].get(str(target_role.id), [])
        changed = False
        if str(applier_role.id) in allowed_roles:
            allowed_roles.remove(str(applier_role.id))
            if allowed_roles:
                guild_data["rules"][str(target_role.id)] = allowed_roles
            else:
                guild_data["rules"].pop(str(target_role.id), None)
            self._save_data()
            changed = True

        if changed:
            logger.info(
                f"Role sharing rule removed in {ctx.guild.name} ({ctx.guild.id}): {ctx.author} ({ctx.author.id}) "
                f"removed {applier_role.name} ({applier_role.id}) from sharing {target_role.name} ({target_role.id})."
            )
            sent_log = await self._send_rule_log(ctx, "removed", applier_role, target_role)
            log_note = "" if sent_log else "\nNo role sharing log channel is configured or reachable."
        else:
            log_note = "\nThat rule was not configured."

        await create_embed_response(
            ctx,
            title="Role Sharing Rule Removed",
            description=f"{applier_role.mention} can no longer share {target_role.mention}.{log_note}",
            color=discord.Color.green(),
        )

    @role_share.command(name="revoke", help="Revoke a role that was shared through this command.")
    @app_commands.describe(
        member="The member whose shared role should be removed.",
        role="The role to revoke.",
        reason="Optional reason for the audit log.",
    )
    async def revoke(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        reason: str = None,
    ):
        if not await self._ensure_available(ctx):
            return
        guild_data = self._guild_data(ctx.guild.id)
        assignment = guild_data["assignments"].get(str(member.id), {}).get(str(role.id))
        if not assignment or not assignment.get("active", True):
            await create_embed_response(
                ctx,
                title="Role Sharing Revoke Denied",
                description=f"No active bot-recorded share of {role.mention} to {member.mention} was found.",
                color=discord.Color.red(),
            )
            return

        assigned_by = assignment.get("assigned_by")
        privileged = await self._is_privileged_revoker(ctx)
        if str(ctx.author.id) != str(assigned_by) and not privileged:
            await create_embed_response(
                ctx,
                title="Role Sharing Revoke Denied",
                description="Only the original giver, the server owner, server admins/manage-server users, or the bot owner can revoke this shared role.",
                color=discord.Color.red(),
            )
            return

        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_roles:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description="I need the Manage Roles permission to revoke shared roles.",
                color=discord.Color.red(),
            )
            return
        if bot_member.top_role <= role:
            await create_embed_response(
                ctx,
                title="Role Sharing Error",
                description=f"My highest role must be above {role.mention}.",
                color=discord.Color.red(),
            )
            return
        if role not in member.roles:
            await create_embed_response(
                ctx,
                title="Role Sharing Revoke Notice",
                description=f"{member.mention} no longer has {role.mention}. I marked the recorded share as revoked.",
                color=discord.Color.orange(),
            )
        else:
            await member.remove_roles(role, reason=f"Shared role revoked by {ctx.author} ({ctx.author.id}): {reason or 'No reason provided'}")

        revoked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        assignment["active"] = False
        assignment["revoked_by"] = str(ctx.author.id)
        assignment["revoked_at"] = revoked_at
        assignment["revoked_reason"] = reason or ""
        self._save_data()

        logger.info(
            f"Shared role revoked in {ctx.guild.name} ({ctx.guild.id}): {ctx.author} ({ctx.author.id}) "
            f"revoked {role.name} ({role.id}) from {member} ({member.id}). Reason: {reason or 'No reason provided'}"
        )
        sent_log = await self._send_revoke_log(ctx, member, role, reason, revoked_at, assignment)
        log_note = "" if sent_log else "\nNo role sharing log channel is configured or reachable."

        await create_embed_response(
            ctx,
            title="Shared Role Revoked",
            description=f"Revoked {role.mention} from {member.mention}.{log_note}",
            color=discord.Color.green(),
        )

    @role_share.command(name="rules", help="List configured role sharing rules.")
    async def rules(self, ctx: commands.Context):
        if not await self._ensure_available(ctx):
            return
        guild_data = self._guild_data(ctx.guild.id)
        lines = []
        for target_role_id, applier_role_ids in sorted(guild_data["rules"].items()):
            target_role = ctx.guild.get_role(int(target_role_id))
            target_name = target_role.mention if target_role else f"Unknown Role ({target_role_id})"
            applier_names = []
            for applier_role_id in applier_role_ids:
                applier_role = ctx.guild.get_role(int(applier_role_id))
                applier_names.append(applier_role.mention if applier_role else f"Unknown Role ({applier_role_id})")
            lines.append(f"{target_name}: {', '.join(applier_names)}")

        await create_embed_response(
            ctx,
            title="Role Sharing Rules",
            description="\n".join(lines) if lines else "No role sharing rules are configured.",
            color=discord.Color.blue(),
        )

    def _active_assignments(self, guild_data):
        for recipient_id, roles in guild_data["assignments"].items():
            for role_id, record in roles.items():
                if record.get("active", True):
                    yield recipient_id, role_id, record

    @role_share.command(name="lookup", help="Show role shares recorded for a member or role.")
    @has_command_permission()
    @app_commands.describe(
        member="Optional member to look up.",
        role="Optional role to look up.",
    )
    async def lookup(
        self,
        ctx: commands.Context,
        member: discord.Member = None,
        role: discord.Role = None,
    ):
        if not ctx.guild:
            return
        if bool(member) == bool(role):
            await create_embed_response(
                ctx,
                title="Role Sharing Lookup Error",
                description="Provide exactly one lookup target: either a member or a role.",
                color=discord.Color.red(),
            )
            return

        guild_data = self._guild_data(ctx.guild.id)

        if role:
            lines = []
            for recipient_id, role_id, record in self._active_assignments(guild_data):
                if str(role.id) != str(role_id):
                    continue
                recipient = ctx.guild.get_member(int(recipient_id))
                recipient_text = recipient.mention if recipient else f"Unknown User ({recipient_id})"
                giver_id = record.get("assigned_by")
                giver = ctx.guild.get_member(int(giver_id)) if giver_id else None
                giver_text = giver.mention if giver else f"Unknown User ({giver_id})"
                lines.append(f"{recipient_text} <- {giver_text}")

            await create_embed_response(
                ctx,
                title=f"Role Sharing Lookup: {role.name}",
                description="\n".join(lines) if lines else f"No active bot-recorded shares found for {role.mention}.",
                color=discord.Color.blue(),
            )
            return

        received_lines = []
        received_assignments = guild_data["assignments"].get(str(member.id), {})
        for role_id, record in sorted(received_assignments.items()):
            if not record.get("active", True):
                continue
            assigned_role = ctx.guild.get_role(int(role_id))
            role_name = assigned_role.mention if assigned_role else f"Unknown Role ({role_id})"
            assigned_by_id = record.get("assigned_by")
            assigned_by = ctx.guild.get_member(int(assigned_by_id)) if assigned_by_id else None
            assigned_by_text = assigned_by.mention if assigned_by else f"Unknown User ({assigned_by_id})"
            reason = record.get("reason") or "No reason provided."
            received_lines.append(
                f"{role_name} by {assigned_by_text} at `{record.get('assigned_at', 'unknown')}`\nReason: {reason}"
            )

        given_lines = []
        for recipient_id, role_id, record in self._active_assignments(guild_data):
            if str(record.get("assigned_by")) != str(member.id):
                continue
            assigned_role = ctx.guild.get_role(int(role_id))
            role_name = assigned_role.mention if assigned_role else f"Unknown Role ({role_id})"
            recipient = ctx.guild.get_member(int(recipient_id))
            recipient_text = recipient.mention if recipient else f"Unknown User ({recipient_id})"
            given_lines.append(f"{role_name} to {recipient_text} at `{record.get('assigned_at', 'unknown')}`")

        fields = [
            {
                "name": "Received Through Role Share",
                "value": "\n\n".join(received_lines) if received_lines else "No active bot-recorded received roles.",
                "inline": False,
            },
            {
                "name": "Given Through Role Share",
                "value": "\n".join(given_lines) if given_lines else "No active bot-recorded given roles.",
                "inline": False,
            },
        ]

        await create_embed_response(
            ctx,
            title=f"Role Sharing Lookup: {member}",
            fields=fields,
            color=discord.Color.blue(),
        )

    @role_share.command(name="log_channel", help="Set the channel used for role sharing audit logs.")
    @has_command_permission()
    @app_commands.describe(channel="Channel that receives role sharing audit logs.")
    async def log_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        if not ctx.guild:
            return
        if channel.guild.id != ctx.guild.id:
            await create_embed_response(
                ctx,
                title="Role Sharing Log Channel Error",
                description="The log channel must be in this server.",
                color=discord.Color.red(),
            )
            return

        bot_member = ctx.guild.me
        if not bot_member:
            await create_embed_response(
                ctx,
                title="Role Sharing Log Channel Error",
                description="I could not verify my server membership for that channel.",
                color=discord.Color.red(),
            )
            return

        permissions = channel.permissions_for(bot_member)
        missing_permissions = []
        if not permissions.view_channel:
            missing_permissions.append("View Channel")
        if not permissions.send_messages:
            missing_permissions.append("Send Messages")
        if not permissions.embed_links:
            missing_permissions.append("Embed Links")

        if missing_permissions:
            await create_embed_response(
                ctx,
                title="Role Sharing Log Channel Error",
                description=(
                    f"I cannot use {channel.mention} as the role sharing log channel. "
                    f"Missing permissions: {', '.join(f'`{permission}`' for permission in missing_permissions)}."
                ),
                color=discord.Color.red(),
            )
            return

        guild_data = self._guild_data(ctx.guild.id)
        guild_data["log_channel_id"] = str(channel.id)
        self._save_data()

        await create_embed_response(
            ctx,
            title="Role Sharing Log Channel Updated",
            description=f"Role sharing logs will be sent to {channel.mention}.",
            color=discord.Color.green(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleSharingCog(bot))
