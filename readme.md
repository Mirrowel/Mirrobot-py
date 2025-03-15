# 🤖 Mirrobot Discord Bot

Mirrobot is an OCR (Optical Character Recognition) bot that scans images for text patterns and provides automatic responses to common issues. The bot is designed to help server administrators manage technical support channels by automatically analyzing screenshots.

## ✨ Features

- **Advanced OCR Processing**: Analyzes images posted in designated channels
- **Pattern Recognition**: Identifies common issues from error messages
- **Automatic Responses**: Provides helpful solutions for recognized problems
- **Flexible Configuration**: Customize command prefix and permissions
- **Role-based Permissions**: Grant specific access to commands by role or user

## 🛠️ Installation

1. Clone the repository
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install Tesseract OCR on your system:
   - Windows: Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
   - Linux: `sudo apt install tesseract-ocr`
   - macOS: `brew install tesseract`
4. Copy `config_example.json` to `config.json` and update it with your bot token

## 📚 Dependencies

The bot relies on the following libraries:

### External Libraries
- **discord.py**: Discord API wrapper for Python
- **pytesseract**: Python wrapper for Google's Tesseract OCR
- **Pillow (PIL)**: Python Imaging Library for image processing
- **aiohttp**: Asynchronous HTTP client/server framework
- **colorlog**: Log formatting with colors for console output
- **requests**: Simple HTTP library for API requests

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

## ⚙️ Configuration

The bot is configured through `config.json`:

```json
{
    "token": "YOUR_BOT_TOKEN_HERE",
    "command_prefix": "!",
    "ocr_read_channels": {},
    "ocr_response_channels": {},
    "ocr_response_fallback": {},
    "server_prefixes": {},
    "command_permissions": {}
}
```

## 📝 Available Commands

### OCR Configuration Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **add_ocr_read_channel** | Add a channel where the bot will scan images for OCR processing | `!add_ocr_read_channel #channel` | Admin, Manager |
| **remove_ocr_read_channel** | Remove a channel from the OCR reading list | `!remove_ocr_read_channel #channel` | Admin, Manager |
| **add_ocr_response_channel** | Add a channel where the bot will post OCR analysis results | `!add_ocr_response_channel #channel` | Admin, Manager |
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
| **add_command_role** | Give a role or user permission to use a specific command | `!add_command_role @role command_name` | Admin, Manager |
| **add_bot_manager** | Add a role or user as a bot manager with access to all non-system commands | `!add_bot_manager @role` | Admin, Manager |
| **remove_command_role** | Remove a role or user's permission to use a specific command | `!remove_command_role @role command_name` | Admin, Manager |
| **remove_bot_manager** | Remove a role or user from bot managers | `!remove_bot_manager @role` | Admin, Manager |

### System Commands

| Command | Description | Usage | Permissions |
|---------|-------------|-------|------------|
| **help** | Show help for bot commands | `!help [command]` | Everyone |
| **shutdown** | Shut down the bot completely | `!shutdown` | Bot Owner Only |

## 🔐 Permission System

Mirrobot uses a tiered permission system:

1. **Bot Owner** - Has unlimited access to all commands on all servers
2. **Server Administrators** - Have access to all commands on their server
3. **Bot Managers** - Roles or users granted access to all non-system commands
4. **Command-specific Permissions** - Roles or users granted access to specific commands

## 🔍 OCR Processing

Mirrobot automatically processes images posted in designated OCR read channels:

1. When an image is posted, the bot extracts text using Tesseract OCR
2. The text is analyzed for known patterns of common issues
3. If a pattern is matched, the bot provides an appropriate response
4. Responses are posted either in the same channel or in designated response channels

## 🔧 Troubleshooting

- **Bot doesn't respond to commands**: Check if the prefix has been changed. Use `@Mirrobot help` to check.
- **OCR isn't working properly**: Make sure Tesseract is installed correctly and the path is set in environment variables.
- **Permission errors**: Check server_info to verify permissions are set correctly.
- **Log files**: Check the bot_YYYY-MM-DD.log files for detailed error information.

## ⚠️ Error Handling

The bot includes robust error handling to maintain stability:
- Connection issues are automatically retried
- Error logs are maintained in daily log files
- Critical errors are reported to the console

## 📚 Additional Information

- Images must be less than 500KB and at least 300x200 pixels for OCR processing
- The bot can also process images from URLs in messages
- Custom pattern recognition can be extended in the source code
