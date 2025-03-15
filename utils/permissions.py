import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from functools import wraps
import asyncio

logger = get_logger()

# System commands that only the owner can use
SYSTEM_COMMANDS = ['shutdown', 'reload_patterns', 'host']

def get_command_permissions(config):
    """Get command permissions from configuration"""
    return config.get('command_permissions', {})

async def check_permission(ctx, command_name, command_permissions):
    """
    Check if a user has permission to use a command
    Returns True if allowed, False if denied
    """
    # System commands can only be used by the bot owner
    if command_name in SYSTEM_COMMANDS:
        try:
            app_info = await ctx.bot.application_info()
            return ctx.author.id == app_info.owner.id
        except Exception as e:
            logger.error(f"Error checking owner for system command: {e}")
            return False

    # Bot owner always has permission
    try:
        app_info = await ctx.bot.application_info()
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
        logger.debug(f"Permission denied: {ctx.author} tried to use {command_name}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    else:
        logger.debug(f"Permission denied: {ctx.author} tried to use {command_name} in DMs")
    return False

def has_command_permission():
    """Decorator to check if a user has permission to use a command"""
    async def predicate(ctx):
        command_permissions = get_command_permissions(ctx.bot.config)
        return await check_permission(ctx, ctx.command.name, command_permissions)
    
    return commands.check(predicate)

def command_category(category):
    """
    Decorator to add a category to a command.
    Properly handles coroutines and command objects.
    """
    def decorator(func):
        # Set the category attribute on the function
        func.category = category
        
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
