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
import os
import json

logger = get_logger()

# System commands that only the owner can use
SYSTEM_COMMANDS = ['shutdown', 'reload_patterns', 'host']

# Dictionary to store command categories
_command_categories = {}

# File path for storing blacklists
BLACKLIST_FILE = "data/permission_blacklists.json"

# Ensure data directory exists
os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)

# Store permission blacklists
_permission_blacklists = {
    "users": {},  # Guild ID -> List of User IDs
    "roles": {}   # Guild ID -> List of Role IDs
}

def has_command_permission(*required_permissions):
    """
    Decorator to check if a user has permission to use a command.
    
    This decorator checks:
    1. If user is an admin or has manage_guild permission
    2. If user has any of the specified Discord permissions
    3. If user has command-specific role/user permissions from config
    4. If user is not in the permission blacklist
    It's used to protect commands from unauthorized access.
    
    Args:
        *required_permissions: Additional Discord permissions that should allow command usage
    
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
        
        # Get the command name
        command_name = ctx.command.name if ctx.command else None
        if not command_name:
            return False
            
        # Get the command's category
        category = None
        if hasattr(ctx.command, 'category'):
            category = ctx.command.category
            
        # Get the config and command permissions
        config = ctx.bot.config
        command_permissions = config.get('command_permissions', {})
        guild_id = str(ctx.guild.id)
        
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
        
        # Always allow administrators and people with manage_guild permission
        if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
            return True
                    
        # Check if user is blacklisted
        if guild_id in _permission_blacklists["users"]:
            if str(ctx.author.id) in _permission_blacklists["users"][guild_id]:
                return False
                
        # Check if any of user's roles are blacklisted
        if guild_id in _permission_blacklists["roles"]:
            user_roles = [str(role.id) for role in ctx.author.roles]
            for role_id in _permission_blacklists["roles"][guild_id]:
                if role_id in user_roles:
                    return False
                
        # Check server-wide permissions if any required_permissions are specified
        if len(required_permissions) > 0:
            guild_perms = ctx.author.guild_permissions
            for perm in required_permissions:
                if getattr(guild_perms, perm, False):
                    return True
        
        # Check if user has a role that has permission for all commands
        if guild_id in command_permissions and "*" in command_permissions[guild_id]:
            user_roles = [str(role.id) for role in ctx.author.roles]
            for role_id in command_permissions[guild_id]["*"]:
                if role_id in user_roles:
                    return True
        
        # Check if user has direct permission for all commands
        if (guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and 
            "*" in command_permissions[guild_id]["users"] and
            str(ctx.author.id) in command_permissions[guild_id]["users"]["*"]):
            return True
            
        # Check if user has a role that has permission for this category
        if category and guild_id in command_permissions and f"category:{category}" in command_permissions[guild_id]:
            user_roles = [str(role.id) for role in ctx.author.roles]
            for role_id in command_permissions[guild_id][f"category:{category}"]:
                if role_id in user_roles:
                    return True
        
        # Check if user has direct permission for this category
        if (category and 
            guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and 
            f"category:{category}" in command_permissions[guild_id]["users"] and
            str(ctx.author.id) in command_permissions[guild_id]["users"][f"category:{category}"]):
            return True
        
        # Check if user has a role that has permission for this command
        if guild_id in command_permissions and command_name in command_permissions[guild_id]:
            user_roles = [str(role.id) for role in ctx.author.roles]
            for role_id in command_permissions[guild_id][command_name]:
                if role_id in user_roles:
                    return True
        
        # Check if user has direct permission for this command
        if (guild_id in command_permissions and 
            "users" in command_permissions[guild_id] and 
            command_name in command_permissions[guild_id]["users"] and
            str(ctx.author.id) in command_permissions[guild_id]["users"][command_name]):
            return True
        
        # If we got here, the user doesn't have permission
        if ctx.guild:
            logger.debug(f"Permission denied: {ctx.author} tried to use {command_name}, Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        else:
            logger.debug(f"Permission denied: {ctx.author} tried to use {command_name} in DMs")
        return False
    
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
        
        if category not in _command_categories:
            _command_categories[category] = []
        _command_categories[category].append(func.__name__)
        
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

async def get_permission_target_manual(ctx, target_str):
    """
    Helper function to get a role or user from a string target.
    Returns (target_object, target_id_str, is_role)
    """
    # First try to get a role by ID or mention
    try:
        # If target is a mention or ID
        if target_str.startswith('<@&') and target_str.endswith('>'):
            role_id = int(target_str[3:-1])
        else:
            role_id = int(target_str)
        
        role = ctx.guild.get_role(role_id)
        if role:
            return role, str(role.id), True
    except ValueError:
        pass
    
    # Then try to find a role by name
    role = discord.utils.find(lambda r: r.name.lower() == target_str.lower(), ctx.guild.roles)
    if role:
        return role, str(role.id), True
    
    # If no role found, try to get a user by ID or mention
    try:
        # If target is a mention or ID
        if target_str.startswith('<@') and target_str.endswith('>'):
            # Remove <@ or <@! and >
            user_id = int(target_str.replace('<@', '').replace('!', '').replace('>', ''))
        else:
            user_id = int(target_str)
        
        user = await ctx.bot.fetch_user(user_id)
        if user:
            return user, str(user.id), False
    except (ValueError, discord.NotFound):
        pass
    
    # Try to find a user by name in the guild members
    member = discord.utils.find(lambda m: m.name.lower() == target_str.lower(), ctx.guild.members)
    if member:
        return member, str(member.id), False
    
    # No target found
    return None, None, None

def get_categories():
    """Get all registered command categories"""
    return _command_categories.keys()

def get_commands_in_category(category):
    """Get all commands in a specific category"""
    return _command_categories.get(category, [])

def add_to_blacklist(guild_id: str, target_id: str, is_role: bool):
    """
    Add a role or user to the permission blacklist for a guild.
    
    Args:
        guild_id: Guild ID string
        target_id: Role or user ID string
        is_role: True if target is a role, False if user
    """
    blacklist_type = "roles" if is_role else "users"
    if guild_id not in _permission_blacklists[blacklist_type]:
        _permission_blacklists[blacklist_type][guild_id] = []
    
    if target_id not in _permission_blacklists[blacklist_type][guild_id]:
        _permission_blacklists[blacklist_type][guild_id].append(target_id)
        # Save changes immediately
        try:
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump(_permission_blacklists, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving permission blacklists to file: {e}")
        return True
    
    return False

def remove_from_blacklist(guild_id: str, target_id: str, is_role: bool):
    """
    Remove a role or user from the permission blacklist for a guild.
    
    Args:
        guild_id: Guild ID string
        target_id: Role or user ID string
        is_role: True if target is a role, False if user
    """
    blacklist_type = "roles" if is_role else "users"
    if (guild_id in _permission_blacklists[blacklist_type] and 
        target_id in _permission_blacklists[blacklist_type][guild_id]):
        _permission_blacklists[blacklist_type][guild_id].remove(target_id)
        
        # Clean up empty lists
        if not _permission_blacklists[blacklist_type][guild_id]:
            del _permission_blacklists[blacklist_type][guild_id]
        
        # Save changes immediately
        try:
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump(_permission_blacklists, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving permission blacklists to file: {e}")
        return True
    
    return False

def get_blacklist(guild_id: str):
    """
    Get the permission blacklist for a guild.
    
    Args:
        guild_id: Guild ID string
        
    Returns:
        Dict with 'users' and 'roles' lists
    """
    return {
        "users": _permission_blacklists["users"].get(guild_id, []),
        "roles": _permission_blacklists["roles"].get(guild_id, [])
    }

# Load blacklists from config
def load_blacklists(config):
    """Load permission blacklists from disk"""
    global _permission_blacklists
    
    # Try to load from the dedicated file first
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r') as f:
                loaded_blacklists = json.load(f)
                if isinstance(loaded_blacklists, dict) and "users" in loaded_blacklists and "roles" in loaded_blacklists:
                    _permission_blacklists = loaded_blacklists
                    return
    except Exception as e:
        logger.error(f"Error loading permission blacklists from file: {e}")
    
    # Fall back to config if file doesn't exist or has issues
    if 'permission_blacklists' in config:
        _permission_blacklists = config['permission_blacklists']
        # Save to file for future use
        save_blacklists(config)
    else:
        _permission_blacklists = {
            "users": {},
            "roles": {}
        }

# Save blacklists to config
def save_blacklists(config):
    """Save permission blacklists to disk and config"""
    # Update the config
    config['permission_blacklists'] = _permission_blacklists
    
    # Save to dedicated file
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(_permission_blacklists, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving permission blacklists to file: {e}")

def check_target_permissions(target, permissions, ctx=None):
    """
    Check if the bot has the required permissions for a target (channel or thread)
    
    Args:
        target: The channel or thread to check permissions in
        permissions: List of required permissions as strings
        ctx: Optional command context for sending error messages
            
    Returns:
        tuple: (has_permissions, missing_permissions, error_message)
    """
    missing = []
    error_message = None
    
    # Handle the case where target is None
    if not target:
        error_message = "Target channel or thread not found"
        return False, ["target not found"], error_message
    
    # Get the appropriate permissions object based on target type
    if isinstance(target, discord.Thread):
        # For threads, we need the parent channel's permissions
        if not target.parent:
            error_message = f"Parent channel for thread {getattr(target, 'mention', '#unknown-thread')} not found"
            return False, ["parent channel not found"], error_message
            
        bot_member = target.guild.me
        if not bot_member:
            error_message = "Bot is not a member of this server"
            return False, ["bot not in guild"], error_message
            
        perms = target.parent.permissions_for(bot_member)
    else:
        # For channels and other Discord objects with guild property
        if not hasattr(target, "guild"):
            error_message = "Target doesn't belong to a guild"
            return False, ["invalid target"], error_message
            
        bot_member = target.guild.me
        if not bot_member:
            error_message = "Bot is not a member of this server"
            return False, ["bot not in guild"], error_message
            
        perms = target.permissions_for(bot_member)
    
    # Check each required permission
    for perm in permissions:
        if not getattr(perms, perm, False):
            missing.append(perm)
    
    has_permissions = len(missing) == 0
    
    # If context provided and permissions are missing, send error message
    if not has_permissions and missing:
        missing_formatted = ", ".join([f"`{perm.replace('_', ' ').title()}`" for perm in missing])
        target_mention = getattr(target, 'mention', 'this channel/thread')
        error_message = f"I don't have sufficient permissions in {target_mention}. Missing: {missing_formatted}"
        if ctx:
            asyncio.create_task(ctx.send(error_message, delete_after=15))
    
    return has_permissions, missing, error_message
