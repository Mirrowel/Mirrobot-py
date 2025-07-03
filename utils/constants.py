"""
Constants module for Mirrobot.

This module defines various constants and utility functions used throughout the bot,
ensuring consistent values across the application.
"""

import time
from datetime import datetime, timedelta

# Bot information
BOT_VERSION = "0.66 AI"
BOT_NAME = "Mirrobot"

# Author information
AUTHOR_NAME = "Mirrowel"
AUTHOR_URL = "https://github.com/Mirrowel"
AUTHOR_ICON_URL = "https://avatars.githubusercontent.com/u/28632877"

# Repository information
REPO_URL = "https://github.com/Mirrowel/Mirrobot-py"
GITHUB_ICON_URL = "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"

# Startup time for uptime calculation
_startup_time = time.time()

def get_uptime():
    """
    Calculate and format the bot's uptime.
    
    Returns:
        str: Formatted string representing the bot's uptime (e.g., "5 days, 3 hours, 2 minutes, 10 seconds")
    
    Example:
        ```python
        uptime_str = get_uptime()
        await ctx.send(f"Bot has been running for {uptime_str}")
        ```
    """
    # Calculate uptime in seconds
    uptime_seconds = int(time.time() - _startup_time)
    
    # Convert to timedelta for easier formatting
    uptime_delta = timedelta(seconds=uptime_seconds)
    
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Format the uptime string
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts:  # Always include seconds if no other parts
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
    return ", ".join(parts)
