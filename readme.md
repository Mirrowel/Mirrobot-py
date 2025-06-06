# 🤖 Mirrobot Discord Bot [![License](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/) [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C0C0UZS4P)

Mirrobot is an OCR (Optical Character Recognition) bot that scans images for text patterns and provides automatic responses to common issues. The bot is designed to help server administrators manage technical support channels by automatically analyzing screenshots.

## ✨ Features

- **Advanced OCR Processing**: Analyzes images posted in designated channels
- **Parallel Processing**: Configurable multi-worker system for handling OCR tasks simultaneously
- **Smart Queue Management**: Efficient handling of incoming images with backpressure control
- **Pattern Recognition**: Identifies common issues from error messages
- **Automatic Responses**: Provides helpful solutions for recognized problems
- **Flexible Configuration**: Customize command prefix and permissions
- **Role-based Permissions**: Grant specific access to commands by role or user
- **Comprehensive Statistics**: Monitor OCR performance and queue metrics
- **Resource Monitoring**: Track system resource usage and performance
- **Thread Management**: Automatically or manually purge inactive threads from any channel type
- **Environment Variable Support**: Secure configuration through environment variables
- **LLM Integration**: Connect to a local or Google AI-powered LLM for natural language queries using `!ask` and `!think` commands.
- **Conversational Chatbot Mode**: Enable persistent, context-aware chat in designated channels with `!chatbot_enable` / `!chatbot_disable`, leveraging automatic message and pinned context indexing.

## 🛠️ Installation

