"""
Resource monitoring utilities for Mirrobot.

This module provides functionality for tracking and managing system resources 
such as memory usage, disk space, and CPU utilization.
"""

import os
import psutil
import time
from threading import Thread, Event
from utils.logging_setup import get_logger

logger = get_logger()

class ResourceMonitor:
    def __init__(self, warning_threshold=80, critical_threshold=90, check_interval=300):
        """
        Initialize the resource monitor.
        
        Args:
            warning_threshold (int): Percentage threshold for warning alerts
            critical_threshold (int): Percentage threshold for critical alerts
            check_interval (int): Time between checks in seconds
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.stop_event = Event()
        self.monitor_thread = None
        
    def start(self):
        """Start the resource monitoring thread"""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_event.clear()
            self.monitor_thread = Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Resource monitoring started")
            
    def stop(self):
        """Stop the resource monitoring thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_event.set()
            self.monitor_thread.join(timeout=5.0)
            logger.info("Resource monitoring stopped")
            
    def _monitor_loop(self):
        """Main monitoring loop that checks system resources periodically"""
        while not self.stop_event.is_set():
            try:
                self._check_memory()
                self._check_disk_space()
                self._check_log_size()
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
            
            # Sleep until next check interval or until stopped
            self.stop_event.wait(self.check_interval)
    
    def _check_memory(self):
        """Check system memory usage and log warnings if above thresholds"""
        memory = psutil.virtual_memory()
        percent_used = memory.percent
        
        if percent_used > self.critical_threshold:
            logger.warning(f"CRITICAL: Memory usage at {percent_used}% - Performance may be severely impacted")
        elif percent_used > self.warning_threshold:
            logger.info(f"WARNING: Memory usage at {percent_used}% - Consider restarting if OCR performance degrades")
            
    def _check_disk_space(self):
        """Check available disk space and log warnings if low"""
        disk = psutil.disk_usage('/')
        if disk.percent > self.critical_threshold:
            logger.warning(f"CRITICAL: Disk usage at {disk.percent}% - Free space very low")
        elif disk.percent > self.warning_threshold:
            logger.info(f"WARNING: Disk usage at {disk.percent}% - Consider clearing logs or temporary files")
    
    def _check_log_size(self):
        """Check size of log directory and log warnings if large"""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        if not os.path.exists(log_dir):
            return
            
        total_size = sum(os.path.getsize(os.path.join(log_dir, f)) for f in os.listdir(log_dir) if f.endswith('.log'))
        size_mb = total_size / (1024 * 1024)
        
        if size_mb > 500:  # 500 MB threshold
            logger.warning(f"Log files total {size_mb:.2f} MB - Consider archiving old logs")

def get_system_info():
    """
    Get current system resource information.
    
    Returns:
        dict: Dictionary containing system resource information
    """
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        return {
            "memory_used": memory.percent,
            "memory_available_mb": memory.available / (1024 * 1024),
            "disk_used": disk.percent,
            "disk_free_gb": disk.free / (1024 * 1024 * 1024),
            "cpu_percent": cpu_percent,
            "pid": os.getpid(),
            "process_memory_mb": psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {}
