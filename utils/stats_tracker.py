"""
Stats tracking utilities for Mirrobot.

This module provides functionality for tracking various statistics about OCR processing,
such as processing times, success rates, and total processed images.
"""

import time
from collections import deque
import threading

# Store OCR processing times in a thread-safe way
_ocr_times_lock = threading.RLock()
_ocr_times = deque(maxlen=100)  # Store the last 100 OCR processing times
_total_processed = 0
_successful_processed = 0

def record_ocr_time(seconds):
    """
    Record the time taken to process an OCR request.
    
    This function is thread-safe and stores processing times in a rotating buffer
    of the last 100 OCR operations.
    
    Args:
        seconds (float): The number of seconds the OCR operation took
    """
    global _total_processed
    with _ocr_times_lock:
        _ocr_times.append(seconds)
        _total_processed += 1

def get_ocr_stats():
    """
    Get statistics about OCR processing performance.
    
    Returns:
        dict: A dictionary containing the following statistics:
            - avg_time (float): Average processing time in seconds
            - min_time (float): Minimum processing time in seconds
            - max_time (float): Maximum processing time in seconds
            - total_processed (int): Total number of images processed
            - success_rate (float): Percentage of successful OCR operations
    """
    with _ocr_times_lock:
        times = list(_ocr_times)
        stats = {
            "avg_time": sum(times) / len(times) if times else 0,
            "min_time": min(times) if times else 0,
            "max_time": max(times) if times else 0,
            "total_processed": _total_processed,
            "success_rate": (_successful_processed / _total_processed * 100) if _total_processed > 0 else 0
        }
    return stats

class OCRTimingContext:
    """
    Context manager for timing OCR operations and recording statistics.
    
    Example:
        ```python
        with OCRTimingContext() as timer:
            # Perform OCR operation
            result = do_ocr_processing()
            
            # If successful, mark it
            if result:
                timer.mark_successful()
        ```
    """
    def __init__(self):
        """Initialize the OCR timing context."""
        self.elapsed = 0
        self.start_time = None
        self.successful = False
    
    def __enter__(self):
        """
        Start timing when entering the context.
        
        Returns:
            self: Returns self for method chaining
        """
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Record timing when exiting the context.
        
        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        if self.start_time:
            self.elapsed = time.time() - self.start_time
        # Only record stats if operation was successful
        if self.successful:
            record_ocr_time(self.elapsed)
    
    def mark_successful(self):
        """Mark the current OCR operation as successful."""
        global _successful_processed
        with _ocr_times_lock:
            self.successful = True
            _successful_processed += 1