1. Install Python 3.8 or higher
2. Install Tesseract OCR:
   - Windows: Download from [GitHub](https://github.com/tesseract-ocr/tesseract)
   - Linux: `sudo apt install tesseract-ocr`
   - Mac: `brew install tesseract`
3. Clone the repository: `git clone https://github.com/Mirrowel/Mirrobot-py.git`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a config file:
   - Rename `config_example.json` to `config.json`
   - Add your Discord bot token and configure settings
   - Alternatively, use environment variables by copying `.env.example` to `.env`
6. Download appropriate tessdata language files:
   - Tesseract comes with "fast" data by default (fastest but least accurate)
   - For better results, download either:
     - **Regular**: Good balance between speed and accuracy
     - **Best**: Highest accuracy, but 2x slower than regular with only small accuracy gains
   - Get additional language data from [tessdata repository](https://github.com/tesseract-ocr/tessdata)
7. Run the bot: `python main.py`

## 📚 Dependencies

The bot relies on the following libraries:

### External Libraries

- **discord.py**: Discord API wrapper for Python
- **pytesseract**: Python wrapper for Google's Tesseract OCR
- **Pillow (PIL)**: Python Imaging Library for image processing
- **aiohttp**: Asynchronous HTTP client/server framework
- **colorlog**: Log formatting with colors for console output
- **requests**: Simple HTTP library for API requests
- **psutil**: Cross-platform process and system monitoring
- **py-cpuinfo**: CPU information retrieval library
- **python-dotenv**: Loading environment variables from .env files
- **google-generativeai**: Google's Generative AI Python SDK for accessing Gemini models

### Standard Libraries

- **json**: JSON data encoding/decoding
- **os**: Operating system interfaces
- **re**: Regular expression operations
- **asyncio**: Asynchronous I/O
- **io**: Core tools for working with streams
- **time**: Time access and conversions
- **subprocess**: Subprocess management
- **tempfile**: Generate temporary files and directories
- **logging**: Logging facility for Python
- **sys**: System-specific parameters and functions
- **datetime**: Basic date and time types
- **platform**: Access to underlying platform's identifying data
- **functools**: Higher-order functions and operations on callable objects
- **socket**: Low-level networking interface
- **collections**: Container datatypes
- **threading**: Thread-based parallelism

### Additional Dependencies

- **psutil**: Cross-platform process and system monitoring

## ⚙️ Configuration

The bot can be configured in two ways:

### 1. Configuration File

The bot uses a `config.json` file to store:

- Discord bot token
- Command prefix (default: `!`)
- Designated channels for OCR reading and responses
- OCR worker count (default: 2)
- OCR queue size (default: 100)
- Command permissions

Example configuration:

```json
{
  "token": "your_discord_bot_token_here",
  "command_prefix": "!",
  "ocr_worker_count": 2,
  "ocr_max_queue_size": 100,
  "ocr_read_channels": {},
  "ocr_response_channels": {},
  "ocr_response_fallback": {},
  "server_prefixes": {},
  "command_permissions": {}
}
```

### 2. Environment Variables

For improved security, you can use environment variables:

1. Create a `.env` file based on `.env.example`
2. Add your Discord bot token: `DISCORD_BOT_TOKEN=your_token_here`

Environment variables take precedence over the config file settings.

### 3. LLM and Chatbot Configuration

#### LLM Configuration (`data/llm_config.json`)

- `base_url`: URL of local LLM server when using `provider: local`

- `timeout`, `max_retries`, `retry_delay`: Request settings

- `provider`: `local` or `google_ai`

- `google_ai_api_key`, `google_ai_model_name`: Google AI key and default model

- `servers`: Per-guild overrides (`enabled`, `preferred_model`, `last_used_model`)

Commands:

| Command          | Description                            | Usage                                  | Permissions     |
|------------------|----------------------------------------|----------------------------------------|-----------------|
| **llm_provider**   | Switch LLM provider                     | `!llm_provider <local\|google_ai>`       | Bot Owner       |
| **llm_set_api_key**| Set Google AI API key                   | `!llm_set_api_key <api_key>`             | Bot Owner       |
| **llm_status**     | Show provider and model status          | `!llm_status`                            | Manage Messages |
| **llm_models**     | List available models                   | `!llm_models [filters]`                  | Manage Messages |
| **llm_select**     | Select model by name or index           | `!llm_select <model_name_or_number>`     | Bot Owner       |
| **ask**            | Standard LLM query                      | `!ask <question>`                        | Manage Messages |
| **think**          | LLM query with thinking prompt          | `!think [<true\|false>] <question>`      | Manage Guild    |

#### Chatbot Configuration (`data/chatbot_config.json`)

- `channels`: Per-guild/channel settings (`enabled`, `max_context_messages`, `max_user_context_messages`, `context_window_hours`, `response_delay_seconds`, `max_response_length`, `auto_prune_enabled`, `prune_interval_hours`, `auto_respond_to_mentions`, `auto_respond_to_replies`)

- `global`: Defaults (`max_context_messages`, `max_user_context_messages`, `context_window_hours`, `response_delay_seconds`, `max_response_length`, `auto_prune_enabled`, `prune_interval_hours`, `user_index_cleanup_hours`, `auto_index_on_restart`, `auto_index_on_enable`)

Commands:

| Command                | Description                      | Usage                         | Permissions        |
|------------------------|----------------------------------|-------------------------------|--------------------|
| **chatbot_enable**       | Enable chatbot in current channel | `!chatbot_enable`             | Chatbot Enable     |
| **chatbot_disable**      | Disable chatbot mode              | `!chatbot_disable`            | Chatbot Disable    |
| **chatbot_status**       | Show config and stats             | `!chatbot_status`             | Chatbot Status     |
| **chatbot_config**       | View/modify settings              | `!chatbot_config [setting] [value]` | Chatbot Config     |
| **chatbot_clear_history**| Clear conversation history         | `!chatbot_clear_history`      | Chatbot Clear History |

## 📝 Available Commands

### OCR Configuration Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **add_ocr_read_channel** | Add a channel where the bot will scan images for OCR processing | `!add_ocr_read_channel #channel [language]` | Admin, Manager |
| **remove_ocr_read_channel** | Remove a channel from the OCR reading list | `!remove_ocr_read_channel #channel` | Admin, Manager |
| **set_ocr_language** | Set the OCR language for a channel | `!set_ocr_language #channel language` | Admin, Manager |
| **add_ocr_response_channel** | Add a channel where the bot will post OCR analysis results | `!add_ocr_response_channel #channel [language]` | Admin, Manager |
| **remove_ocr_response_channel** | Remove a channel from the OCR response list | `!remove_ocr_response_channel #channel` | Admin, Manager |
| **add_ocr_response_fallback** | Add a fallback channel for OCR responses | `!add_ocr_response_fallback #channel` | Admin, Manager |
| **remove_ocr_response_fallback** | Remove a channel from the OCR response fallback list | `!remove_ocr_response_fallback #channel` | Admin, Manager |

### Bot Configuration Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **set_prefix** | Change the command prefix for this server | `!set_prefix $` | Admin, Manager |
| **reset_prefix** | Reset the command prefix to default (!) | `!reset_prefix` | Admin, Manager |
| **server_info** | Display all bot configuration settings for this server | `!server_info` | Admin, Manager |

### Permissions Management Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **add_command_role** | Give a role or user permission to use a specific command | `!add_command_role <target> <command_name>` | Admin, Manager |
| **add_bot_manager** | Add a role or user as a bot manager with access to all non-system commands | `!add_bot_manager <target>` | Admin, Manager |
| **remove_command_role** | Remove a role or user's permission to use a specific command | `!remove_command_role <target> <command_name>` | Admin, Manager |
| **remove_bot_manager** | Remove a role or user from bot managers | `!remove_bot_manager <target>` | Admin, Manager |
| **add_category_permission** | Give a role or user permission to use all commands in a category | `!add_category_permission <target> <category>` | Admin, Manager |
| **remove_category_permission** | Remove a role or user's permission to use all commands in a category | `!remove_category_permission <target> <category>` | Admin, Manager |
| **list_categories** | List all available command categories | `!list_categories` | Admin, Manager |
| **add_to_blacklist** | Add a role or user to the blacklist to prevent using any commands | `!add_to_blacklist <target>` | Admin, Manager |
| **remove_from_blacklist** | Remove a role or user from the blacklist | `!remove_from_blacklist <target>` | Admin, Manager |
| **list_blacklist** | List all roles and users in the command permission blacklist | `!list_blacklist` | Admin, Manager |

### Pattern Management Commands

The bot can be configured to recognize specific text patterns and respond with appropriate solutions:

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **list_patterns** | List all configured patterns | `!list_patterns [verbosity]` | Admin, Manager |
| **add_response** | Add a new response template | `!add_response "solution text" [name] [note]` | Admin, Manager |
| **remove_response** | Remove an existing response | `!remove_response response_id_or_name` | Admin, Manager |
| **add_pattern_to_response** | Add a pattern to an existing response | `!add_pattern_to_response response_id_or_name "pattern" [flags] [name] [url]` | Admin, Manager |
| **remove_pattern_from_response** | Remove a pattern from a response | `!remove_pattern_from_response response_id_or_name pattern_id` | Admin, Manager |
| **view_response** | View details of a specific response | `!view_response response_id_or_name` | Admin, Manager |
| **extract_text** | Extract text from an image for testing | `!extract_text [url]` | Admin, Manager |

### System Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **help** | Show info about the bot and its features | `!help [command]` | Everyone |
| **helpmenu** | Interactive help menu with categories | `!helpmenu` | Everyone |
| **ping** | Check the bot's response time | `!ping` | Everyone |
| **uptime** | Show how long the bot has been running | `!uptime` | Everyone |
| **status** | Display bot status, queue, and statistics | `!status` | Everyone |
| **invite** | Get the bot's invite link | `!invite` | Everyone |
| **host** | Display system information about the host | `!host` | Bot Owner Only |
| **reload_patterns** | Reload the pattern database | `!reload_patterns` | Bot Owner Only |
| **shutdown** | Shut down the bot completely | `!shutdown` | Bot Owner Only |

### LLM Integration Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|-------------|
| **llm_provider** | Switch LLM provider | `!llm_provider <local\|google_ai>` | Bot Owner |
| **llm_set_api_key** | Set Google AI API key | `!llm_set_api_key <api_key>` | Bot Owner |
| **llm_status** | Show provider and model status | `!llm_status` | Manage Messages |
| **llm_models** | List available models | `!llm_models [filters]` | Manage Messages |
| **llm_select** | Select model by name or index | `!llm_select <model_name_or_number>` | Bot Owner |
| **ask** | Standard LLM query | `!ask <question>` | Manage Messages |
| **think** | LLM query with thinking prompt | `!think [<true\|false>] <question>` | Manage Guild |

### Chatbot Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|-------------|
| **chatbot_enable** | Enable chatbot in current channel | `!chatbot_enable` | Chatbot Enable |
| **chatbot_disable** | Disable chatbot mode | `!chatbot_disable` | Chatbot Disable |
| **chatbot_status** | Show config and stats | `!chatbot_status` | Chatbot Status |
| **chatbot_config** | View/modify settings | `!chatbot_config [setting] [value]` | Chatbot Config |
| **chatbot_clear_history** | Clear conversation history | `!chatbot_clear_history` | Chatbot Clear History |

### Moderation Commands

Manage channels and threads with automated cleanup:

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **watch_forum** | Add a channel to the watchlist for automatic thread purging | `!watch_forum <channel> <time_period>` | Admin, Manager |
| **unwatch_forum** | Remove a channel from the watchlist | `!unwatch_forum <channel>` | Admin, Manager |
| **purge_threads** | Manually purge inactive threads from a channel | `!purge_threads <channel> <time_period>` | Admin, Manager |
| **ignore_thread** | Add a thread to the ignore list to prevent it from being purged | `!ignore_thread <thread>` | Admin, Manager |
| **unignore_thread** | Remove a thread from the ignore list | `!unignore_thread <thread>` | Admin, Manager |
| **ignore_tag** | Add a thread tag to the ignore list to prevent threads with that tag from being purged | `!ignore_tag <tag_name>` | Admin, Manager |
| **unignore_tag** | Remove a thread tag from the ignore list | `!unignore_tag <tag_name>` | Admin, Manager |
| **list_thread_settings** | List thread management settings for this server | `!list_thread_settings [type]` | Admin, Manager |

[View Moderation Command Documentation](docs/commands/moderation.md)

## Thread Management Features

The bot can automatically or manually purge inactive threads from channels:

| Feature | Description |
|---------|-------------|
| **Thread Purging** | Automatically removes inactive threads after a configurable time period |
| **Manual Purging** | Command to manually purge inactive threads on demand |
| **Multiple Channel Support** | Works with text channels, forum channels, and voice channels |
| **Thread Ignoring** | Specific threads can be excluded from automatic purging |
| **Tag Protection** | Threads with specific tags can be automatically protected from purging |
| **Configurable Thresholds** | Each channel can have its own inactivity threshold (days, hours, minutes, seconds) |
| **Pinned Thread Protection** | Pinned threads are never automatically purged |

### Permission Management

The bot features a comprehensive permission system:

- Role and user-based permissions for commands and command categories
- Permission blacklists to prevent specific roles or users from using commands
- Persistent storage of permission settings that survive bot restarts

For details, see the [Permissions Documentation](docs/commands/permissions.md).

## 🔐 Permission System

Mirrobot uses a tiered permission system:

1. **Bot Owner** - Has unlimited access to all commands on all servers
2. **Server Administrators** - Have access to all commands on their server
3. **Blacklist** - Prevents command access regardless of other permissions (except administrators)
4. **Bot Managers** - Roles or users granted access to all non-system commands
5. **Category Permissions** - Roles or users granted access to all commands in a specific category
6. **Command-specific Permissions** - Roles or users granted access to specific commands

## 🔍 OCR Processing

Mirrobot automatically processes images posted in designated OCR read channels:

1. When an image is posted, it's validated for format and size requirements
2. Valid images are queued for processing with smart backpressure handling
3. Multiple OCR workers process the queue in parallel for better performance
4. The text is extracted using Tesseract OCR and analyzed for known patterns
5. If a pattern is matched, the bot provides an appropriate response
6. Responses are posted either in the same channel or in designated response channels

## 📊 Stats and Monitoring

The bot tracks various statistics:

- Number of images processed
- Success/failure rate of OCR operations
- Queue statistics (current size, total enqueued, rejected, high watermark)
- Pattern match frequency
- Processing times and averages
- System resource usage (CPU, memory)

View statistics with the `!status` command.

## 🔧 Troubleshooting

- **Bot doesn't respond to commands**: Check if the prefix has been changed. Use `@Mirrobot help` to check.
- **OCR isn't working properly**: Make sure Tesseract is installed correctly and the path is set in environment variables.
- **Permission errors**: Check server_info to verify permissions are set correctly.
- **OCR processing is slow**: Consider increasing the `ocr_worker_count` in the config file for better performance.
- **Queue filling up**: If the `!status` command shows the queue is frequently near capacity, increase the `ocr_max_queue_size`.
- **Log files**: Check the bot_YYYY-MM-DD.log files in the logs directory for detailed error information.

## ⚠️ Error Handling

The bot includes robust error handling to maintain stability:

- Connection issues are automatically retried
- Queue backpressure prevents memory overload
- Config validation ensures proper setup
- Error logs are maintained in daily log files
- Critical errors are reported to the console

## 📚 Additional Information

- Images must be less than 500KB and at least 300x200 pixels for OCR processing
- The bot can also process images from URLs in messages
- Custom pattern recognition can be extended in the source code
- Comprehensive documentation is available in the `/docs` directory

## 🔄 Updates and Version History

- **v0.65 AI** - Added LLM integration with support for both local and Google AI providers, direct query commands (`!ask`, `!think`), and persistent conversational chatbot mode for channels. Includes automatic message/user indexing, context-aware responses, and intelligent embed formatting. See the detailed [AI Changelog](docs/changelogs/changelog_065AI.md) and [LLM Integration Guide](docs/llm_integration.md).
- **v0.5** - Refactored channel handling and enhanced thread purge validations. Updated ModerationCommandsCog and OCRConfigCog with improved time parsing, detailed logging, new manual purge command, and channel validation. Also refactored core bot setup and embed customization.
- **v0.45 Unstable** - Enhanced permission management with category permissions and blacklist support. Updated moderation commands to use the new @has_command_permission decorator with Manage Threads checks, added category-level commands (add/remove/list_category_permission) and blacklist management, and revised permissions configuration.
- **v0.4 Unstable** - Introduced Moderation Commands with automated thread purging (watch/unwatch, ignore/unignore, list settings), improved cog loading with enhanced logging/debug details, time parsing, embed formatting, and updated documentation in docs/commands/moderation.md.
- **v0.35** - Improved queue management, environment variable support, comprehensive documentation, configuration validation, enhanced embedding, and status command.
- **v0.30** - Parallel OCR processing using multiple workers.
- **v0.25** - First modular structure release. A lot of edits and improvements.
- **v0.20** - Final single-file release.
- **v0.15** - Initial version with basic features.
- For latest updates, visit the [GitHub repository](https://github.com/Mirrowel/Mirrobot-py)

## 📜 License

This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License. See the [LICENSE.MD](LICENSE.MD) file for details.
