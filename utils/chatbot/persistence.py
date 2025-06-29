"""
Handles persistence for the chatbot, including reading from and writing to JSON files.
"""

import json
import os
from typing import Any, Dict

from utils.logging_setup import get_logger

logger = get_logger()

class JsonStorageManager:
    """Manages reading from and writing to JSON files."""

    def read(self, file_path: str) -> Dict[str, Any]:
        """
        Reads a JSON file and returns its content.
        Returns an empty dictionary if the file doesn't exist or is invalid.
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading JSON file at {file_path}: {e}", exc_info=True)
            return {}

    def write(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        Writes data to a JSON file.
        Returns True on success, False on failure.
        """
        try:
            # Ensure the directory exists before writing
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.error(f"Error writing JSON file to {file_path}: {e}", exc_info=True)
            return False
