# Moderation Commands

These commands are for managing threads and channels, including automated purging of inactive threads.

### `watch_forum`
Adds a forum channel to the watchlist for automatic thread purging. The bot will periodically check this channel and purge threads that have been inactive for the specified duration.

- **Usage:** `!watch_forum <channel> <inactivity_period>`
- **Arguments:**
    - `<channel>` (Required): The forum channel to watch (e.g., `#help-forum`).
    - `<inactivity_period>` (Required): The period of inactivity after which threads should be purged. Supports formats like `7d` (7 days), `24h` (24 hours), `30m` (30 minutes).
- **Example:** `!watch_forum #help-forum 7d`
- **Permissions:** `manage_channels`

### `unwatch_forum`
Removes a forum channel from the watchlist, stopping automatic thread purging for that channel.

- **Usage:** `!unwatch_forum <channel>`
- **Arguments:**
    - `<channel>` (Required): The forum channel to unwatch (e.g., `#help-forum`).
- **Example:** `!unwatch_forum #help-forum`
- **Permissions:** `manage_channels`

### `purge_threads`
Manually purges inactive threads from a specified channel. This command allows for immediate cleanup of old or resolved threads.

- **Usage:** `!purge_threads <channel> <inactivity_period>`
- **Arguments:**
    - `<channel>` (Required): The channel from which to purge threads (e.g., `#help-forum`).
    - `<inactivity_period>` (Required): The period of inactivity after which threads should be purged. Supports formats like `7d` (7 days), `24h` (24 hours), `30m` (30 minutes).
- **Example:** `!purge_threads #help-forum 30d`
- **Permissions:** `manage_channels`

### `ignore_thread`
Adds a specific thread to the ignore list, preventing it from being automatically purged by the bot's thread management system. This is useful for important or ongoing discussions that should not be closed due to inactivity.

- **Usage:** `!ignore_thread <thread>`
- **Arguments:**
    - `<thread>` (Required): The thread to ignore (e.g., `#important-discussion`).
- **Example:** `!ignore_thread #important-announcements`
- **Permissions:** `manage_channels`

### `unignore_thread`
Removes a thread from the ignore list, allowing it to be subject to automatic purging based on the channel's `watch_forum` settings.

- **Usage:** `!unignore_thread <thread>`
- **Arguments:**
    - `<thread>` (Required): The thread to unignore (e.g., `#no-longer-important-thread`).
- **Example:** `!unignore_thread #old-discussion`
- **Permissions:** `manage_channels`

### `ignore_tag`
Adds a specific thread tag to the ignore list. Threads within watched forum channels that have this tag will be excluded from automatic purging, regardless of their inactivity.

- **Usage:** `!ignore_tag <tag_name>`
- **Arguments:**
    - `<tag_name>` (Required): The exact name of the thread tag to ignore. Enclose in quotes if the tag name contains spaces.
- **Example:** `!ignore_tag "In Progress"`
- **Permissions:** `manage_channels`

### `unignore_tag`
Removes a thread tag from the ignore list, allowing threads with that tag to be subject to automatic purging based on the channel's `watch_forum` settings.

- **Usage:** `!unignore_tag <tag_name>`
- **Arguments:**
    - `<tag_name>` (Required): The exact name of the thread tag to unignore. Enclose in quotes if the tag name contains spaces.
- **Example:** `!unignore_tag "Resolved"`
- **Permissions:** `manage_channels`

### `list_thread_settings`
Lists the current thread management settings for the server. This includes channels being watched for automatic purging, individual threads being ignored, and thread tags that prevent purging.

- **Usage:** `!list_thread_settings [type]`
- **Arguments:**
    - `[type]` (Optional): A filter to display specific settings:
        - `watched`: Shows only channels configured for automatic purging.
        - `ignored`: Shows only individual threads that are being ignored.
        - `tags`: Shows only thread tags that are being ignored.
        - Defaults to `all` if no type is specified.
- **Examples:**
    - `!list_thread_settings`: Lists all thread management settings.
    - `!list_thread_settings watched`: Shows only watched forum channels.
    - `!list_thread_settings tags`: Shows only ignored thread tags.
- **Permissions:** `manage_channels`
