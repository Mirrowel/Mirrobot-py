"""
Log management utilities for Mirrobot.

This module provides functionality for managing log files, including rotation,
archiving, and cleanup of old log files.
"""

import os
import glob
import tarfile
import zstandard as zstd
import io
from collections import defaultdict
from datetime import datetime, timedelta
from utils.logging_setup import get_logger

logger = get_logger()

class LogManager:
    def __init__(self, log_dir=None, archive_logs=True):
        """
        Initialize the log manager.
        
        Args:
            log_dir (str, optional): Directory containing log files. If None, uses 'logs' in project root.
            archive_logs (bool): Whether to archive old logs.
        """
        if log_dir is None:
            self.log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        else:
            self.log_dir = log_dir
            
        self.archive_logs = archive_logs
        
        if self.archive_logs:
            self.archive_dir = os.path.join(self.log_dir, 'archive')
            os.makedirs(self.archive_dir, exist_ok=True)

    def cleanup_old_logs(self):
        """
        Clean up and archive old log files based on a tiered monthly strategy.
        - Logs from the current month are kept as is.
        - Logs from the previous month are individually compressed.
        - Logs older than the previous month are bundled into monthly tar.zst archives.
        - Individually archived logs are re-archived into monthly archives when they become old enough.
        """
        if not self.archive_logs or not os.path.exists(self.log_dir):
            return (0, 0)

        today = datetime.now()
        start_of_current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_previous_month = (start_of_current_month - timedelta(days=1)).replace(day=1)

        logs_by_month = defaultdict(list)
        
        # Include both .log and .zst files in the scan
        log_files = glob.glob(os.path.join(self.log_dir, 'bot_*.log'))
        archived_logs = glob.glob(os.path.join(self.archive_dir, 'bot_*.log.zst'))
        all_files = log_files + archived_logs

        for log_file in all_files:
            try:
                filename = os.path.basename(log_file)
                if filename.endswith('.zst'):
                    date_str = filename[4:-8] # For 'bot_YYYY-MM-DD.log.zst'
                else:
                    date_str = filename[4:-4] # For 'bot_YYYY-MM-DD.log'
                
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                
                if file_date >= start_of_current_month:
                    continue # Skip current month's logs
                
                logs_by_month[file_date.strftime('%Y-%m')].append(log_file)

            except ValueError:
                logger.warning(f"Could not parse date from log file: {log_file}")
                continue
        
        cleaned_count = 0
        error_count = 0

        for month_str, files in logs_by_month.items():
            month_date = datetime.strptime(month_str, '%Y-%m')
            
            if month_date >= start_of_previous_month:
                # Individually archive previous month's logs if they are not already archived
                for log_file in files:
                    if log_file.endswith('.zst'):
                        continue
                    try:
                        self._archive_individual_log(log_file)
                        os.remove(log_file)
                        cleaned_count += 1
                    except Exception as e:
                        logger.error(f"Error archiving individual log {log_file}: {e}")
                        error_count += 1
            else:
                # Create or update monthly archive for older logs
                try:
                    self._create_monthly_archive(month_str, files)
                    for log_file in files:
                        os.remove(log_file)
                    cleaned_count += len(files)
                except Exception as e:
                    logger.error(f"Error creating/updating monthly archive for {month_str}: {e}")
                    error_count += 1
        
        logger.info(f"Log cleanup complete: {cleaned_count} files processed, {error_count} errors")
        return (cleaned_count, error_count)

    def _archive_individual_log(self, log_file):
        """Compresses a single log file using zstandard."""
        archive_path = os.path.join(self.archive_dir, f"{os.path.basename(log_file)}.zst")
        cctx = zstd.ZstdCompressor(level=9)
        with open(log_file, 'rb') as f_in, open(archive_path, 'wb') as f_out:
            with cctx.stream_writer(f_out) as compressor:
                compressor.write(f_in.read())
        logger.debug(f"Archived individual log: {log_file} -> {archive_path}")

    def _create_monthly_archive(self, month_str, files):
        """Creates or updates a .tar.zst archive for a given month's log files."""
        archive_path = os.path.join(self.archive_dir, f"archive_{month_str}.tar.zst")
        
        # Decompress individual .zst files in memory
        dctx = zstd.ZstdDecompressor()
        
        cctx = zstd.ZstdCompressor(level=15, threads=-1)
        with open(archive_path, 'wb') as f_out:
            with cctx.stream_writer(f_out) as compressor:
                with tarfile.open(fileobj=compressor, mode='w:') as tar:
                    for log_file in files:
                        arcname = os.path.basename(log_file)
                        if log_file.endswith('.zst'):
                            # Decompress and add to tar
                            arcname = arcname[:-4] # Remove .zst extension
                            with open(log_file, 'rb') as f_in:
                                with dctx.stream_reader(f_in) as reader:
                                    log_content = reader.read()
                                    tarinfo = tarfile.TarInfo(name=arcname)
                                    tarinfo.size = len(log_content)
                                    tar.addfile(tarinfo, fileobj=io.BytesIO(log_content))
                        else:
                            # Add .log file directly
                            tar.add(log_file, arcname=arcname)
                            
        logger.info(f"Created/Updated monthly archive for {month_str}: {archive_path}")
        
    def get_log_stats(self):
        """
        Get statistics about log files.
        
        Returns:
            dict: Statistics about log files
        """
        if not os.path.exists(self.log_dir):
            return {"error": "Log directory does not exist"}
            
        log_files = glob.glob(os.path.join(self.log_dir, 'bot_*.log'))
        archive_files = []
        if self.archive_logs:
            archive_files.extend(glob.glob(os.path.join(self.archive_dir, '*.zst')))
            archive_files.extend(glob.glob(os.path.join(self.archive_dir, '*.tar.zst')))

        total_size_logs = sum(os.path.getsize(f) for f in log_files)
        total_size_archives = sum(os.path.getsize(f) for f in archive_files)
        
        return {
            "log_count": len(log_files),
            "log_size_mb": total_size_logs / (1024 * 1024),
            "archive_count": len(archive_files),
            "archive_size_mb": total_size_archives / (1024 * 1024),
            "total_size_mb": (total_size_logs + total_size_archives) / (1024 * 1024)
        }
