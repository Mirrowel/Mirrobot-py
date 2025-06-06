# This file makes the cogs directory a package
from discord.ext import commands
import os
import sys
import importlib
import asyncio
from utils.logging_setup import get_logger

logger = get_logger()

# List of cogs to load
cogs = [
    'bot_config',
    'llm_commands',
    'moderation_commands',
    'ocr_config',
    'pattern_commands',
    'permission_commands',
    'system_commands'
]
