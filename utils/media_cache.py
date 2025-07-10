import aiohttp
import asyncio
import random
import hashlib
import json
import os
import time
from typing import Optional, List

from utils.logging_setup import get_logger

logger = get_logger()
CACHE_FILE = "data/media_cache.json"

class MediaCacheManager:
    """Manages the caching of media files to third-party services."""

    def __init__(self, config: dict, bot):
        self.config = config.get('media_caching', {})
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.services = self.config.get('services', [])
        self.pixeldrain_api_key = self.config.get('pixeldrain_api_key')
        self.upload_timeout = self.config.get('upload_timeout_seconds', 30)
        self.cache = self._load_cache()
        self._lock = asyncio.Lock()

    def _load_cache(self) -> dict:
        """Loads the media cache from a JSON file and purges expired entries."""
        if not os.path.exists(CACHE_FILE):
            return {}
        
        with open(CACHE_FILE, 'r') as f:
            try:
                cache = json.load(f)
            except json.JSONDecodeError:
                return {}
        
        now = time.time()
        purged_cache = {
            h: entry for h, entry in cache.items()
            if isinstance(entry, dict) and 'expiry_timestamp' in entry and (entry['expiry_timestamp'] is None or entry['expiry_timestamp'] > now)
        }
        
        if len(purged_cache) < len(cache):
            logger.info(f"Purged {len(cache) - len(purged_cache)} expired entries from media cache.")
            # This is a bit of a hack, but it prevents a circular call
            # during initialization.
            if hasattr(self, 'cache'):
                self.cache = purged_cache
                self._save_cache()
            
        return purged_cache

    def _save_cache(self):
        """Saves the media cache to a JSON file."""
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.cache, f, indent=4)

    async def close_session(self):
        """Closes the aiohttp session."""
        await self.session.close()

    async def cache_url(self, url: str) -> str:
        """
        Caches a media URL to a configured third-party service.

        Args:
            url (str): The URL of the media to cache.

        Returns:
            str: The new cached URL, or the original URL if caching fails.
        """
        if not self.config.get('enabled') or not self.services:
            return url

        async with self._lock:
            try:
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download media from {url}: HTTP {response.status}")
                        return url
                    file_data = await response.read()
                    filename = url.split('/')[-1].split('?')[0]
            except Exception as e:
                logger.error(f"Error downloading media from {url}: {e}")
                return url

            file_hash = hashlib.sha256(file_data).hexdigest()
            cached_entry = self.cache.get(file_hash)

            if cached_entry:
                expiry = cached_entry.get('expiry_timestamp')
                if not expiry or expiry > time.time():
                    logger.info(f"Found valid cached URL for {url} (hash: {file_hash})")
                    return cached_entry['url']
                else:
                    logger.info(f"Cached URL for {url} has expired. Re-uploading.")

            shuffled_services = random.sample(self.services, len(self.services))

            for service in shuffled_services:
                try:
                    new_url = None
                    expiry_timestamp = None
                    if service == 'catbox':
                        new_url = await self._upload_to_catbox(file_data, filename)
                        if new_url:
                            expiry_timestamp = time.time() + (72 * 3600)
                    elif service == 'pixeldrain':
                        new_url = await self._upload_to_pixeldrain(file_data, filename)
                    else:
                        logger.warning(f"Unknown media caching service: {service}")
                        continue

                    if new_url:
                        logger.info(f"Successfully cached {url} to {service}: {new_url}")
                        self.cache[file_hash] = {
                            "url": new_url,
                            "expiry_timestamp": expiry_timestamp
                        }
                        self._save_cache()
                        return new_url
                except Exception as e:
                    logger.error(f"Failed to upload to {service}: {e}")
                    continue

            logger.warning(f"Failed to cache media from {url} to any service.")
            return url

    async def _upload_to_catbox(self, file_data: bytes, filename: str) -> Optional[str]:
        """Uploads file data to Catbox's Litterbox service."""
        url = "https://litterbox.catbox.moe/resources/internals/api.php"
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('time', '72h')
        data.add_field('fileToUpload', file_data, filename=filename)

        async with self.session.post(url, data=data, timeout=self.upload_timeout) as response:
            if response.status == 200:
                return await response.text()
            else:
                logger.error(f"Catbox upload failed with status {response.status}: {await response.text()}")
                return None

    async def _upload_to_pixeldrain(self, file_data: bytes, filename: str) -> Optional[str]:
        """Uploads file data to Pixeldrain."""
        if not self.pixeldrain_api_key:
            logger.warning("Pixeldrain API key not configured.")
            return None

        url = f"https://pixeldrain.com/api/file/{filename}"
        auth = aiohttp.BasicAuth(login="", password=self.pixeldrain_api_key)
        
        async with self.session.put(url, auth=auth, data=file_data, timeout=self.upload_timeout) as response:
            if response.status == 201:
                try:
                    # Ignore content type and parse as JSON
                    data = await response.json(content_type=None)
                    file_id = data.get('id')
                    return f"https://pixeldrain.com/api/file/{file_id}" if file_id else None
                except Exception as e:
                    logger.error(f"Error parsing Pixeldrain response: {e}")
                    return None
            else:
                logger.error(f"Pixeldrain upload failed with status {response.status}: {await response.text()}")
                return None