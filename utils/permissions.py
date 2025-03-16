"""
Permissions management module for Mirrobot.

This module provides functionality for checking and managing command permissions
for users and roles within Discord servers.
"""

import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from functools import wraps
import asyncio

logger = get_logger()

# System commands that only the owner can use
SYSTEM_COMMANDS = ['shutdown', 'reload_patterns', 'host']

def get_command_permissions(config):
    """
    Get command permissions from the bot configuration.
    
    Args:
        config (dict): Bot configuration dictionary
        
    Returns:
        dict: Command permissions dictionary
    """
    return config.get('command_permissions', {})

async def check_permission(ctx, command_name, command_permissions):
    """
    Check if a user has permission to execute a command.
    
    This function checks various permission criteria including:
    - Bot owner status
    - Server administrator status
    - Bot manager role
    - Command-specific role permissions
    
    Args:
        ctx (commands.Context): The command context
        command_name (str): The command name to check permissions for
        command_permissions (dict): Command permissions dictionary
        
    Returns:
        bool: True if the user has permission, False otherwise
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
        
    # Check if we're in a guild
    if not ctx.guild:
        logger.debug(f"Command '{command_name}' denied in DM for {ctx.author}")
        return False
    
    # Server admins always have permission
    if ctx.guild and (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
        return True
        
    guild_id = str(ctx.guild.id)
    if guild_id not in command_permissions:
        return False
        
    # Check bot manager roles/users
    if 'bot_managers' in command_permissions[guild_id]:
        bot_managers = command_permissions[guild_id]['bot_managers']
        
        # Check user ID
        if str(ctx.author.id) in bot_managers.get('users', []):
            logger.debug(f"Command '{command_name}' allowed for bot manager user {ctx.author} in {ctx.guild.name}")
            return True
            
        # Check role IDs
        author_role_ids = [str(role.id) for role in ctx.author.roles]
        for role_id in bot_managers.get('roles', []):
            if role_id in author_role_ids:
                logger.debug(f"Command '{command_name}' allowed for user {ctx.author} with bot manager role in {ctx.guild.name}")
                return True
    
    # Check command-specific permissions
    if command_name in command_permissions[guild_id]:
        cmd_perms = command_permissions[guild_id][command_name]
        
        # Check user ID
        if str(ctx.author.id) in cmd_perms.get('users', []):
            logger.debug(f"Command '{command_name}' allowed for permitted user {ctx.author} in {ctx.guild.name}")
            return True
            
        # Check role IDs
        author_role_ids = [str(role.id) for role in ctx.author.roles]
        for role_id in cmd_perms.get('roles', []):
            if role_id in author_role_ids:
                logger.debug(f"Command '{command_name}' allowed for user {ctx.author} with permitted role in {ctx.guild.name}")
                return True
    
    # No permission found
    if ctx.guild:
        logger.debug(f"Permission denied: {ctx.author} tried to use {command_name}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
    else:
        logger.debug(f"Permission denied: {ctx.author} tried to use {command_name} in DMs")
    return False

def has_command_permission():
    """
    Decorator to check if a user has permission to use a command.
    
    This decorator checks if the user has permission to execute a command
    based on the bot's permission settings. It's used to protect commands
    from unauthorized access.
    
    Returns:
        function: A command check that verifies permissions
    """
    async def predicate(ctx):
        """
        Predicate function that checks command permissions.
        
        Args:
            ctx (commands.Context): The command context
            
        Returns:
            bool: True if the user has permission, False otherwise
            
        Raises:
            commands.CheckFailure: If the user doesn't have permission
        """
        if not hasattr(ctx.bot, 'config'):
            # If bot config is not accessible, deny by default
            logger.error("Bot configuration not accessible for permission check")
            raise commands.CheckFailure("Bot configuration error")
            
        # Get command permissions from config
        command_permissions = get_command_permissions(ctx.bot.config)
        return await check_permission(ctx, ctx.command.name, command_permissions)
    
    return commands.check(predicate)

def command_category(category):
    """
    Decorator to assign a category to a command.
    
    This decorator assigns a category to a command, which is used for organizing
    commands in help menus and documentation.
    
    Args:
        category (str): The category name to assign
        
    Returns:
        function: A decorator that adds category metadata to commands
    """
    def decorator(func):
        """
        The actual decorator function.
        
        Args:
            func: The command function to decorate
            
        Returns:
            function: The decorated function with category metadata
        """
        # Store the category on both the function and its __func__ if it exists
        # This is needed to handle both regular functions and methods
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
