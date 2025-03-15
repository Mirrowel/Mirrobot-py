"""
Constants and utilities for the Mirrobot application
"""
import datetime

# Bot information
BOT_VERSION = "0.25"
BOT_NAME = "Mirrobot"

# Author information 
AUTHOR_NAME = "Mirrowel"
AUTHOR_URL = "https://github.com/Mirrowel"
AUTHOR_ICON_URL = "https://avatars.githubusercontent.com/u/28632877"

# Repository information
REPO_URL = "https://github.com/Mirrowel/Mirrobot-py"
GITHUB_ICON_URL = "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"

# Uptime tracking
BOT_START_TIME = datetime.datetime.now(datetime.timezone.utc)

def get_uptime():
    """
    Get the bot's current uptime as a formatted string.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - BOT_START_TIME
    
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    
    return ", ".join(parts)
