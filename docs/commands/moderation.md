# Moderation Commands

This module provides commands for managing forum threads, including automatic purging of inactive threads.

## Thread Purging Commands

### Watch Forum

Add a forum channel to the watchlist for automatic thread purging.

**Command:** `!watch_forum <channel> <time_period>`

**Examples:**
- `!watch_forum #help-forum 7d` - Purge threads in #help-forum that are inactive for 7 days
- `!watch_forum #questions 24h` - Purge threads in #questions that are inactive for 24 hours
- `!watch_forum #quick-help 30m` - Purge threads in #quick-help that are inactive for 30 minutes

**Notes:**
- Time format can be specified as:
  - `Xd` for X days
  - `Xh` for X hours
  - `Xm` for X minutes
- Only works on forum channels
- Requires "Manage Channels" permission

### Unwatch Forum

Remove a forum channel from the watchlist.

**Command:** `!unwatch_forum <channel>`

**Example:** `!unwatch_forum #help-forum`

**Notes:**
- Requires "Manage Channels" permission

### List Watched

List all forum channels in the watchlist for this server.

**Command:** `!list_watched`

**Notes:**
- Requires "Manage Channels" permission

## Thread Ignore Commands

### Ignore Thread

Add a thread to the ignore list to prevent it from being purged automatically.

**Command:** `!ignore_thread <thread>`

**Example:** `!ignore_thread #important-thread`

**Notes:**
- Requires "Manage Threads" permission

### Unignore Thread

Remove a thread from the ignore list.

**Command:** `!unignore_thread <thread>`

**Example:** `!unignore_thread #no-longer-important-thread`

**Notes:**
- Requires "Manage Threads" permission

### List Ignored

List all threads in the ignore list for this server.

**Command:** `!list_ignored`

**Notes:**
- Requires "Manage Threads" permission

## Best Practices

1. Use reasonable inactivity thresholds based on your forum's purpose
   - High-traffic forums may need shorter thresholds (1-3 days)
   - Low-traffic forums may need longer thresholds (7-30 days)

2. Always ignore important reference threads using the `ignore_thread` command

3. Communicate your thread purging policy to your community

4. Consider pinning important threads (pinned threads are automatically excluded from purging)
