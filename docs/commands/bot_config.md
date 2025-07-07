# Bot Configuration Commands

These commands are used to manage server-specific bot settings.

### `set_prefix`
Changes the command prefix for the current server. This allows you to customize how you interact with the bot in your server.

- **Usage:** `!set_prefix <new_prefix>`
- **Arguments:**
    - `<new_prefix>` (Required): The new prefix you want to set for bot commands. This can be any string.
- **Examples:**
    - `!set_prefix $`: Changes the prefix to `$`, so commands would be `!$help`.
    - `!set_prefix >`: Changes the prefix to `>`, so commands would be `!>help`.
- **Permissions:** `has_command_permission`

### `reset_prefix`
Resets the command prefix for the current server back to the bot's default prefix, which is typically `!`.

- **Usage:** `!reset_prefix`
- **Permissions:** `has_command_permission`

### `server_info`
Displays a comprehensive overview of all bot configuration settings specific to the current server. This includes the command prefix, OCR channels, permission settings, and other server-level configurations.

- **Usage:** `!server_info`
- **Permissions:** `has_command_permission`
