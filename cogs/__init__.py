# This file makes the cogs directory a package
import os
from utils.logging_setup import get_logger

logger = get_logger()

# --- Dynamic Cog Loader ---

# A blacklist of cogs to prevent from loading automatically.
# This is useful for testing cogs or cogs that are not ready.
COGS_BLACKLIST = {
    'testing_commands',
    'log_analysis_commands',
    'maintenance',
}

# Dynamically discover and load cogs
cogs = []
cogs_dir = os.path.dirname(__file__)

for filename in os.listdir(cogs_dir):
    # Check if it's a Python file, not __init__.py, and not in the blacklist
    if filename.endswith('.py') and filename != '__init__.py':
        cog_name = filename[:-3]  # Remove .py extension
        if cog_name not in COGS_BLACKLIST:
            cogs.append(cog_name)
            logger.debug(f"Discovered cog: {cog_name}")
        else:
            logger.info(f"Skipping blacklisted cog: {cog_name}")

logger.info(f"Dynamically discovered {len(cogs)} cogs to be loaded: {', '.join(cogs)}")
