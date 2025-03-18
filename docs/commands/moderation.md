# Moderation Commands

## Thread Management

### Watch Forum
Add a channel to the watchlist for automatic thread purging.

**Command:** `!watch_forum <channel> <time_period>`

**Arguments:**
- `<channel>` - The channel to watch (can be a forum channel, text channel, or voice channel)
- `<time_period>` - Inactivity threshold (format: 3d, 12h, 30m, 45s)

**Examples:**
- `!watch_forum #help-forum 7d` - Purge threads after 7 days of inactivity
- `!watch_forum #general 24h` - Purge threads after 24 hours of inactivity

### Unwatch Forum
Remove a channel from the watchlist.

**Command:** `!unwatch_forum <channel>`

**Arguments:**
- `<channel>` - The channel to remove from the watchlist

**Examples:**
- `!unwatch_forum #help-forum`

### Purge Threads
Manually purge inactive threads from a channel.

**Command:** `!purge_threads <channel> <time_period>`

**Arguments:**
- `<channel>` - The channel containing threads to purge
- `<time_period>` - Inactivity threshold (format: 3d, 12h, 30m, 45s)

**Examples:**
- `!purge_threads #help-forum 7d` - Purge threads inactive for 7 days
- `!purge_threads #general 2h` - Purge threads inactive for 2 hours

### Ignore Thread
Add a thread to the ignore list to prevent it from being purged.

**Command:** `!ignore_thread <thread>`

**Arguments:**
- `<thread>` - The thread to add to the ignore list

**Examples:**
- `!ignore_thread #important-thread`

### Unignore Thread
Remove a thread from the ignore list.

**Command:** `!unignore_thread <thread>`

**Arguments:**
- `<thread>` - The thread to remove from the ignore list

**Examples:**
- `!unignore_thread #no-longer-important-thread`

### Ignore Tag
Add a thread tag to the ignore list to prevent threads with that tag from being purged.

**Command:** `!ignore_tag <tag_name>`

**Arguments:**
- `<tag_name>` - The name of the tag to ignore

**Examples:**
- `!ignore_tag important`
- `!ignore_tag "do not delete"`

### Unignore Tag
Remove a thread tag from the ignore list.

**Command:** `!unignore_tag <tag_name>`

**Arguments:**
- `<tag_name>` - The name of the tag to remove from the ignore list

**Examples:**
- `!unignore_tag important`

### List Thread Settings
List thread management settings for this server.

**Command:** `!list_thread_settings [type]`

**Arguments:**
- `[type]` (optional) - Filter by "watched", "ignored", or "tags" (default: all)

**Examples:**
- `!list_thread_settings` - Show all settings
- `!list_thread_settings watched` - Show only watched channels
- `!list_thread_settings ignored` - Show only ignored threads
- `!list_thread_settings tags` - Show only ignored tags

## Best Practices

1. Use reasonable inactivity thresholds based on your channel's purpose
   - High-traffic channels may need shorter thresholds (1-3 days)
   - Low-traffic channels may need longer thresholds (7-30 days)

2. Always ignore important reference threads using the `ignore_thread` command

3. Communicate your thread purging policy to your community

4. Consider pinning important threads (pinned threads are automatically excluded from purging)

5. Use the `purge_threads` command to clean up channels on demand before setting up automatic purging
