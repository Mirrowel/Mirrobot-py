# Maintenance Commands

These commands are for bot maintenance, including restarts and configuration.

### `restart`
Restarts the bot application. This command is useful for applying updates or refreshing the bot's state.

- **Usage:** `!restart`
- **Permissions:** Bot Owner

### `toggle_auto_restart`
Toggles the automatic restart functionality of the bot. When enabled, the bot will restart at the configured interval.

- **Usage:** `!toggle_auto_restart`
- **Permissions:** Bot Owner

### `set_restart_time`
Sets the interval for the bot's automatic restart. This allows you to schedule regular restarts for maintenance or to refresh the bot's state.

- **Usage:** `!set_restart_time <time_string>`
- **Arguments:**
    - `<time_string>` (Required): The time interval for the restart. Supports various formats:
        - `24h`: 24 hours
        - `12h30m`: 12 hours and 30 minutes
        - `1h`: 1 hour
        - `30m`: 30 minutes
        - `1d`: 1 day
        - `7d`: 7 days
- **Examples:**
    - `!set_restart_time 12h`: Sets the bot to restart every 12 hours.
    - `!set_restart_time 1d`: Sets the bot to restart every day.
- **Permissions:** Bot Owner

### `show_restart_settings`
Displays the current automatic restart settings, including whether it's enabled and the configured restart interval.

- **Usage:** `!show_restart_settings`
- **Permissions:** Bot Owner