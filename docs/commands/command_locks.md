# Command Lock Commands

Manage which servers cannot use specific commands or command categories.

Locks are server blacklists. If a command or category is not listed for a server, it is available normally. When you add a server to a command/category lock, that command/category is disabled only in that server. Slash commands are synced per server so locked commands are hidden from servers where they are disabled.

### `command_lock command add`
Disables a command in a server.

- **Usage:** `!command_lock command add <command_name> [guild_id]`
- **Slash:** `/command_lock command add`
- **Permissions:** `has_command_permission`

### `command_lock command remove`
Removes a command/server blacklist entry, re-enabling that command in the server.

- **Usage:** `!command_lock command remove <command_name> [guild_id]`
- **Slash:** `/command_lock command remove`
- **Permissions:** `has_command_permission`

### `command_lock category add`
Disables a command category in a server.

- **Usage:** `!command_lock category add <category_name> [guild_id]`
- **Slash:** `/command_lock category add`
- **Permissions:** `has_command_permission`

### `command_lock category remove`
Removes a category/server blacklist entry, re-enabling that category in the server.

- **Usage:** `!command_lock category remove <category_name> [guild_id]`
- **Slash:** `/command_lock category remove`
- **Permissions:** `has_command_permission`

### `command_lock list`
Lists configured command and category locks.

- **Usage:** `!command_lock list [guild_id]`
- **Slash:** `/command_lock list`
- **Permissions:** `has_command_permission`
