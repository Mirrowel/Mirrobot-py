"""
Module for tracking and maintaining various bot statistics
"""
import time
from collections import deque
from threading import Lock

# Global stats tracking
_stats = {
    'ocr': {
        'processing_times': deque(maxlen=100),  # Store last 100 processing times
        'total_processed': 0,
        'avg_time': 0.0
    }
}

_stats_lock = Lock()

def record_ocr_time(seconds):
    """
    Record the time taken to process an OCR request
    
    Args:
        seconds (float): Time taken in seconds
    """
    with _stats_lock:
        _stats['ocr']['processing_times'].append(seconds)
        _stats['ocr']['total_processed'] += 1
        
        # Update average
        if _stats['ocr']['processing_times']:
            _stats['ocr']['avg_time'] = sum(_stats['ocr']['processing_times']) / len(_stats['ocr']['processing_times'])

def get_ocr_stats():
    """
    Get current OCR statistics
    
    Returns:
        dict: Statistics about OCR processing
    """
    with _stats_lock:
        return {
            'avg_time': _stats['ocr']['avg_time'],
            'total_processed': _stats['ocr']['total_processed'],
            'recent_times': list(_stats['ocr']['processing_times'])
        }

class OCRTimingContext:
    """Context manager to time OCR operations"""
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        record_ocr_time(elapsed)
