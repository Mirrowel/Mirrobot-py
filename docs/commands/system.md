# System Commands

This document describes the various system-level commands available in Mirrobot.

## Command Reference

### help
Shows information about available commands.

- **Usage**: `!help [command]`
- **Arguments**: 
  - `command` (optional): Shows detailed help for a specific command
- **Examples**: 
  - `!help` - List all available commands
  - `!help add_ocr_read_channel` - Show detailed help for the add_ocr_read_channel command

### helpmenu
Shows an interactive help menu with dropdown categories and command pagination.

- **Usage**: `!helpmenu`
- **Arguments**: None
- **Example**: `!helpmenu`

### ping
Check the bot's current latency.

- **Usage**: `!ping`
- **Arguments**: None
- **Example**: `!ping`

### uptime
Display how long the bot has been running.

- **Usage**: `!uptime`
- **Arguments**: None
- **Example**: `!uptime`

### status
Display bot status, uptime, and statistics.

- **Usage**: `!status`
- **Arguments**: None
- **Example**: `!status`
- **Output**: Shows information about:
  - Bot uptime
  - OCR performance statistics
  - Queue statistics
  - Server statistics

### invite
Get an invite link to add this bot to other servers.

- **Usage**: `!invite`
- **Arguments**: None
- **Example**: `!invite`
- **Note**: Only available to the bot owner

### host
Display detailed information about the host system.

- **Usage**: `!host`
- **Arguments**: None
- **Example**: `!host`
- **Note**: Only available to the bot owner

### reload_patterns
Reload pattern configurations from the patterns.json file.

- **Usage**: `!reload_patterns`
- **Arguments**: None
- **Example**: `!reload_patterns`
- **Note**: Only available to the bot owner

### shutdown
Shut down the bot completely.

- **Usage**: `!shutdown`
- **Arguments**: None
- **Example**: `!shutdown`
- **Note**: Only available to the bot owner
