# Mirrobot [![License](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/) [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C0C0UZS4P)

Welcome to the Mirrobot documentation. This guide will help you understand how to use and configure the Mirrobot Discord bot.

## Getting Started

If you're new to Mirrobot, start with these guides:

1. [Configuration Guide](configuration.md) - Learn how to set up and configure the bot. Note that LLM and Chatbot settings are now in dedicated files (`data/llm_config.json`, `data/chatbot_config.json`).
2. [Usage Guide](usage.md) - Examples and best practices for using the bot effectively.

## Command Documentation

Mirrobot's commands are organized by category. This is a list of documentation pages for each category:

- [AI Assistant](commands/ai_assistant.md) - Interact with the LLM and manage the chatbot.
- [Bot Configuration](commands/bot_config.md) - General bot settings and configuration.
- [Inline Response](commands/inline_response.md) - Configure inline responses to mentions.
- [Log Analysis](commands/log_analysis.md) - Analyze game logs for errors.
- [Maintenance](commands/maintenance.md) - Bot maintenance and restart commands.
- [Moderation](commands/moderation.md) - Automated thread purging and moderation tools.
- [OCR Configuration](commands/ocr_config.md) - Set up OCR channels and processing options.
- [Pattern Management](commands/patterns.md) - Create and manage response patterns.
- [Permission Management](commands/permissions.md) - Manage command access permissions.
- [System](commands/system.md) - Basic bot control and information commands.
- [Testing](commands/testing.md) - Commands for testing bot features.

## Developer Documentation

If you're interested in contributing to Mirrobot or understanding its internal structure:

- **`/core/`**: Core functionality (bot startup, event handlers, OCR processing).
- **`/cogs/`**: Command implementations, organized by category.
- **`/utils/`**: Helper modules for permissions, logging, embeds, and more.
- **`/config/`**: Configuration management for the main bot and LLM features.
- **`/docs/`**: All documentation files.
- **`/data/`**: Data files for patterns, LLM configurations, and conversation history.

## Support

If you need help with Mirrobot:

1. Check the [Troubleshooting](usage.md#troubleshooting) section of the Usage Guide.
2. Visit our [GitHub repository](https://github.com/Mirrowel/Mirrobot-py) to submit issues.
3. Join our [Discord server](https://discord.gg/invite-link) for community support.

## License

Mirrobot is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.