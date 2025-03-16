# Configuration Guide

This document describes how to configure Mirrobot for your Discord server.

## Initial Setup

1. Create a Discord bot application from the [Discord Developer Portal](https://discord.com/developers/applications)
2. Copy your bot token and add it to the `.env` file or directly into `config.json`
3. Invite the bot to your server using the generated OAuth2 URL

## Configuration File

The main configuration file is `config.json`. Here's what each field means:

```json
{
  "token": "your_discord_bot_token_here",  // Your Discord bot token
  "command_prefix": "!",                    // Default command prefix
  "ocr_worker_count": 2,                    // Number of parallel OCR workers
  "ocr_max_queue_size": 100,                // Maximum OCR queue size
  "ocr_read_channels": {},                  // Channels where OCR scanning is active
  "ocr_response_channels": {},              // Channels where OCR responses are sent
  "ocr_response_fallback": {},              // Fallback channels for OCR responses
  "server_prefixes": {},                    // Server-specific command prefixes
  "command_permissions": {}                 // Command permission settings
}
```

## Environment Variables

Instead of putting your token directly in the config file, you can use environment variables:

1. Create a `.env` file based on the `.env.example` template
2. Add your Discord bot token: `DISCORD_BOT_TOKEN=your_token_here`

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
