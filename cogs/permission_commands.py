import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category, get_permission_target
from config.config_manager import save_config

logger = get_logger()

class PermissionCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

async def setup(bot):
    await bot.add_cog(PermissionCommandsCog(bot))
