# Permission Management Commands

This document describes the commands available for managing permissions in Mirrobot.

## Permission System Overview

Mirrobot uses a hierarchical permission system:

1. **Bot Owner**: Has access to all commands without restriction
2. **Server Administrators**: Have access to all commands on their server
3. **Bot Managers**: Roles or users granted access to all non-system commands
4. **Command-specific Permissions**: Roles or users granted access to specific commands

## Command Reference

### add_command_role
Give a role or user permission to use a specific bot command.

- **Usage**: `!add_command_role <target> <command_name>`
- **Arguments**: 
  - `target` (required): The role/user to grant permission to (mention or ID)
  - `command_name` (required): The name of the command
- **Examples**: 
  - `!add_command_role @Moderators add_ocr_read_channel`
  - `!add_command_role @username add_ocr_read_channel`
- **Permissions**: Requires administrator privileges or bot manager status

### remove_command_role
Remove a role or user's permission to use a specific bot command.

- **Usage**: `!remove_command_role <target> <command_name>`
- **Arguments**: 
  - `target` (required): The role/user to remove permission from (mention or ID)
  - `command_name` (required): The name of the command
- **Examples**: 
  - `!remove_command_role @Moderators add_ocr_read_channel`
  - `!remove_command_role @username add_ocr_read_channel`
- **Permissions**: Requires administrator privileges or bot manager status

### add_bot_manager
Add a role or user as a bot manager with access to all non-system commands.

- **Usage**: `!add_bot_manager <target>`
- **Arguments**: 
  - `target` (required): The role/user to designate as bot manager (mention or ID)
- **Examples**: 
  - `!add_bot_manager @Admins`
  - `!add_bot_manager @username`
- **Permissions**: Requires administrator privileges

### remove_bot_manager
Remove a role or user from bot managers, revoking access to all commands.

- **Usage**: `!remove_bot_manager <target>`
- **Arguments**: 
  - `target` (required): The role/user to remove from manager status (mention or ID)
- **Examples**: 
  - `!remove_bot_manager @Admins`
  - `!remove_bot_manager @username`
- **Permissions**: Requires administrator privileges

## Permission Hierarchy

When determining if a user can run a command, Mirrobot checks permissions in this order:

1. Is the user the bot owner?
2. Is the user a server administrator?
3. Is the user (or their roles) listed as a bot manager?
4. Does the user (or their roles) have specific permission for the command?

If any check passes, the user can use the command. Otherwise, access is denied.

## Managing Permissions

It's recommended to:

1. Grant `bot_manager` status to trusted admin/mod roles
2. Use command-specific permissions for roles that need limited access
3. Use the `server_info` command to review current permission settings

## Best Practices

- **Least Privilege**: Give users only the permissions they need
- **Role-Based**: Grant permissions to roles rather than individual users when possible
- **Documentation**: Keep track of which roles have which permissions
- **Audit**: Periodically review permissions using `server_info`
