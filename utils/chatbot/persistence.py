"""
Handles persistence for the chatbot, including reading from and writing to JSON files.
"""

import json
import os
import shutil
import time
from collections import defaultdict
from threading import Lock
from typing import Any, Dict

from utils.logging_setup import get_logger

logger = get_logger()

class JsonStorageManager:
    """
    Manages reading from and writing to JSON files with file-level locking
    to ensure thread safety.
    """

    def __init__(self):
        self._file_locks = defaultdict(Lock)

    def read(self, file_path: str) -> Dict[str, Any]:
        """
        Reads a JSON file and returns its content.
        Returns an empty dictionary if the file doesn't exist or is invalid.
        Moves corrupted files to a .bak file.
        """
        with self._file_locks[file_path]:
            if not os.path.exists(file_path):
                return {}
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {file_path}: {e}", exc_info=True)
                try:
                    # Backup the corrupted file
                    backup_path = f"{file_path}.{int(time.time())}.bak"
                    shutil.move(file_path, backup_path)
                    logger.info(f"Backed up corrupted file to {backup_path}")
                except (IOError, shutil.Error) as backup_e:
                    logger.error(f"Could not back up corrupted file {file_path}: {backup_e}", exc_info=True)
                return {}
            except IOError as e:
                logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
                return {}

    def write(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        Writes data to a JSON file atomically.
        Returns True on success, False on failure.
        """
        with self._file_locks[file_path]:
            try:
                # Ensure the directory exists before writing
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Write to a temporary file first
                temp_file_path = f"{file_path}.tmp"
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Atomically rename the temporary file to the final destination
                os.replace(temp_file_path, file_path)
                
                return True
            except (IOError, os.error) as e:
                logger.error(f"Error writing JSON file to {file_path}: {e}", exc_info=True)
                return False
