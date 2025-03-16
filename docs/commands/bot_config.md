# Bot Configuration Commands

This document describes the commands available for basic bot configuration in Mirrobot.

## Command Reference

### set_prefix
Change the command prefix for this server.

- **Usage**: `!set_prefix <prefix>`
- **Arguments**: 
  - `prefix` (required): The new prefix to use
- **Examples**: 
  - `!set_prefix $`
  - `!set_prefix >`
- **Notes**: 
  - After changing the prefix, you'll use the new prefix for all commands
  - You can always mention the bot as a prefix regardless of the configured prefix
- **Permissions**: Requires administrator privileges or bot manager status

### reset_prefix
Reset the command prefix for this server to the default (!).

- **Usage**: `!reset_prefix`
- **Arguments**: None
- **Example**: `!reset_prefix`
- **Note**: If you've changed your prefix and forgotten it, you can always use `@Mirrobot reset_prefix`
- **Permissions**: Requires administrator privileges or bot manager status

### server_info
Display all bot configuration settings for this server.

- **Usage**: `!server_info`
- **Arguments**: None
- **Example**: `!server_info`
- **Output**: Shows information about:
  - Current prefix setting
  - OCR read channels
  - OCR response channels
  - OCR fallback channels
  - Bot manager roles and users
  - Command permissions
- **Permissions**: Requires administrator privileges or bot manager status

## Configuration Best Practices

### Prefixes

- **Choose Distinct Prefixes**: Avoid prefixes that might conflict with other bots on your server
- **Short Prefixes**: Short prefixes (like `!`, `$`, `>`) are easier to type
- **Consistent Prefixes**: Consider using the same prefix for all bots for consistency
- **Mention Alternative**: Remember you can always use `@Mirrobot command` regardless of prefix

### Server Configuration

- Review your server configuration periodically using `!server_info`
- Keep track of which channels are configured for OCR
- Document any custom settings in a dedicated server channel
