"""
Maintenance cog for Mirrobot.

This module contains tasks and commands related to bot maintenance,
including automatic restart after specified uptime.
"""

import os
import sys
import asyncio
import discord
from discord.ext import commands, tasks
import time
import logging
import re

from utils.constants import get_uptime, get_uptime_seconds
from utils.permissions import has_command_permission, command_category
from config.config_manager import save_config

logger = logging.getLogger('mirrobot')

# Default values (will be used if not found in config)
DEFAULT_RESTART_THRESHOLD_HOURS = 24  # Default: restart after 24 hours
DEFAULT_CHECK_INTERVAL_MINUTES = 15   # Check uptime every 15 minutes

class MaintenanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Initialize maintenance config if not present
        config = bot.config
        if 'maintenance' not in config:
            config['maintenance'] = {}
            
        maintenance_config = config['maintenance']
        
        # Get restart threshold from config (seconds) or calculate from default hours
        self.restart_threshold_seconds = maintenance_config.get(
            'restart_threshold_seconds', 
            DEFAULT_RESTART_THRESHOLD_HOURS * 3600
        )
        
        # Get check interval from config or use default
        self.check_interval_minutes = maintenance_config.get(
            'check_interval_minutes',
            DEFAULT_CHECK_INTERVAL_MINUTES
        )
        
        # Get auto-restart enabled setting from config or use default (True)
        self.auto_restart_enabled = maintenance_config.get('auto_restart_enabled', True)
        
        # Update config with current values (in case they were missing)
        self.save_settings_to_config()
        
        # Start the auto-restart task with the interval from config
        self.auto_restart_task.change_interval(minutes=self.check_interval_minutes)
        self.auto_restart_task.start()
        
        logger.info(f"Auto-restart initialized: Will restart after {self.get_threshold_display()}")
    
    def save_settings_to_config(self):
        """Save the current maintenance settings to the config file"""
        config = self.bot.config
        if 'maintenance' not in config:
            config['maintenance'] = {}
            
        config['maintenance']['restart_threshold_seconds'] = self.restart_threshold_seconds
        config['maintenance']['check_interval_minutes'] = self.check_interval_minutes
        config['maintenance']['auto_restart_enabled'] = self.auto_restart_enabled
        
        # Save to file
        save_config(config)
        logger.debug("Maintenance settings saved to config file")
    
    def cog_unload(self):
        """Clean up resources when cog is unloaded"""
        self.auto_restart_task.cancel()
    
    def get_threshold_display(self):
        """Get a human-readable string for the restart threshold"""
        hours, remainder = divmod(self.restart_threshold_seconds, 3600)
        minutes = remainder // 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            
        return " and ".join(parts) if parts else "0 minutes"
    
    @tasks.loop()  # Interval will be set in __init__
    async def auto_restart_task(self):
        """Task to automatically restart the bot after running for specified time"""
        if not self.auto_restart_enabled:
            return
            
        # Get current uptime in seconds
        uptime_seconds = get_uptime_seconds()
        
        if uptime_seconds >= self.restart_threshold_seconds:
            logger.warning(f"Auto-restart triggered after {uptime_seconds/3600:.2f} hours of uptime")
            
            # For automatic restarts, don't send messages to channels
            # Just log and restart
            await self.restart_bot("Scheduled maintenance restart")

    @auto_restart_task.before_loop
    async def before_auto_restart(self):
        """Wait until the bot is ready before starting the auto-restart task"""
        await self.bot.wait_until_ready()
    
    async def restart_bot(self, reason="Manually triggered restart"):
        """
        Restart the bot process
        
        Args:
            reason (str): Reason for restart, for logging
        """
        logger.info(f"Restarting bot: {reason}")
        
        try:
            # Close the bot connection
            await self.bot.close()
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")
            
        # Restart using the same command that started the bot
        executable = sys.executable
        script = sys.argv[0]
        args = sys.argv[1:]
        
        logger.info(f"Restarting with command: {executable} {script} {' '.join(args)}")
        
        # Replace current process with new process
        os.execv(executable, [executable, script] + args)
    
    @commands.command(name="restart", help="Restart the bot.\nNo additional arguments required.\nExample: !restart")
    @has_command_permission()
    @commands.is_owner()  # Only bot owner can use this command
    @command_category("Maintenance")
    async def restart_cmd(self, ctx):
        """Command to manually restart the bot"""
        embed = discord.Embed(
            title="🔄 Bot Restart",
            description="Bot is restarting now. Please wait a moment.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        
        # Log the manual restart event
        logger.info(f"Manual restart triggered by {ctx.author} (ID: {ctx.author.id})")
        
        # Restart with a small delay to allow the message to be sent
        await asyncio.sleep(1)
        # For manual restart, do send notifications
        await self.restart_bot(f"Manual restart by {ctx.author}")

    @commands.command(name="toggle_auto_restart", help="Toggle automatic restart functionality.\nNo additional arguments required.\nExample: !toggle_auto_restart")
    @has_command_permission()
    @commands.is_owner()  # Only bot owner can use this command
    @command_category("Maintenance")
    async def toggle_auto_restart(self, ctx):
        """Command to toggle automatic restart functionality"""
        self.auto_restart_enabled = not self.auto_restart_enabled
        status = "enabled" if self.auto_restart_enabled else "disabled"
        
        # Save the updated setting to config
        self.save_settings_to_config()
        
        embed = discord.Embed(
            title="⚙️ Auto-Restart Settings",
            description=f"Automatic restart has been **{status}**",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        logger.info(f"Auto-restart {status} by {ctx.author}")
    
    @commands.command(name="set_restart_time", help="Set the auto-restart interval.\nArguments: time - Format examples: 24h, 12h30m\nExample: !set_restart_time 12h")
    @has_command_permission()
    @commands.is_owner()  # Only bot owner can use this command
    @command_category("Maintenance")
    async def set_restart_time(self, ctx, time_str: str):
        """Command to set the auto-restart time interval"""
        # Parse the time string (format: 24h, 12h30m, 30m, etc.)
        pattern = re.compile(r'(?:(\d+)h)?(?:(\d+)m)?$')
        match = pattern.match(time_str)
        
        if not match or not any(match.groups()):
            await ctx.send("❌ Invalid time format. Use format like `24h`, `12h30m`, or `45m`.")
            return
            
        # Extract hours and minutes
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        
        # Convert to seconds
        total_seconds = (hours * 3600) + (minutes * 60)
        
        if total_seconds < 60*30:  # Minimum 30 minutes
            await ctx.send("❌ Restart interval must be at least 30 minutes.")
            return
            
        # Update the threshold
        self.restart_threshold_seconds = total_seconds
        
        # Save the updated setting to config
        self.save_settings_to_config()
        
        # Format response
        threshold_display = self.get_threshold_display()
        
        embed = discord.Embed(
            title="⏱️ Auto-Restart Settings Updated",
            description=f"Bot will now automatically restart after **{threshold_display}** of uptime.",
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed)
        logger.info(f"Auto-restart interval set to {threshold_display} by {ctx.author}")

    @commands.command(name="show_restart_settings", help="Show current restart settings.\nNo arguments required.\nExample: !show_restart_settings")
    @has_command_permission()
    @commands.is_owner()  # Only bot owner can use this command
    @command_category("Maintenance")
    async def show_restart_settings(self, ctx):
        """Show current restart settings"""
        status = "enabled" if self.auto_restart_enabled else "disabled"
        threshold_display = self.get_threshold_display()
        
        embed = discord.Embed(
            title="⚙️ Auto-Restart Settings",
            description=f"Current auto-restart configuration",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Status", value=f"Auto-restart is **{status}**", inline=False)
        embed.add_field(name="Interval", value=f"Bot will restart after **{threshold_display}** of uptime", inline=False)
        embed.add_field(name="Check Frequency", value=f"Bot checks uptime every **{self.check_interval_minutes} minutes**", inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot):
    """Setup function for the maintenance cog"""
    await bot.add_cog(MaintenanceCog(bot))
