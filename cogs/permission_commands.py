import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from config.config_manager import save_config
from utils.permissions import (
    has_command_permission, command_category, get_permission_target,
    get_categories, get_commands_in_category, add_to_blacklist, 
    remove_from_blacklist, get_blacklist, load_blacklists, save_blacklists
)

logger = get_logger()

class PermissionCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load blacklists from config
        load_blacklists(bot.config)

    @commands.command(name='add_command_role', help='Give a role or user permission to use a specific bot command.\nArguments: target (mention or ID) - The role/user to grant permission to\n           command_name (str) - The name of the command\nExample: !add_command_role @Moderators add_ocr_read_channel or !add_command_role @username add_ocr_read_channel')
    @has_command_permission()
    @command_category("Permissions")
    async def add_command_role(self, ctx, target, command_name: str):
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
        
        # Verify the command exists
        if command_name not in [cmd.name for cmd in self.bot.commands]:
            response = f'Command {command_name} does not exist'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        
        # Initialize the command_permissions structure as needed
        if guild_id not in command_permissions:
            command_permissions[guild_id] = {}
        
        if is_role:
            # Handle role permissions
            if command_name not in command_permissions[guild_id]:
                command_permissions[guild_id][command_name] = []
                
            # Check if the role ID already exists for this command
            if target_id_str in command_permissions[guild_id][command_name]:
                response = f'Role {target_obj.name} already has permission to use the {command_name} command.'
            else:
                # Add the role ID to the command's permissions
                command_permissions[guild_id][command_name].append(target_id_str)
                response = f'Role {target_obj.name} added to permissions for the {command_name} command.'
        else:
            # Handle user permissions
            if "users" not in command_permissions[guild_id]:
                command_permissions[guild_id]["users"] = {}
                
            if command_name not in command_permissions[guild_id]["users"]:
                command_permissions[guild_id]["users"][command_name] = []
                
            # Check if the user ID already exists for this command
            if target_id_str in command_permissions[guild_id]["users"][command_name]:
                response = f'User {target_obj.name} already has permission to use the {command_name} command.'
            else:
                # Add the user ID to the command's permissions
                command_permissions[guild_id]["users"][command_name].append(target_id_str)
                response = f'User {target_obj.name} added to permissions for the {command_name} command.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='add_bot_manager', help='Add a role or user as a bot manager with access to all non-system commands.\nArguments: target (mention or ID) - The role/user to designate as bot manager\nExample: !add_bot_manager @Admins or !add_bot_manager @username')
    @has_command_permission()
    @command_category("Permissions")
    async def add_bot_manager(self, ctx, target):
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
        
        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        
        # Initialize the command_permissions structure as needed
        if guild_id not in command_permissions:
            command_permissions[guild_id] = {}
        
        if is_role:
            # Handle role manager permissions
            if "*" not in command_permissions[guild_id]:
                command_permissions[guild_id]["*"] = []
                
            # Check if the role ID already exists for manager role
            if target_id_str in command_permissions[guild_id]["*"]:
                response = f'Role {target_obj.name} is already a bot manager with access to all commands.'
            else:
                # Add the role ID to the manager list
                command_permissions[guild_id]["*"].append(target_id_str)
                response = f'Role {target_obj.name} has been added as a bot manager with access to all non-system commands.'
        else:
            # Handle user manager permissions
            if "users" not in command_permissions[guild_id]:
                command_permissions[guild_id]["users"] = {}
                
            if "*" not in command_permissions[guild_id]["users"]:
                command_permissions[guild_id]["users"]["*"] = []
                
            # Check if the user ID already exists for manager
            if target_id_str in command_permissions[guild_id]["users"]["*"]:
                response = f'User {target_obj.name} is already a bot manager with access to all commands.'
            else:
                # Add the user ID to the manager list
                command_permissions[guild_id]["users"]["*"].append(target_id_str)
                response = f'User {target_obj.name} has been added as a bot manager with access to all non-system commands.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_command_role', help='Remove a role or user\'s permission to use a specific bot command.\nArguments: target (mention or ID) - The role/user to remove permission from\n           command_name (str) - The name of the command\nExample: !remove_command_role @Moderators add_ocr_read_channel or !remove_command_role @username add_ocr_read_channel')
    @has_command_permission()
    @command_category("Permissions")
    async def remove_command_role(self, ctx, target, command_name: str):
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
        
        # Verify the command exists
        if command_name not in [cmd.name for cmd in self.bot.commands]:
            response = f'Command {command_name} does not exist'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return

        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        
        if is_role:
            # Check if the role has any permissions for this command
            if (guild_id in command_permissions and 
                command_name in command_permissions[guild_id] and 
                target_id_str in command_permissions[guild_id][command_name]):
                
                # Remove the role ID from the command's permissions
                command_permissions[guild_id][command_name].remove(target_id_str)
                
                # If there are no more roles for this command, remove the command entry
                if not command_permissions[guild_id][command_name]:
                    del command_permissions[guild_id][command_name]
                
                response = f'Role {target_obj.name} no longer has specific permission to use the {command_name} command.'
            else:
                response = f'Role {target_obj.name} does not have specific permission for the {command_name} command.'
        else:
            # Check if the user has any permissions for this command
            if (guild_id in command_permissions and 
                "users" in command_permissions[guild_id] and
                command_name in command_permissions[guild_id]["users"] and 
                target_id_str in command_permissions[guild_id]["users"][command_name]):
                
                # Remove the user ID from the command's permissions
                command_permissions[guild_id]["users"][command_name].remove(target_id_str)
                
                # If there are no more users for this command, remove the command entry
                if not command_permissions[guild_id]["users"][command_name]:
                    del command_permissions[guild_id]["users"][command_name]
                    
                    # If the users dict is empty, remove it
                    if not command_permissions[guild_id]["users"]:
                        del command_permissions[guild_id]["users"]
                
                response = f'User {target_obj.name} no longer has specific permission to use the {command_name} command.'
            else:
                response = f'User {target_obj.name} does not have specific permission for the {command_name} command.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_bot_manager', help='Remove a role or user from bot managers, revoking access to all commands.\nArguments: target (mention or ID) - The role/user to remove from manager status\nExample: !remove_bot_manager @Admins or !remove_bot_manager @username')
    @has_command_permission()
    @command_category("Permissions")
    async def remove_bot_manager(self, ctx, target):
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
        
        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        
        if is_role:
            # Check if the role is a bot manager
            if (guild_id in command_permissions and 
                "*" in command_permissions[guild_id] and 
                target_id_str in command_permissions[guild_id]["*"]):
                
                # Remove the role ID from the manager list
                command_permissions[guild_id]["*"].remove(target_id_str)
                
                # If there are no more manager roles, remove the entry
                if not command_permissions[guild_id]["*"]:
                    del command_permissions[guild_id]["*"]
                
                response = f'Role {target_obj.name} has been removed from bot managers and no longer has access to all commands.'
            else:
                response = f'Role {target_obj.name} is not a bot manager.'
        else:
            # Check if the user is a bot manager
            if (guild_id in command_permissions and 
                "users" in command_permissions[guild_id] and
                "*" in command_permissions[guild_id]["users"] and 
                target_id_str in command_permissions[guild_id]["users"]["*"]):
                
                # Remove the user ID from the manager list
                command_permissions[guild_id]["users"]["*"].remove(target_id_str)
                
                # If there are no more manager users, remove the entry
                if not command_permissions[guild_id]["users"]["*"]:
                    del command_permissions[guild_id]["users"]["*"]
                    
                    # If the users dict is empty, remove it
                    if not command_permissions[guild_id]["users"]:
                        del command_permissions[guild_id]["users"]
                
                response = f'User {target_obj.name} has been removed from bot managers and no longer has access to all commands.'
            else:
                response = f'User {target_obj.name} is not a bot manager.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='add_category_permission', help='Give a role or user permission to use all commands in a category.\nArguments: target (mention or ID) - The role/user to grant permission to\n           category (str) - The category name\nExample: !add_category_permission @Moderators Moderation')
    @has_command_permission()
    @command_category("Permissions")
    async def add_category_permission(self, ctx, target, category: str):
        """Add permission for all commands in a category"""
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Verify the category exists
        categories = list(get_categories())
        found_category = None
        for cat in categories:
            if cat.lower() == category.lower():
                found_category = cat
                break
                
        if not found_category:
            await ctx.reply(f"Category '{category}' does not exist. Available categories: {', '.join(categories)}")
            return
            
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
            
        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        
        # Initialize the command_permissions structure as needed
        if guild_id not in command_permissions:
            command_permissions[guild_id] = {}
        
        category_key = f"category:{found_category}"
        
        if is_role:
            # Handle role category permissions
            if category_key not in command_permissions[guild_id]:
                command_permissions[guild_id][category_key] = []
                
            # Check if the role ID already exists for this category
            if target_id_str in command_permissions[guild_id][category_key]:
                response = f'Role {target_obj.name} already has permission for all {found_category} commands.'
            else:
                # Add the role ID to the category's permissions
                command_permissions[guild_id][category_key].append(target_id_str)
                response = f'Role {target_obj.name} granted permission for all {found_category} commands.'
        else:
            # Handle user category permissions
            if "users" not in command_permissions[guild_id]:
                command_permissions[guild_id]["users"] = {}
                
            if category_key not in command_permissions[guild_id]["users"]:
                command_permissions[guild_id]["users"][category_key] = []
                
            # Check if the user ID already exists for this category
            if target_id_str in command_permissions[guild_id]["users"][category_key]:
                response = f'User {target_obj.name} already has permission for all {found_category} commands.'
            else:
                # Add the user ID to the category's permissions
                command_permissions[guild_id]["users"][category_key].append(target_id_str)
                response = f'User {target_obj.name} granted permission for all {found_category} commands.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_category_permission', help='Remove a role or user\'s permission to use all commands in a category.\nArguments: target (mention or ID) - The role/user to remove permission from\n           category (str) - The category name\nExample: !remove_category_permission @Moderators Moderation')
    @has_command_permission()
    @command_category("Permissions")
    async def remove_category_permission(self, ctx, target, category: str):
        """Remove permission for all commands in a category"""
        config = self.bot.config
        command_permissions = config.get('command_permissions', {})
        
        # Verify the category exists
        categories = list(get_categories())
        found_category = None
        for cat in categories:
            if cat.lower() == category.lower():
                found_category = cat
                break
                
        if not found_category:
            await ctx.reply(f"Category '{category}' does not exist. Available categories: {', '.join(categories)}")
            return
            
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
            
        guild_id = str(ctx.guild.id)  # Ensure guild_id is a string for JSON keys
        category_key = f"category:{found_category}"
        
        if is_role:
            # Handle role category permissions
            if (guild_id in command_permissions and 
                category_key in command_permissions[guild_id] and 
                target_id_str in command_permissions[guild_id][category_key]):
                
                command_permissions[guild_id][category_key].remove(target_id_str)
                
                # If there are no more roles for this category, remove the category entry
                if not command_permissions[guild_id][category_key]:
                    del command_permissions[guild_id][category_key]
                
                response = f'Role {target_obj.name} no longer has permission for all {found_category} commands.'
            else:
                response = f'Role {target_obj.name} does not have category-wide permission for {found_category} commands.'
        else:
            # Handle user category permissions
            if (guild_id in command_permissions and 
                "users" in command_permissions[guild_id] and
                category_key in command_permissions[guild_id]["users"] and 
                target_id_str in command_permissions[guild_id]["users"][category_key]):
                
                command_permissions[guild_id]["users"][category_key].remove(target_id_str)
                
                # If there are no more users for this category, remove the category entry
                if not command_permissions[guild_id]["users"][category_key]:
                    del command_permissions[guild_id]["users"][category_key]
                
                response = f'User {target_obj.name} no longer has permission for all {found_category} commands.'
            else:
                response = f'User {target_obj.name} does not have category-wide permission for {found_category} commands.'
        
        # Save the updated configuration
        config['command_permissions'] = command_permissions
        save_config(config)
        
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='add_to_blacklist', help='Add a role or user to the permission blacklist to prevent them from using any commands.\nArguments: target (mention or ID) - The role/user to blacklist\nExample: !add_to_blacklist @Troublemaker')
    @has_command_permission()
    @command_category("Permissions")
    async def add_to_blacklist_command(self, ctx, target):
        """Add a role or user to the command permission blacklist"""
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
            
        # Prevent blacklisting server administrators
        if not is_role and target_obj.guild_permissions.administrator:
            await ctx.reply(f"Cannot blacklist {target_obj.name} as they have administrator privileges.")
            return
            
        if is_role and target_obj.permissions.administrator:
            await ctx.reply(f"Cannot blacklist the {target_obj.name} role as it has administrator privileges.")
            return
            
        guild_id = str(ctx.guild.id)
        
        # Add to blacklist
        if add_to_blacklist(guild_id, target_id_str, is_role):
            target_type = "Role" if is_role else "User"
            response = f'{target_type} {target_obj.name} added to the command permission blacklist.'
        else:
            target_type = "Role" if is_role else "User"
            response = f'{target_type} {target_obj.name} is already in the command permission blacklist.'
            
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='remove_from_blacklist', help='Remove a role or user from the permission blacklist.\nArguments: target (mention or ID) - The role/user to remove from blacklist\nExample: !remove_from_blacklist @Troublemaker')
    @has_command_permission()
    @command_category("Permissions")
    async def remove_from_blacklist_command(self, ctx, target):
        """Remove a role or user from the command permission blacklist"""
        # Get the target (either role or user)
        target_obj, target_id_str, is_role = await get_permission_target(ctx, target)
        
        # Check if target is valid
        if not target_obj:
            response = f'Could not find role or user "{target}"'
            logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.debug(f"Response: {response}")
            await ctx.reply(response)
            return
            
        guild_id = str(ctx.guild.id)
        
        # Remove from blacklist
        if remove_from_blacklist(guild_id, target_id_str, is_role):
            target_type = "Role" if is_role else "User"
            response = f'{target_type} {target_obj.name} removed from the command permission blacklist.'
        else:
            target_type = "Role" if is_role else "User"
            response = f'{target_type} {target_obj.name} is not in the command permission blacklist.'
            
        logger.debug(f"Server: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
        logger.debug(f"Response: {response}")
        await ctx.reply(response)

    @commands.command(name='list_blacklist', help='List all roles and users in the command permission blacklist.\nNo arguments required.\nExample: !list_blacklist')
    @has_command_permission()
    @command_category("Permissions")
    async def list_blacklist(self, ctx):
        """List all roles and users in the command permission blacklist"""
        guild_id = str(ctx.guild.id)
        blacklist = get_blacklist(guild_id)
        
        if not blacklist["users"] and not blacklist["roles"]:
            await ctx.reply("No roles or users are blacklisted in this server.")
            return
            
        # Build response message
        response = "**🚫 Permission Blacklist**\n\n"
        
        # Add blacklisted roles
        if blacklist["roles"]:
            response += "**Blacklisted Roles:**\n"
            for role_id in blacklist["roles"]:
                role = ctx.guild.get_role(int(role_id))
                role_name = role.name if role else f"Unknown Role (ID: {role_id})"
                response += f"• {role_name}\n"
            response += "\n"
            
        # Add blacklisted users
        if blacklist["users"]:
            response += "**Blacklisted Users:**\n"
            for user_id in blacklist["users"]:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    user_name = f"{user.name}" if user else f"Unknown User (ID: {user_id})"
                    response += f"• {user_name}\n"
                except:
                    response += f"• Unknown User (ID: {user_id})\n"
            
        # Send the response
        await ctx.reply(response)

    @commands.command(name='list_categories', help='List all available command categories.\nNo arguments required.\nExample: !list_categories')
    @has_command_permission()
    @command_category("Permissions")
    async def list_categories(self, ctx):
        """List all available command categories"""
        categories = sorted(get_categories())
        
        if not categories:
            await ctx.reply("No command categories found.")
            return
            
        # Build response message
        response = "**🗂️ Available Command Categories**\n\n"
        
        for category in categories:
            commands = get_commands_in_category(category)
            response += f"• **{category}** - {len(commands)} commands\n"
            
        await ctx.reply(response)

async def setup(bot):
    await bot.add_cog(PermissionCommandsCog(bot))
