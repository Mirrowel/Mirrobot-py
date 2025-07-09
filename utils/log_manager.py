"""
Log management utilities for Mirrobot.

This module provides functionality for managing log files, including rotation,
archiving, and cleanup of old log files.
"""

import os
import glob
import gzip
import time
import shutil
from datetime import datetime, timedelta
from utils.logging_setup import get_logger

logger = get_logger()

class LogManager:
    def __init__(self, log_dir=None, max_log_age_days=30, archive_logs=True):
        """
        Initialize the log manager.
        
        Args:
            log_dir (str, optional): Directory containing log files. If None, uses 'logs' in project root.
            max_log_age_days (int): Maximum age of log files in days before cleanup.
            archive_logs (bool): Whether to archive old logs before removal.
        """
        if log_dir is None:
            # Default to 'logs' directory in project root
            self.log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        else:
            self.log_dir = log_dir
            
        self.max_log_age_days = max_log_age_days
        self.archive_logs = archive_logs
        
        # Create archive directory if it doesn't exist
        if self.archive_logs:
            self.archive_dir = os.path.join(self.log_dir, 'archive')
            os.makedirs(self.archive_dir, exist_ok=True)
    
    def cleanup_old_logs(self):
        """
        Clean up log files older than max_log_age_days.
        
        Returns:
            tuple: (cleaned_count, error_count)
        """
        if not os.path.exists(self.log_dir):
            logger.warning(f"Log directory does not exist: {self.log_dir}")
            return (0, 0)
            
        cutoff_date = datetime.now() - timedelta(days=self.max_log_age_days)
        cleaned_count = 0
        error_count = 0
        
        # Find all log files in the log directory
        log_files = glob.glob(os.path.join(self.log_dir, 'bot_*.log'))
        
        for log_file in log_files:
            try:
                # Extract the date from the log filename (assumes format like bot_YYYY-MM-DD.log)
                filename = os.path.basename(log_file)
                if not self._is_old_log(log_file, cutoff_date):
                    continue
                    
                # Archive the log file if configured
                if self.archive_logs:
                    self._archive_log(log_file)
                
                # Delete the original log file
                os.remove(log_file)
                cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Error cleaning up log file {log_file}: {e}")
                error_count += 1
                
        logger.info(f"Log cleanup complete: {cleaned_count} files cleaned, {error_count} errors")
        return (cleaned_count, error_count)
    
    def _is_old_log(self, log_file, cutoff_date):
        """
        Check if a log file is older than the cutoff date.
        
        Args:
            log_file (str): Path to log file
            cutoff_date (datetime): Cutoff date for old logs
            
        Returns:
            bool: True if the log file is older than the cutoff date
        """
        try:
            # First try to extract date from filename (format: bot_YYYY-MM-DD.log)
            filename = os.path.basename(log_file)
            if filename.startswith('bot_') and filename.endswith('.log'):
                date_str = filename[4:-4] # Extract YYYY-MM-DD
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                return file_date < cutoff_date
            
            # Fall back to file modification time
            mod_time = os.path.getmtime(log_file)
            mod_date = datetime.fromtimestamp(mod_time)
            return mod_date < cutoff_date
        except:
            # If we can't parse the date, use file modification time
            mod_time = os.path.getmtime(log_file)
            mod_date = datetime.fromtimestamp(mod_time)
            return mod_date < cutoff_date
    
    def _archive_log(self, log_file):
        """
        Archive a log file by compressing it and moving to archive directory.
        
        Args:
            log_file (str): Path to log file to archive
        """
        archive_path = os.path.join(self.archive_dir, f"{os.path.basename(log_file)}.gz")
        
        # Compress the log file
        with open(log_file, 'rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        logger.debug(f"Archived log file: {log_file} -> {archive_path}")
        
    def get_log_stats(self):
        """
        Get statistics about log files.
        
        Returns:
            dict: Statistics about log files
        """
        if not os.path.exists(self.log_dir):
            return {"error": "Log directory does not exist"}
            
        log_files = glob.glob(os.path.join(self.log_dir, '*.log'))
        archive_files = glob.glob(os.path.join(self.archive_dir, '*.gz')) if self.archive_logs else []
        
        total_size_logs = sum(os.path.getsize(f) for f in log_files)
        total_size_archives = sum(os.path.getsize(f) for f in archive_files)
        
        return {
            "log_count": len(log_files),
            "log_size_mb": total_size_logs / (1024 * 1024),
            "archive_count": len(archive_files),
            "archive_size_mb": total_size_archives / (1024 * 1024),
            "total_size_mb": (total_size_logs + total_size_archives) / (1024 * 1024)
        }
