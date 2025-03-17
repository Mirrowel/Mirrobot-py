# Permission Management Commands

This module provides commands for managing permissions to use the bot's features. Permissions can be granted to specific roles and users, or managed at the category level.

## Role and User Permissions

### Add Command Role

Give a role or user permission to use a specific bot command.

**Command:** `!add_command_role <target> <command_name>`

**Examples:**
- `!add_command_role @Moderators add_ocr_read_channel` - Grant Moderators permission to add OCR channels
- `!add_command_role @username extract_text` - Grant specific user permission to extract text from images

**Notes:**
- Target can be a role mention, role name, user mention, or user ID
- Command name must be a valid bot command

### Remove Command Role

Remove a role or user's permission to use a specific bot command.

**Command:** `!remove_command_role <target> <command_name>`

**Examples:**
- `!remove_command_role @Moderators add_ocr_read_channel`
- `!remove_command_role @username extract_text`

## Bot Manager Commands

### Add Bot Manager

Add a role or user as a bot manager with access to all non-system commands.

**Command:** `!add_bot_manager <target>`

**Examples:**
- `!add_bot_manager @Admins` - Make the Admins role a bot manager
- `!add_bot_manager @username` - Make a specific user a bot manager

**Notes:**
- Bot managers can use all regular commands without needing specific permissions
- System commands are still restricted to the bot owner

### Remove Bot Manager

Remove a role or user from bot managers, revoking access to all commands.

**Command:** `!remove_bot_manager <target>`

**Examples:**
- `!remove_bot_manager @Admins`
- `!remove_bot_manager @username`

## Category Permissions

### Add Category Permission

Give a role or user permission to use all commands in a category.

**Command:** `!add_category_permission <target> <category>`

**Examples:**
- `!add_category_permission @Moderators Moderation` - Grant all moderation commands to Moderators
- `!add_category_permission @username OCR Configuration` - Grant all OCR commands to a user

### Remove Category Permission

Remove a role or user's permission to use all commands in a category.

**Command:** `!remove_category_permission <target> <category>`

**Examples:**
- `!remove_category_permission @Moderators Moderation`
- `!remove_category_permission @username OCR Configuration`

### List Categories

List all available command categories.

**Command:** `!list_categories`

## Blacklist Management

### Add To Blacklist

Add a role or user to the command permission blacklist to prevent them from using any commands.

**Command:** `!add_to_blacklist <target>`

**Examples:**
- `!add_to_blacklist @Troublemaker` - Prevent a user from using any commands
- `!add_to_blacklist @RestrictedRole` - Prevent anyone with a specific role from using commands

**Notes:**
- Users with Administrator permission cannot be blacklisted
- Roles with Administrator permission cannot be blacklisted
- Blacklist overrides all other permission settings (except for administrators)
- Blacklists are now stored persistently in `data/permission_blacklists.json` and will survive bot restarts and config resets

### Remove From Blacklist

Remove a role or user from the permission blacklist.

**Command:** `!remove_from_blacklist <target>`

**Examples:**
- `!remove_from_blacklist @Troublemaker`
- `!remove_from_blacklist @RestrictedRole`

### List Blacklist

List all roles and users in the command permission blacklist.

**Command:** `!list_blacklist`

## Permission System Overview

The permission system uses the following hierarchy (from highest to lowest priority):
1. **Bot Owner** - Always has access to all commands
2. **Blacklist** - Prevents command access regardless of other permissions (except administrators)
3. **Server Administrator** - Has access to all commands in the server
4. **Bot Manager** - Has access to all non-system commands
5. **Category Permission** - Has access to all commands in a specific category
6. **Command Permission** - Has access to a specific command
7. **Discord Permission** - Has access based on Discord permissions

## Default Permissions

- Server owners/administrators have access to all commands
- Only the bot owner can use system commands like `shutdown`, `reload_patterns`, etc.
- Other users need explicit permission grants to use commands
