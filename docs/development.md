# Development Guide

This document provides information for developers who want to contribute to Mirrobot or understand its internal architecture.

## Project Structure

The Mirrobot codebase is organized into several key directories:

- `/` - Root directory with main.py and project-level files
- `/core/` - Core functionality modules
- `/cogs/` - Discord command implementations
- `/utils/` - Utility functions and helper modules
- `/config/` - Configuration management
- `/docs/` - Documentation files

## Key Components

### Core Modules

- `core/bot.py` - Bot initialization and event handling
- `core/ocr.py` - OCR image processing logic
- `core/pattern_manager.py` - Pattern matching and management

### Command Cogs

- `cogs/system_commands.py` - General bot commands
- `cogs/ocr_config.py` - OCR configuration commands
- `cogs/pattern_commands.py` - Pattern management commands
- `cogs/permission_commands.py` - Permission management commands
- `cogs/bot_config.py` - Bot configuration commands

### Utilities

- `utils/stats_tracker.py` - Performance statistics tracking
- `utils/permissions.py` - Permission checking functions
- `utils/embed_helper.py` - Discord embed creation utilities
- `utils/constants.py` - Global constants
- `utils/logging_setup.py` - Logging configuration

## Development Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Mirrowel/Mirrobot-py.git
   cd Mirrobot-py
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

5. Set up configuration:
   ```bash
   cp config_example.json config.json
   cp .env.example .env
   ```
   
6. Edit the configuration files to add your bot token and settings

## Development Guidelines

### Code Style

- Follow PEP 8 guidelines for Python code
- Use Google-style docstrings for functions and classes
- Keep lines to a maximum of 100 characters
- Use descriptive variable and function names

### Adding New Commands

1. Choose the appropriate cog or create a new one if needed
2. Use the `@commands.command()` decorator for commands
3. Add help text using the `help` parameter
4. Use the `@command_category()` decorator to categorize commands
5. Add proper permission checks with `@has_command_permission()`
6. Include detailed docstrings for command functions

Example:

```python
@commands.command(name='my_command', help='Description of what my command does.\nArguments: arg1 - Description of arg1\nExample: !my_command value')
@has_command_permission()
@command_category("MyCategory")
async def my_command(self, ctx, arg1: str):
    """
    Detailed description of what this command does.
    
    Args:
        ctx (commands.Context): The command context
        arg1 (str): Description of arg1
    """
    # Command implementation
    await ctx.send(f"You provided: {arg1}")
```

### Error Handling

- Use try/except blocks for operations that might fail
- Log errors with appropriate severity levels
- Provide helpful error messages to users
- Handle permission denials gracefully

### Logging

- Use the logger from `utils.logging_setup` for all logging
- Choose appropriate log levels:
  - DEBUG: Detailed information for debugging
  - INFO: Confirmation that things are working
  - WARNING: Something unexpected happened but the application can continue
  - ERROR: An error occurred that prevents a function from working
  - CRITICAL: A serious error that might prevent the application from continuing

### Testing

- Test commands manually before submitting pull requests
- Write unit tests for utility functions
- Test with different permission setups to ensure access control works

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes, following code style guidelines
4. Update documentation if necessary
5. Test your changes thoroughly
6. Submit a pull request with a clear description of the changes

## Documentation

- Update the in-code docstrings for any functions you modify
- Update the corresponding command documentation in `/docs/`
- Add examples where appropriate
- Document any new configuration options or features
