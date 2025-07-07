# 🤖 Mirrobot Discord Bot [![License](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/) [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C0C0UZS4P)

Mirrobot is an OCR (Optical Character Recognition) bot that scans images for text patterns and provides automatic responses to common issues. The bot is designed to help server administrators manage technical support channels by automatically analyzing screenshots.

## ✨ Features

Mirrobot offers a comprehensive suite of features designed to enhance Discord server management and provide intelligent assistance:

-   **Advanced OCR Processing**: Automatically scans images for text, supporting multiple languages.
-   **Intelligent Pattern Recognition**: Identifies common issues and triggers automated responses based on extracted text.
-   **Flexible Response System**: Configurable responses linked to patterns, with options for custom text and external links.
-   **Powerful LLM Integration**: Connects to various Large Language Models (LLMs), including local and cloud-based providers, for advanced AI capabilities.
-   **Context-Aware Chatbot**: Provides a persistent, conversational AI experience in designated channels, maintaining conversation history and user context.
-   **Inline AI Responses**: Configurable bot responses to mentions, leveraging LLMs for dynamic and context-aware replies.
-   **Automated Log Analysis**: Scans game log files for known errors and provides instant solutions.
-   **Comprehensive Thread Management**: Automatically purges inactive threads from forum channels, with options to ignore specific threads or tags.
-   **Granular Permission System**: Tiered permission control for commands and categories, including role-based access, user-specific permissions, and a global blacklist.
-   **Customizable Bot Configuration**: Easily set command prefixes, configure OCR channels, and manage other server-specific settings.
-   **Performance Monitoring & Statistics**: Tracks OCR processing, queue metrics, and system resource usage for optimal performance.
-   **Robust Error Handling**: Ensures stability with automatic retries, queue backpressure, and detailed error logging.
-   **Secure Configuration**: Supports environment variables for sensitive data, enhancing security.

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

### Quick Setup

1. Copy `config_example.json` to `config.json`
2. **RECOMMENDED**: Create a `.env` file from `.env.example` and add your bot token there
3. Configure channels and permissions as needed

### Environment Variables (Recommended)

For security, use environment variables instead of storing sensitive data in config files:

- `DISCORD_BOT_TOKEN` - Your Discord bot token (**USE THIS INSTEAD OF STORING IN CONFIG**)
- `GOOGLE_AI_API_KEY` - Google AI API key for LLM features (optional)

### Key Configuration Options

#### Basic Settings
- **token**: Discord bot token (use environment variable `DISCORD_BOT_TOKEN`)
- **command_prefix**: Default command prefix (e.g., `"!"` for `!help`)
- **ocr_worker_count**: Number of parallel OCR workers (1-10, default: 2)
- **ocr_max_queue_size**: Maximum queued OCR requests (10-1000, default: 100)

#### Channel Configuration
All use format: `{"guild_id": [channel_id1, channel_id2]}`

- **ocr_read_channels**: Channels where the bot scans images for OCR
- **ocr_response_channels**: Channels where OCR results are posted
- **ocr_response_fallback**: Backup channels if primary response channels fail

#### Advanced Settings
- **server_prefixes**: Custom command prefixes per server
- **command_permissions**: Role-based command access control
- **ocr_channel_config**: OCR language settings per channel
- **maintenance**: Auto-restart and maintenance settings

### Getting Discord IDs

Enable Developer Mode in Discord, then:
- **Server/Guild ID**: Right-click server name → Copy ID
- **Channel ID**: Right-click channel → Copy ID  
- **Role ID**: Right-click role in server settings → Copy ID

### Security Best Practices

1. **Never commit** your actual `config.json` with real tokens to version control
2. **Always use** environment variables for sensitive data like tokens
3. **Restrict file permissions** on config files containing secrets

> 📖 **For detailed configuration examples and troubleshooting**, see [Configuration Guide](docs/configuration.md)

### LLM and Chatbot Configuration

#### LLM Configuration (`data/llm_config.json`)

- `base_url`: URL of local LLM server when using `provider: local`

- `timeout`, `max_retries`, `retry_delay`: Request settings

- `provider`: `local` or `google_ai`

- `google_ai_api_key`, `google_ai_model_name`: Google AI key and default model

- `servers`: Per-guild overrides (`enabled`, `preferred_model`, `last_used_model`)

> For a complete and detailed list of all commands, their usage, arguments, and permissions, please refer to the [Commands Documentation](docs/README.md).

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
