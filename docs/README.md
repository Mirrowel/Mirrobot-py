# Mirrobot [![License](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/) [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C0C0UZS4P)

Welcome to the Mirrobot documentation. This guide will help you understand how to use and configure the Mirrobot Discord bot.

## Getting Started

If you're new to Mirrobot, start with these guides:

1. [Configuration Guide](configuration.md) - Learn how to set up and configure the bot. Note that LLM and Chatbot settings are now in dedicated files (`data/llm_config.json`, `data/chatbot_config.json`).
2. [Usage Guide](usage.md) - Examples and best practices for using the bot effectively.

## Command Documentation

Mirrobot's commands are organized by category. This is a list of documentation pages for each category:

- [System Commands](commands/system.md) - Basic bot control and information commands.
- [OCR Configuration](commands/ocr_config.md) - Setting up OCR channels and processing options.
- [Pattern Management](commands/patterns.md) - Creating and managing response patterns.
- [Permission Management](commands/permissions.md) - Managing command access permissions.
- [Bot Configuration](commands/bot_config.md) - General bot settings and configuration (like prefixes).
- [AI Assistant (LLM & Chatbot)](llm_integration.md) - Commands for interacting with the Large Language Model and managing the persistent chatbot feature. **(Updated)**

## Developer Documentation

If you're interested in contributing to Mirrobot or understanding its internal structure:

- The code is organized into several modules, each with its own responsibility.
- Core functionality is in the `core` directory (e.g., bot startup, event handlers, main message processing).
- Configuration management is in the `config` directory (`config_manager.py`, `llm_config_manager.py`).
- Utility functions are in the `utils` directory (e.g., logging, permissions, embed helpers, chatbot management, resource monitoring).
- Command implementations are in the `cogs` directory.

## Support

If you need help with Mirrobot:

1. Check the [Troubleshooting](usage.md#troubleshooting) section of the Usage Guide.
2. Visit our [GitHub repository](https://github.com/Mirrowel/Mirrobot-py) to submit issues.
3. Join our [Discord server](https://discord.gg/invite-link) for community support.

## License

Mirrobot is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.