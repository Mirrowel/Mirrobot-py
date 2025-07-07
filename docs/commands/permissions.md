# Permission Management Commands

These commands are for managing role-based and user-based permissions for bot commands.

### `add_command_role`
Grants a specific role or user permission to use a particular bot command. This allows for granular control over who can access individual commands.

- **Usage:** `!add_command_role <target> <command_name>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to grant permission to.
    - `<command_name>` (Required): The exact name of the command (e.g., `add_ocr_read_channel`, `set_prefix`).
- **Examples:**
    - `!add_command_role @Moderators add_ocr_read_channel`: Allows the `@Moderators` role to use the `add_ocr_read_channel` command.
    - `!add_command_role @SomeUser purge_threads`: Allows `@SomeUser` to use the `purge_threads` command.
- **Permissions:** `has_command_permission`

### `remove_command_role`
Revokes a specific role or user's permission to use a particular bot command.

- **Usage:** `!remove_command_role <target> <command_name>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to remove permission from.
    - `<command_name>` (Required): The exact name of the command.
- **Examples:**
    - `!remove_command_role @Moderators add_ocr_read_channel`: Revokes the `@Moderators` role's permission to use `add_ocr_read_channel`.
    - `!remove_command_role @SomeUser purge_threads`: Revokes `@SomeUser`'s permission to use `purge_threads`.
- **Permissions:** `has_command_permission`

### `add_bot_manager`
Designates a role or user as a "bot manager." Bot managers have access to all bot commands, except for highly restricted system commands (e.g., `restart`). This provides a convenient way to grant broad administrative control over the bot.

- **Usage:** `!add_bot_manager <target>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to designate as a bot manager.
- **Examples:**
    - `!add_bot_manager @Admins`: Grants all members of the `@Admins` role bot manager privileges.
    - `!add_bot_manager @SomeUser`: Grants `@SomeUser` bot manager privileges.
- **Permissions:** `has_command_permission`

### `remove_bot_manager`
Removes a role or user from the bot manager list, revoking their broad access to bot commands.

- **Usage:** `!remove_bot_manager <target>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to remove from bot manager status.
- **Examples:**
    - `!remove_bot_manager @Admins`: Removes the `@Admins` role from bot manager privileges.
    - `!remove_bot_manager @SomeUser`: Removes `@SomeUser` from bot manager privileges.
- **Permissions:** `has_command_permission`

### `add_category_permission`
Grants a specific role or user permission to use all commands within a designated command category. This simplifies permission management for groups of related commands.

- **Usage:** `!add_category_permission <target> <category_name>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to grant permission to.
    - `<category_name>` (Required): The exact name of the command category (e.g., `Moderation`, `AI Assistant`). You can list available categories using `!list_categories`.
- **Examples:**
    - `!add_category_permission @Moderators Moderation`: Allows the `@Moderators` role to use all commands in the "Moderation" category.
    - `!add_category_permission @SomeUser "Bot Configuration"`: Allows `@SomeUser` to use all commands in the "Bot Configuration" category.
- **Permissions:** `has_command_permission`

### `remove_category_permission`
Revokes a specific role or user's permission to use all commands within a designated command category.

- **Usage:** `!remove_category_permission <target> <category_name>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to remove permission from.
    - `<category_name>` (Required): The exact name of the command category.
- **Examples:**
    - `!remove_category_permission @Moderators Moderation`: Revokes the `@Moderators` role's permission to use commands in the "Moderation" category.
    - `!remove_category_permission @SomeUser "Bot Configuration"`: Revokes `@SomeUser`'s permission to use commands in the "Bot Configuration" category.
- **Permissions:** `has_command_permission`

### `list_categories`
Lists all available command categories that can be used with permission management commands (e.g., `add_category_permission`).

- **Usage:** `!list_categories`
- **Permissions:** `has_command_permission`

### `add_to_blacklist`
Adds a role or user to the global command permission blacklist. Entities on the blacklist are explicitly denied from using any bot commands, regardless of any other permissions they may have.

- **Usage:** `!add_to_blacklist <target>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to add to the blacklist.
- **Examples:**
    - `!add_to_blacklist @Troublemaker`: Blacklists `@Troublemaker` from using any bot commands.
    - `!add_to_blacklist @SpamRole`: Blacklists all members of the `@SpamRole` from using any bot commands.
- **Permissions:** `has_command_permission`

### `remove_from_blacklist`
Removes a role or user from the global command permission blacklist, allowing them to use commands again (subject to other permission settings).

- **Usage:** `!remove_from_blacklist <target>`
- **Arguments:**
    - `<target>` (Required): The role (mention or ID) or user (mention or ID) to remove from the blacklist.
- **Examples:**
    - `!remove_from_blacklist @Troublemaker`: Removes `@Troublemaker` from the blacklist.
    - `!remove_from_blacklist @SpamRole`: Removes all members of the `@SpamRole` from the blacklist.
- **Permissions:** `has_command_permission`

### `list_blacklist`
Lists all roles and users currently in the global command permission blacklist. This provides an overview of which entities are explicitly prevented from using bot commands.

- **Usage:** `!list_blacklist`
- **Permissions:** `has_command_permission`
