# Configuration Guide

This document describes how to configure Mirrobot for your Discord server.

## Initial Setup

1. Create a Discord bot application from the [Discord Developer Portal](https://discord.com/developers/applications)
2. Copy your bot token and add it to the `.env` file or directly into `config.json`
3. Invite the bot to your server using the generated OAuth2 URL

## Configuration File

The main configuration file is `config.json`. You can copy `config_example.json` as a starting point. Here's what each field means:

```json
{
  "token": "See environment variable DISCORD_BOT_TOKEN",  // Your Discord bot token (RECOMMENDED: Use environment variable)
  "command_prefix": "!",                                  // Default command prefix
  "ocr_worker_count": 2,                                  // Number of parallel OCR workers
  "ocr_max_queue_size": 100,                              // Maximum OCR queue size
  "thread_purge_interval_minutes": 10,                    // How often to purge old thread data
  "ocr_read_channels": {},                                // Channels where OCR scanning is active
  "ocr_response_channels": {},                            // Channels where OCR responses are sent
  "ocr_response_fallback": {},                            // Fallback channels for OCR responses
  "server_prefixes": {},                                  // Server-specific command prefixes
  "command_permissions": {},                              // Command permission settings
  "ocr_channel_config": {},                               // OCR language settings per channel
  "maintenance": {                                        // Auto-restart and maintenance settings
    "restart_threshold_seconds": 86400,                   // Auto-restart after 24 hours
    "check_interval_minutes": 15,                         // Check interval for restart conditions
    "auto_restart_enabled": true                          // Enable automatic restarts
  }
}
```

### Configuration Field Details

- **token**: Your Discord bot token. **STRONGLY RECOMMENDED** to use the `DISCORD_BOT_TOKEN` environment variable instead
- **ocr_read_channels**: Format: `{"guild_id": [channel_id1, channel_id2]}` - Channels to monitor for images
- **ocr_response_channels**: Format: `{"guild_id": [channel_id1, channel_id2]}` - Where to send OCR results
- **ocr_response_fallback**: Format: `{"guild_id": [channel_id1, channel_id2]}` - Backup channels if primary unavailable
- **server_prefixes**: Format: `{"guild_id": "prefix"}` - Custom prefixes per server (e.g., `"ocr!"`)
- **command_permissions**: Format: `{"guild_id": {"command": ["role_id1"]}}` - Role-based command access
- **ocr_channel_config**: Format: `{"guild_id": {"channel_id": {"lang": "eng"}}}` - Language per channel

## Media Caching

The bot can be configured to re-upload Discord media attachments to third-party services to prevent links from expiring. This is useful for preserving conversation history that is passed to the LLM.

- **media_caching**:
  - **enabled**: `true` or `false`. Enables or disables the media caching feature.
  - **services**: A list of services to use for uploading. Supported services are `"litterbox"`, `"catbox"`, and `"pixeldrain"`.
  - **upload_timeout_seconds**: The timeout in seconds for each upload attempt.
  - **permanent_host_fallback**: `true` or `false`. If `true`, the bot will fall back to a permanent host if the temporary host (`litterbox`) fails.
  - **pixeldrain_api_key**: Your API key for the Pixeldrain service.
  - **catbox_user_hash**: Your user hash for the Catbox service.

## Environment Variables

**RECOMMENDED APPROACH**: Use environment variables for sensitive data:

1. Create a `.env` file based on the `.env.example` template
2. Add your Discord bot token: `DISCORD_BOT_TOKEN=your_token_here`
3. Optionally add Google AI API key: `GOOGLE_AI_API_KEY=your_key_here`

The bot will automatically use environment variables when available, overriding config file values.

## OCR Configuration

### Setting Up OCR Channels

To enable OCR in specific channels:

1. Use `!add_ocr_read_channel #channel-name` to add a channel for OCR scanning
2. Use `!add_ocr_response_channel #channel-name` to designate where responses go
3. Optionally set language: `!set_ocr_language #channel-name eng` (eng = English, rus = Russian)

### OCR Performance Tuning

- Increase `ocr_worker_count` for faster processing (but higher CPU usage)
- Adjust `ocr_max_queue_size` based on your server's activity level

## Patterns Configuration

Patterns are stored in `patterns.json`. Each pattern associates a regex pattern with a response.

You can manage patterns using:

- `!add_response "response text" "name" "note"`
- `!add_pattern_to_response "response-name" "regex pattern" "IGNORECASE|DOTALL"`
- `!remove_pattern_from_response "response-name" pattern_id`

## Permissions

Manage command permissions:

- `!add_command_role @role command_name` - Give a role permission to use a command
- `!remove_command_role @role command_name` - Remove permission
- `!add_bot_manager @role` - Give a role access to all non-system commands

## Server-Specific Settings

- Change the command prefix: `!set_prefix $`
- Reset to default prefix: `!reset_prefix`
- View all server settings: `!server_info`
