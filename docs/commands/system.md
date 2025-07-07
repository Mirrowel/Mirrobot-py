# System Commands

These commands provide general information about the bot and the system it's running on.

### `help`
Displays information about the bot and its commands. You can get a general overview or detailed help on a specific command.

- **Usage:** `!help [command_name]`
- **Arguments:**
    - `[command_name]` (Optional): The name of a specific command to get detailed help for (e.g., `set_prefix`, `purge_threads`).
- **Examples:**
    - `!help`: Shows a general help message.
    - `!help set_prefix`: Shows detailed help for the `set_prefix` command.
- **Alias:** `info`
- **Permissions:** Everyone

### `helpmenu`
Displays an interactive help menu with dropdown categories and command pagination. This provides a user-friendly way to browse all available commands and their descriptions directly within Discord.

- **Usage:** `!helpmenu`
- **Permissions:** Everyone

### `ping`
Checks the bot's current latency (response time) to the Discord API. This is useful for diagnosing connection issues or general bot responsiveness.

- **Usage:** `!ping`
- **Permissions:** Everyone

### `uptime`
Displays how long the bot has been continuously running since its last restart.

- **Usage:** `!uptime`
- **Permissions:** Everyone

### `status`
Displays the bot's current operational status, including its uptime, server count, user count, and other relevant statistics.

- **Usage:** `!status`
- **Permissions:** Everyone

### `invite`
Generates and provides an invite link that allows you to add the bot to other Discord servers.

- **Usage:** `!invite`
- **Permissions:** Bot Owner

### `host`
Displays detailed information about the host system where the bot is currently running. This includes operating system details, CPU usage, memory usage, and disk space.

- **Usage:** `!host`
- **Permissions:** Bot Owner

### `shutdown`
Shuts down the bot application completely. This command requires direct ownership of the bot.

- **Usage:** `!shutdown`
- **Permissions:** Bot Owner

### `reload_patterns`
Reloads the pattern configurations from the `patterns.json` file. This is useful if you have manually edited the patterns file and want the bot to apply the changes without a full restart.

- **Usage:** `!reload_patterns`
- **Permissions:** Bot Owner

### `about`
Displays detailed information about the bot, including its version, developer, and a brief description of its purpose.

- **Usage:** `!about`
- **Alias:** `botinfo`
- **Permissions:** Everyone
