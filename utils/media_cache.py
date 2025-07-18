import aiohttp
import asyncio
import random
import hashlib
import json
import os
import time
from typing import Optional, List, Dict

from utils.logging_setup import get_logger
from utils.chatbot.persistence import JsonStorageManager

logger = get_logger()
CACHE_FILE = "data/media_cache.json"
SAVE_INTERVAL_SECONDS = 30

class MediaCacheManager:
    """Manages the caching of media files to third-party services using a hybrid URL and content-hash approach."""

    def __init__(self, config: dict, bot):
        self.config = config.get('media_caching', {})
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.storage_manager = JsonStorageManager()
        self.services = self.config.get('services', [])
        self.pixeldrain_api_key = self.config.get('pixeldrain_api_key')
        self.catbox_user_hash = self.config.get('catbox_user_hash')
        self.imgbb_api_key = self.config.get('imgbb_api_key')
        self.filebin_bin_name = self.config.get('filebin_bin_name')
        self.upload_timeout = self.config.get('upload_timeout_seconds', 30)
        self.permanent_host_fallback = self.config.get('permanent_host_fallback', True)
        self._load_cache()
        self._lock = asyncio.Lock()
        self._dirty = False
        self._save_task: asyncio.Task = None

    async def start(self):
        """Starts the periodic save background task."""
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._periodic_save())
            logger.info("MediaCacheManager background save task started.")

    async def shutdown(self):
        """Stops the background task, closes the session, and performs a final save."""
        # Close the client session first
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("aiohttp client session closed.")

        # Cancel the background save task
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                logger.info("MediaCacheManager background save task cancelled.")
        
        # Perform one final save
        logger.info("Performing final save of media cache...")
        await self._save_cache_to_disk()
        logger.info("Final media cache save complete.")

    async def _periodic_save(self):
        while True:
            try:
                await asyncio.sleep(SAVE_INTERVAL_SECONDS)
                if self._dirty:
                    await self._save_cache_to_disk()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in media cache periodic save task: {e}", exc_info=True)

    def _load_cache(self):
        """Loads the media cache from a JSON file and purges expired entries."""
        cache_data = self.storage_manager.read(CACHE_FILE)
        self.media_entries = cache_data.get('media_entries', {})
        self.url_to_hash_map = cache_data.get('url_to_hash_map', {})

        now = time.time()
        purged_hashes = set()
        
        for hash_key, entry in list(self.media_entries.items()):
            expiry = entry.get('expiry_timestamp')
            if expiry and expiry <= now:
                purged_hashes.add(hash_key)
                for url in entry.get('known_urls', []):
                    if self.url_to_hash_map.get(url) == hash_key:
                        del self.url_to_hash_map[url]
                del self.media_entries[hash_key]

        if purged_hashes:
            logger.info(f"Purged {len(purged_hashes)} expired entries from media cache.")
            self._mark_dirty()

    async def _save_cache_to_disk(self):
        """Saves the media cache to a JSON file using the storage manager."""
        async with self._lock:
            cache_data = {
                'media_entries': self.media_entries,
                'url_to_hash_map': self.url_to_hash_map
            }
            await asyncio.to_thread(self.storage_manager.write, CACHE_FILE, cache_data)
            self._dirty = False
            logger.debug("Media cache saved to disk.")

    def get_hash_for_cached_url(self, url: str) -> Optional[str]:
        """Finds the content hash for a given cached URL."""
        for hash_key, entry in self.media_entries.items():
            if entry.get('url') == url:
                return hash_key
        return None

    def _mark_dirty(self):
        """Marks the cache as dirty, to be saved by the periodic task."""
        self._dirty = True

    def _get_clean_url(self, url: str) -> str:
        """Removes query parameters from a URL."""
        return url.split('?')[0]

    async def cache_url(self, url: str) -> str:
        """
        Caches a media URL using a hybrid approach.

        1.  Checks for the clean URL in a direct lookup map.
        2.  If not found, downloads the content and checks for its hash.
        3.  If the hash is found, it updates the URL map.
        4.  If both are new, it uploads the file and populates the cache.
        """
        if not self.config.get('enabled') or not self.services:
            return url

        clean_url = self._get_clean_url(url)

        async with self._lock:
            # Fast Path: URL is already known
            if clean_url in self.url_to_hash_map:
                file_hash = self.url_to_hash_map[clean_url]
                cached_entry = self.media_entries.get(file_hash)
                if cached_entry:
                    expiry = cached_entry.get('expiry_timestamp')
                    if not expiry or expiry > time.time():
                        logger.debug(f"Found valid cached URL for {clean_url} via URL map.")
                        return cached_entry['url']

            # Medium/Slow Path: URL not in map, need to download
            try:
                async with self.session.get(url) as response:
                    if response.status in [403, 404]:
                        logger.warning(f"Media at {url} is expired or inaccessible (HTTP {response.status}).")
                        return None # Explicitly signal that the URL is dead
                    elif response.status != 200:
                        logger.warning(f"Failed to download media from {url}: HTTP {response.status}")
                        return url # Return original URL for other errors (e.g., server errors)
                    
                    file_data = await response.read()
                    filename = clean_url.split('/')[-1]
            except Exception as e:
                logger.error(f"Error downloading media from {url}: {e}")
                return url

            file_hash = hashlib.sha256(file_data).hexdigest()

            # Medium Path: Content hash is known from a different URL
            if file_hash in self.media_entries:
                logger.debug(f"Found existing entry for content hash from new URL {clean_url}.")
                self.url_to_hash_map[clean_url] = file_hash
                if clean_url not in self.media_entries[file_hash]['known_urls']:
                    self.media_entries[file_hash]['known_urls'].append(clean_url)
                self._mark_dirty()
                return self.media_entries[file_hash]['url']

            # Slow Path: New file, needs to be uploaded
            permanent_patterns = [
                "discordapp.com/avatars/", "discordapp.com/icons/",
                "discordapp.com/banners/", "discordapp.com/splashes/",
                "discordapp.com/emojis/"
            ]
            is_permanent = any(pattern in url for pattern in permanent_patterns)

            # Define service priority: URL-based services first
            url_upload_services = ['catbox', 'imgbb']
            file_upload_services = ['pixeldrain', 'filebin', 'litterbox']

            # Prioritize services based on upload method
            def get_prioritized_services(service_list):
                """Sorts a list of services, placing URL-based ones first."""
                url_first = [s for s in url_upload_services if s in service_list]
                file_then = [s for s in file_upload_services if s in service_list]
                # Shuffle within each priority group to distribute load
                random.shuffle(url_first)
                random.shuffle(file_then)
                return url_first + file_then

            services_to_try = []
            if is_permanent:
                permanent_services = [s for s in ['pixeldrain', 'catbox', 'imgbb', 'filebin'] if s in self.services]
                if permanent_services:
                    services_to_try = get_prioritized_services(permanent_services)
                else:
                    # Fallback to temporary if no permanent services are configured
                    logger.warning(f"No permanent storage service for {url}. Falling back to temporary.")
                    temporary_services = [s for s in ['litterbox', 'imgbb'] if s in self.services]
                    services_to_try = get_prioritized_services(temporary_services)
            else:
                temporary_services = [s for s in ['litterbox', 'imgbb'] if s in self.services]
                if temporary_services:
                    services_to_try = get_prioritized_services(temporary_services)

            if not services_to_try:
                logger.warning(f"No available caching service for {url}.")
                return url

            # Attempt to upload to the selected services
            for service in services_to_try:
                try:
                    # Pass whether the original intent was for a temporary upload
                    is_temp_upload = not is_permanent
                    new_url, expiry_timestamp = await self._upload_file(service, file_data, filename, is_temp_upload, source_url=url)
                    if new_url:
                        logger.debug(f"Successfully cached {url} to {service}: {new_url}")
                        self.media_entries[file_hash] = {
                            "url": new_url,
                            "expiry_timestamp": expiry_timestamp,
                            "known_urls": [clean_url]
                        }
                        self.url_to_hash_map[clean_url] = file_hash
                        self._mark_dirty()
                        return new_url
                except Exception as e:
                    logger.error(f"Failed to upload to {service}: {e}")
                    continue
            
            # If a temporary upload fails and fallback is enabled, try permanent services
            if not is_permanent and self.permanent_host_fallback:
                logger.warning(f"Temporary upload failed for {url}. Attempting fallback to permanent services.")
                permanent_services = [s for s in ['pixeldrain', 'catbox', 'imgbb', 'filebin'] if s in self.services]
                
                # Prioritize the permanent services as well
                prioritized_fallback_services = get_prioritized_services(permanent_services)

                for service in prioritized_fallback_services:
                    try:
                        new_url, expiry_timestamp = await self._upload_file(service, file_data, filename, is_temp_upload=False, source_url=url)
                        if new_url:
                            logger.info(f"Successfully cached {url} to fallback service {service}: {new_url}")
                            self.media_entries[file_hash] = {
                                "url": new_url,
                                "expiry_timestamp": expiry_timestamp, # Will be None for permanent
                                "known_urls": [clean_url]
                            }
                            self.url_to_hash_map[clean_url] = file_hash
                            self._mark_dirty()
                            return new_url
                    except Exception as e:
                        logger.error(f"Failed to upload to fallback service {service}: {e}")
                        continue

            logger.warning(f"Failed to cache media from {url} to any service.")
            return url

    async def _upload_file(self, service: str, file_data: bytes, filename: str, is_temp_upload: bool, source_url: str) -> tuple[Optional[str], Optional[float]]:
        """Dispatches file upload to the correct service and returns the new URL and expiry."""
        if service == 'litterbox':
            url = await self._upload_to_litterbox(file_data, filename)
            expiry = time.time() + (72 * 3600) if url and is_temp_upload else None
            return url, expiry
        elif service == 'catbox':
            url = await self._upload_to_catbox(source_url)
            return url, None
        elif service == 'pixeldrain':
            url = await self._upload_to_pixeldrain(file_data, filename)
            return url, None
        elif service == 'imgbb':
            url, expiry = await self._upload_to_imgbb(is_temp_upload, source_url=source_url)
            return url, expiry
        elif service == 'filebin':
            url = await self._upload_to_filebin(file_data, filename)
            return url, None
        
        logger.warning(f"Unknown media caching service: {service}")
        return None, None

    async def _upload_to_litterbox(self, file_data: bytes, filename: str) -> Optional[str]:
        """Uploads file data to Catbox's Litterbox service for temporary storage."""
        url = "https://litterbox.catbox.moe/resources/internals/api.php"
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('time', '72h')
        data.add_field('fileToUpload', file_data, filename=filename)

        async with self.session.post(url, data=data, timeout=self.upload_timeout) as response:
            if response.status == 200:
                return await response.text()
            logger.error(f"Litterbox upload failed with status {response.status}: {await response.text()}")
            return None

    async def _upload_to_catbox(self, source_url: str) -> Optional[str]:
        """Uploads a file from a URL to Catbox for permanent storage."""
        api_url = "https://catbox.moe/user/api.php"
        data = aiohttp.FormData()
        data.add_field('reqtype', 'urlupload')
        if self.catbox_user_hash:
            data.add_field('userhash', self.catbox_user_hash)
        data.add_field('url', source_url)

        async with self.session.post(api_url, data=data, timeout=self.upload_timeout) as response:
            if response.status == 200:
                return await response.text()
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
            logger.error(f"Pixeldrain upload failed with status {response.status}: {await response.text()}")
            return None

    async def _upload_to_imgbb(self, is_temp: bool, source_url: str) -> tuple[Optional[str], Optional[float]]:
        """Uploads an image to ImgBB from a URL. Can be temporary or permanent."""
        if not self.imgbb_api_key:
            logger.warning("ImgBB API key not configured.")
            return None, None

        api_url = "https://api.imgbb.com/1/upload"
        
        # ImgBB expects the image URL as form data, not a query parameter.
        data = aiohttp.FormData()
        data.add_field('image', source_url)
        
        params = {'key': self.imgbb_api_key}
        if is_temp:
            params['expiration'] = 60 * 60 * 24 * 3  # 3 days

        try:
            async with self.session.post(api_url, params=params, data=data, timeout=self.upload_timeout) as response:
                if response.status == 200:
                    resp_json = await response.json(content_type=None)
                    if resp_json.get("success"):
                        image_url = resp_json["data"]["url"]
                        expiration_seconds = int(resp_json["data"].get("expiration", 0))
                        expiry_timestamp = time.time() + expiration_seconds if expiration_seconds > 0 else None
                        return image_url, expiry_timestamp
                    else:
                        logger.error(f"ImgBB upload failed: {resp_json.get('error', {}).get('message', 'Unknown error')}")
                        return None, None
                else:
                    logger.error(f"ImgBB upload failed with status {response.status}: {await response.text()}")
                    return None, None
        except Exception as e:
            logger.error(f"Exception during ImgBB upload: {e}")
            return None, None

    async def _upload_to_filebin(self, file_data: bytes, filename: str) -> Optional[str]:
        """Uploads a file to Filebin for permanent storage."""
        bin_name = self.filebin_bin_name or hashlib.sha1(str(time.time()).encode()).hexdigest()[:10]
        url = f"https://filebin.net/{bin_name}/{filename}"
        
        headers = {'Content-Type': 'application/octet-stream'}
        
        try:
            async with self.session.post(url, data=file_data, headers=headers, timeout=self.upload_timeout) as response:
                if response.status == 201:
                    return f"https://filebin.net/{bin_name}/{filename}"
                else:
                    logger.error(f"Filebin upload failed with status {response.status}: {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Filebin upload: {e}")
            return None