# Moderation Commands

## Thread Management

### Watch Forum
Add a forum channel to the watchlist for automatic thread purging.

**Command:** `!watch_forum <channel> <time_period>`

**Arguments:**
- `<channel>` - The forum channel to watch
- `<time_period>` - Inactivity threshold (format: 3d, 12h, 30m)

**Examples:**
- `!watch_forum #help-forum 7d` - Purge threads after 7 days of inactivity

### Unwatch Forum
Remove a forum channel from the watchlist.

**Command:** `!unwatch_forum <channel>`

**Arguments:**
- `<channel>` - The forum channel to remove from the watchlist

**Examples:**
- `!unwatch_forum #help-forum`

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
- `!list_thread_settings watched` - Show only watched forums
- `!list_thread_settings ignored` - Show only ignored threads
- `!list_thread_settings tags` - Show only ignored tags

## Best Practices

1. Use reasonable inactivity thresholds based on your forum's purpose
   - High-traffic forums may need shorter thresholds (1-3 days)
   - Low-traffic forums may need longer thresholds (7-30 days)

2. Always ignore important reference threads using the `ignore_thread` command

3. Communicate your thread purging policy to your community

4. Consider pinning important threads (pinned threads are automatically excluded from purging)
