import re
import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
import time
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from utils.embed_helper import create_embed_response, create_llm_response
import google.generativeai as genai
from google.generativeai.types.generation_types import StopCandidateException
from google.generativeai.types import HarmCategory, HarmBlockThreshold # Import for safety settings

logger = get_logger()

class LLMCommands(commands.Cog):
    """Commands for interacting with a locally hosted Large Language Model"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_online = False
        self.last_check_time = 0
        self.check_interval = 30  # Check every 30 seconds
        self.current_model = None  # Store the actual model name
        self.preferred_model = None  # Store user's preferred model (for local)
        self.gemini_client: Optional[genai.GenerativeModel] = None  # Store the Google AI client GenerativeModel instance
        self.llm_provider = "local"  # Can be "local" or "google_ai"
        
    async def cog_load(self):
        """Initialize the HTTP session when the cog loads"""
        self.session = aiohttp.ClientSession()
        
        # Try to load configuration from LLM config manager
        try:
            from config.llm_config_manager import load_llm_config
            llm_config = load_llm_config()
            
            # Load preferred model from config
            if "default_model" in llm_config:
                self.preferred_model = llm_config.get("default_model")
            else:
                # Get server-specific model if available (this only applies to local LLM)
                guild_id = self.bot.guilds[0].id if self.bot.guilds else None
                if guild_id and str(guild_id) in llm_config.get("servers", {}):
                    self.preferred_model = llm_config["servers"][str(guild_id)].get("preferred_model")
            
            # Load provider from LLM config
            self.llm_provider = llm_config.get("provider", "local")
            
            # Initialize Google AI client if using google_ai provider
            if self.llm_provider == "google_ai":
                self._init_google_ai(llm_config)
        except ImportError:
            logger.warning("LLM config manager not available, falling back to legacy config")
            # Fall back to old config method
            
            # Load preferred model from bot config
            config = self.get_llm_config() # This gets the global config for preferred model if no guild_id
            self.preferred_model = config.get('preferred_model', None)
            
            # Load provider from chatbot config
            from utils.chatbot_manager import chatbot_manager
            global_config = chatbot_manager.config_cache.get("global", {})
            self.llm_provider = global_config.get("llm_provider", "local")
            
            # Initialize Google AI client if using google_ai provider
            if self.llm_provider == "google_ai":
                self._init_google_ai(global_config)
        
        # Check if LLM is online at startup and get model name
        # For Google AI, this is done in _init_google_ai
        # For local, it checks status and populates current_model
        if self.llm_provider == "local":
            await self.check_llm_status(self.bot.guilds[0].id if self.bot.guilds else None) # Pass guild_id
        
    async def cog_unload(self):
        """Clean up the HTTP session when the cog unloads"""
        if self.session:
            await self.session.close()

    def get_llm_config(self, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """Get LLM configuration from LLM config or fallback to bot config for a specific server"""
        try:
            # First try to use the new LLM config system
            from config.llm_config_manager import load_llm_config
            
            # Load the global LLM config
            llm_config = load_llm_config()
            
            # Base configuration (global settings)
            base_config = {
                "base_url": llm_config.get("base_url", "http://localhost:1234"),
                "timeout": llm_config.get("timeout", 120),
                "max_retries": llm_config.get("max_retries", 3),
                "retry_delay": llm_config.get("retry_delay", 2),
                "provider": llm_config.get("provider", "local"),
                "google_ai_api_key": llm_config.get("google_ai_api_key"),
                "google_ai_model_name": llm_config.get("google_ai_model_name", "gemma-3-27b-it")
            }
            
            # If a guild ID is provided, get server-specific config
            if guild_id:
                server_id_str = str(guild_id)
                if "servers" in llm_config and server_id_str in llm_config["servers"]:
                    server_config = llm_config["servers"][server_id_str]
                    # Merge global and server configs
                    config = {**base_config, **server_config}
                    return config
            
            # Return base config with default enabled status if no server config or no guild specified
            return {**base_config, "enabled": True} # Default to enabled if no specific guild config to disable
            
        except ImportError:
            # Fall back to using the old bot config system
            logger.debug("LLM config manager not available, falling back to bot config")
            
            # Global default config from bot config
            global_config = self.bot.config.get('llm_global', {
                "base_url": "http://localhost:1234",
                "timeout": 120,
                "max_retries": 3,
                "retry_delay": 2
            })
            
            # Server-specific config
            if guild_id:
                server_configs = self.bot.config.get('llm_servers', {})
                server_config = server_configs.get(str(guild_id), {
                    "enabled": False, # Old config had disabled by default per server
                    "preferred_model": None,
                    "last_used_model": None
                })
                
                # Merge global and server configs
                config = {**global_config, **server_config}
                return config
            
            # Return global config if no guild specified
            return {**global_config, "enabled": False} # Default to disabled for global in old config

    async def save_model_to_config(self, model_name: str, guild_id: Optional[int] = None):
        """Save the selected model to config (only for local LLM preferences)"""
        guild_id_str = str(guild_id) if guild_id else "global"
        logger.debug(f"Saving model {model_name} to config for guild {guild_id_str}")
        
        try:
            # Try to use the new LLM config system
            from config.llm_config_manager import load_llm_config, save_llm_config
            
            # Load the current LLM config
            llm_config = load_llm_config()
            
            # Update server-specific config
            if guild_id:
                # Make sure servers dict exists
                if "servers" not in llm_config:
                    llm_config["servers"] = {}
                
                # Make sure this server exists in config
                if guild_id_str not in llm_config["servers"]:
                    # Create default entry for new guild if it doesn't exist
                    llm_config["servers"][guild_id_str] = {
                        "enabled": True,
                        "preferred_model": None,
                        "last_used_model": None
                    }
                
                # Update the model preferences
                llm_config["servers"][guild_id_str]["preferred_model"] = model_name
                llm_config["servers"][guild_id_str]["last_used_model"] = model_name
                
                # Save the config
                save_llm_config(llm_config)
            else:
                # If no guild_id, save as default model (for global local LLM)
                llm_config["default_model"] = model_name
                save_llm_config(llm_config)
            
            logger.info(f"Saved model {model_name} to LLM config for guild {guild_id_str}")
            return
        except ImportError:
            # Fall back to the old config system
            logger.warning("LLM config manager not available, falling back to bot config")
        
        # Legacy path using bot config
        # Ensure llm_servers exists in config
        if 'llm_servers' not in self.bot.config:
            self.bot.config['llm_servers'] = {}
        
        # Ensure guild config exists
        if guild_id_str not in self.bot.config['llm_servers']:
            self.bot.config['llm_servers'][guild_id_str] = {
                "enabled": True,
                "preferred_model": None,
                "last_used_model": None
            }
        
        # Update the model preferences
        self.bot.config['llm_servers'][guild_id_str]['preferred_model'] = model_name
        self.bot.config['llm_servers'][guild_id_str]['last_used_model'] = model_name
        
        # Import and use save_config
        try:
            from config.config_manager import save_config
            save_config(self.bot.config)
            logger.info(f"Saved model {model_name} to bot config for guild {guild_id_str}")
        except ImportError:
            logger.warning("Could not import save_config - model preference not saved")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def get_llm_data_path(self, guild_id: Optional[int] = None) -> str:
        """Get the path to the LLM data directory for a guild"""
        if guild_id:
            return os.path.join("llm_data", f"guild_{guild_id}")
        else:
            return "llm_data"
    
    def ensure_llm_data_directory(self, guild_id: Optional[int] = None):
        """Ensure the LLM data directory exists for a guild"""
        data_path = self.get_llm_data_path(guild_id)
        os.makedirs(data_path, exist_ok=True)
        logger.debug(f"Ensured LLM data directory exists: {data_path}")
    
    def get_system_prompt_path(self, guild_id: Optional[int] = None, thinking: bool = False) -> str:
        """Get the path to the system prompt file"""
        data_path = self.get_llm_data_path(guild_id)
        if thinking:
            return os.path.join(data_path, "system_prompt_thinking.txt")
        else:
            return os.path.join(data_path, "system_prompt.txt")
    
    def get_context_file_path(self, guild_id: Optional[int] = None) -> str:
        """Get the path to the context file"""
        data_path = self.get_llm_data_path(guild_id)
        return os.path.join(data_path, "context.txt")
    
    def load_system_prompt(self, guild_id: Optional[int] = None, thinking: bool = False) -> str:
        """Load the system prompt from file or return default"""
        prompt_path = self.get_system_prompt_path(guild_id, thinking)
        default_path = "llm_data/default_system_prompt_thinking.txt" if thinking else "llm_data/default_system_prompt.txt"
        
        prompt = None
        
        # Try to load guild-specific prompt first
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
                    #if prompt:
                        #logger.debug(f"Loaded guild-specific system prompt from {prompt_path}")
            except Exception as e:
                logger.warning(f"Failed to load guild-specific system prompt from {prompt_path}: {e}")
        
        # Fall back to default prompt if guild-specific not found
        if not prompt and os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
                    #if prompt:
                        #logger.debug(f"Loaded default system prompt from {default_path}")
            except Exception as e:
                logger.warning(f"Failed to load default system prompt from {default_path}: {e}")
        
        # Final fallback to hardcoded prompt
        if not prompt:
            if thinking:
                prompt = "You are a helpful AI assistant named Helper Retirement Machine 9000, here to answer questions about the bot and its functionality, as well as general questions. Think through your response step by step, showing your reasoning process clearly before providing your final answer."
            else:
                prompt = "You are a helpful AI assistant named Helper Retirement Machine 9000, here to answer questions about the bot and its functionality, as well as general questions. Provide clear, concise, and accurate responses."
        
        # Automatically append /no_think to non-thinking prompts if not already present
        #if not thinking and not prompt.endswith('/no_think'):
        #    prompt = prompt.rstrip() + ' /no_think'        
        return prompt
    
    def load_context(self, guild_id: Optional[int] = None) -> Optional[str]:
        """Load the context from file"""
        context_path = self.get_context_file_path(guild_id)
        default_path = "llm_data/default_context.txt"
        
        # Try to load guild-specific context first
        if os.path.exists(context_path):
            try:
                with open(context_path, 'r', encoding='utf-8') as f:
                    context = f.read().strip()
                    if context:
                        #logger.debug(f"Loaded guild-specific context from {context_path}")
                        return context
            except Exception as e:
                logger.warning(f"Failed to load guild-specific context from {context_path}: {e}")
        
        # Fall back to default context
        if os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    context = f.read().strip()
                    if context:
                        #logger.debug(f"Loaded default context from {default_path}")
                        return context
            except Exception as e:
                logger.warning(f"Failed to load default context from {default_path}: {e}")
        
        return None
    
    def save_system_prompt(self, prompt: str, guild_id: Optional[int] = None, thinking: bool = False) -> bool:
        """Save a system prompt to file"""
        try:
            self.ensure_llm_data_directory(guild_id)
            prompt_path = self.get_system_prompt_path(guild_id, thinking)
            
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            logger.info(f"Saved {'thinking ' if thinking else ''}system prompt to {prompt_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save system prompt: {e}")
            return False
    
    def save_context(self, context: str, guild_id: Optional[int] = None) -> bool:
        """Save context to file"""
        try:
            self.ensure_llm_data_directory(guild_id)
            context_path = self.get_context_file_path(guild_id)
            
            with open(context_path, 'w', encoding='utf-8') as f:
                f.write(context)
            
            logger.info(f"Saved context to {context_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            return False
    
    async def get_available_models(self, guild_id: Optional[int] = None, verbose_logging: bool = False) -> list:
        """Get list of available models from the LLM server"""
        config = self.get_llm_config(guild_id)
        models = []
        
        logger.debug(f"Getting available models for guild {guild_id}, verbose={verbose_logging}")
        
        # Try LM Studio/OpenAI compatible models endpoint
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(
                f"{config['base_url']}/v1/models",
                timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'data' in result and result['data']:
                        models = [model.get('id', 'unknown') for model in result['data']]
                        if verbose_logging:
                            logger.info(f"Found OpenAI-compatible models: {models}")
                        else:
                            logger.debug(f"Found {len(models)} OpenAI-compatible models")
                        return models
        except Exception as e:
            if verbose_logging:
                logger.error(f"Failed to get models from /v1/models: {e}")
            else:
                logger.debug(f"Failed to get models from /v1/models: {e}")
        
        # Try Ollama models endpoint
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(
                f"{config['base_url']}/api/tags",
                timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'models' in result and result['models']:
                        models = [model.get('name', 'unknown') for model in result['models']]
                        if verbose_logging:
                            logger.info(f"Found Ollama models: {models}")
                        else:
                            logger.debug(f"Found {len(models)} Ollama models")
                        return models
        except Exception as e:
            if verbose_logging:
                logger.error(f"Failed to get models from /api/tags: {e}")
            else:
                logger.debug(f"Failed to get models from /api/tags: {e}")
        
        # Return empty list if no models found
        logger.debug("No models found from any endpoint")
        return models
    
    async def get_current_model(self, guild_id: Optional[int] = None) -> Optional[str]:
        """Get the currently loaded model name (primarily for local LLM)"""
        logger.debug(f"Getting current model for guild {guild_id}")
        
        # If using Google AI, use its configured model name
        if self.llm_provider == "google_ai":
            config = self.get_llm_config(guild_id)
            return config.get("google_ai_model_name", "gemma-3-27b-it")
            
        # For local LLM, try to get from available models or fallback
        models = await self.get_available_models(guild_id, verbose_logging=False)
        if models:
            # If we have a preferred model and it's available, use it
            if self.preferred_model and self.preferred_model in models:
                logger.debug(f"Using preferred local model: {self.preferred_model}")
                return self.preferred_model
            # Otherwise return the first available model
            logger.debug(f"Using first available local model: {models[0]}")
            return models[0]
        
        # Fallback to configured model name if no models found (for local LLM)
        config = self.get_llm_config(guild_id)
        fallback_model = config.get('last_used_model', 'local-model')
        logger.debug(f"Using fallback local model: {fallback_model}")
        return fallback_model
    
    async def check_llm_status(self, guild_id: Optional[int] = None) -> bool:
        """Check if the LLM is online and responding (for local LLM)"""
        config = self.get_llm_config(guild_id)
        logger.debug(f"Checking LLM status for guild {guild_id}")
        
        if not config.get('enabled', False) and self.llm_provider == "local":
            self.is_online = False
            logger.debug("Local LLM is disabled in configuration")
            return False
        
        if self.llm_provider == "google_ai":
            # For Google AI, status is determined by _init_google_ai
            return self.is_online
            
        # For local LLM:
        # Try health check endpoints (prioritize official endpoints)
        health_endpoints = ["/v1/models", "/api/tags"]
        for endpoint in health_endpoints:
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with self.session.get(
                    f"{config['base_url']}{endpoint}",
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        self.is_online = True
                        logger.debug(f"Local LLM health check successful via {endpoint}")
                        
                        # Try to extract model name from models endpoint
                        if endpoint == "/v1/models" and not self.current_model:
                            try:
                                result = await response.json()
                                if 'data' in result and result['data']:
                                    available_models = [model.get('id', 'unknown') for model in result['data']]
                                    if self.preferred_model and self.preferred_model in available_models:
                                        self.current_model = self.preferred_model
                                    elif available_models:
                                        self.current_model = available_models[0]
                                    logger.debug(f"Set current local model to {self.current_model} from health check")
                            except Exception as e:
                                logger.debug(f"Failed to extract model from health check: {e}")
                        
                        return True
            except Exception as e:
                logger.debug(f"Local LLM health check failed for {endpoint}: {e}")
        
        # If health endpoints don't work, try a simple completion request
        try:
            # We don't want to trigger full make_llm_request which involves full prompt preparation
            # Instead, do a minimal mock request
            temp_model = self.current_model or "test-model" # Use current model if available, else a dummy
            
            payload = {
                "model": temp_model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
                "temperature": 0
            }
            timeout = aiohttp.ClientTimeout(total=5)
            url = f"{config['base_url']}/v1/chat/completions"
            
            async with self.session.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    self.is_online = True
                    logger.debug(f"Local LLM health check successful via test completion")
                    return True
                else:
                    logger.debug(f"Local LLM test request returned status {response.status}")
                    self.is_online = False
                    return False
        except Exception as e:
            logger.debug(f"Local LLM test request failed: {e}")
            self.is_online = False
            return False
    
    async def make_llm_request(
        self, 
        prompt: Optional[str] = None,
        thinking: bool = False,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        guild_id: Optional[int] = None,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Make a request to the LLM API and return response with performance metrics.
        Automatically detects which provider to use (local or Google AI) based on configuration."""
        start_time = time.time()
        
        # Try to get provider from LLM config first, if available
        try:
            from config.llm_config_manager import load_llm_config
            llm_config = load_llm_config()
            self.llm_provider = llm_config.get("provider", "local")
        except ImportError:
            # Fall back to chatbot_manager config if LLM config is not available
            from utils.chatbot_manager import chatbot_manager
            global_config = chatbot_manager.config_cache.get("global", {})
            self.llm_provider = global_config.get("llm_provider", "local")
        
        # Common preparation of system prompt and context
        system_prompt, context = self._prepare_prompts(system_prompt, context, thinking, guild_id)
        
        # Route to appropriate provider
        if self.llm_provider == "google_ai":
            # Get config for Google AI (it's a global config for Google AI)
            try:
                from config.llm_config_manager import load_llm_config
                config_for_request = load_llm_config()
            except ImportError:
                from utils.chatbot_manager import chatbot_manager
                config_for_request = chatbot_manager.config_cache.get("global", {})
                
            return await self._make_google_ai_request(
                prompt, system_prompt, context, max_tokens, temperature,
                config_for_request, guild_id, start_time
            )
        else: # "local" provider
            return await self._make_local_llm_request(
                prompt, system_prompt, context, max_tokens, temperature,
                guild_id, start_time
            )

    def _prepare_prompts(self, system_prompt: Optional[str], context: Optional[str],
                        thinking: bool, guild_id: Optional[int]) -> Tuple[str, Optional[str]]:
        """Prepare system prompt and context for both providers"""
        # Prepare the system prompt
        if system_prompt is None:
            system_prompt = self.load_system_prompt(guild_id, thinking=thinking)

        # Load context if available and not provided
        # (This is for static context from file, dynamic chatbot context is passed directly)
        if context is None:
            context = self.load_context(guild_id)
            
        return system_prompt, context

    def _save_debug_payload(self, payload: dict, endpoint: str, provider: str):
        """Save debug payload to file for debugging purposes"""
        try:
            debug_dir = os.path.join("llm_data", "debug_prompts")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"llm_payload_{provider}.json"
            debug_filepath = os.path.join(debug_dir, debug_filename)
            
            with open(debug_filepath, 'w', encoding='utf-8') as f:
                f.write(f"// filepath: {debug_filepath}\n")
                f.write(f"// Provider: {provider}\n")
                f.write(f"// Endpoint: {endpoint}\n")
                f.write(f"// Timestamp: {timestamp}\n")
                f.write("// PAYLOAD:\n")
                # Use json.dumps from standard library
                f.write(json.dumps(payload, indent=2, ensure_ascii=False))
            logger.debug(f"Saved debug payload to {debug_filepath}")
        except Exception as e:
            logger.warning(f"Failed to save debug payload: {e}")

    def _calculate_performance_metrics(self, start_time: float, content: str,
                                     usage: Optional[dict] = None) -> Dict[str, Any]:
        """Calculate performance metrics for LLM response"""
        end_time = time.time()
        elapsed_time = end_time - start_time
        char_count = len(content) if content else 0
        chars_per_sec = char_count / elapsed_time if elapsed_time > 0 else 0
        
        # Extract token usage if available
        prompt_tokens = usage.get('prompt_tokens', 0) if usage else 0
        completion_tokens = usage.get('completion_tokens', 0) if usage else 0
        total_tokens = usage.get('total_tokens', 0) if usage else 0
        
        # Calculate tokens per second
        # If exact token data isn't available, estimate using a common factor (e.g., 4 chars/token)
        tokens_per_sec = 0
        if completion_tokens > 0:
            tokens_per_sec = completion_tokens / elapsed_time if elapsed_time > 0 else 0
        elif char_count > 0: # Fallback estimation if no token usage
            tokens_per_sec = chars_per_sec / 4  # Rough estimation

        return {
            'elapsed_time': elapsed_time,
            'char_count': char_count,
            'chars_per_sec': chars_per_sec,
            'tokens_per_sec': tokens_per_sec,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'has_token_data': total_tokens > 0 # Indicates if token data came from API or was estimated
        }

    async def _make_google_ai_request(self, prompt: Optional[str], system_prompt: str,
                                    context: Optional[str], max_tokens: int,
                                    temperature: float, global_config: dict,
                                    guild_id: Optional[int], start_time: float) -> Tuple[str, Dict[str, Any]]:
        """Handle Google AI (Gemini) requests, supporting system instructions and Gemma-specific formats."""

        model_name = global_config.get("google_ai_model_name", "gemma-3-27b-it")
        self.current_model = model_name  # Update current model for status/logging

        # Check if model requires Gemma-specific system prompt handling
        gemma_model_prefixes = ("gemma", "gemma-")
        is_gemma_family = model_name.lower().startswith(gemma_model_prefixes)

        # Decide how to pass the system_prompt
        system_instruction_for_model_init = None
        # Gemma models do not support system_instruction parameter, it must be part of the first user turn.
        # Other Gemini models (like gemini-pro) can use system_instruction.
        if not is_gemma_family:
            system_instruction_for_model_init = system_prompt
            logger.debug(f"Google AI: Non-Gemma model '{model_name}'. Using system_instruction parameter.")
        else:
            logger.debug(f"Google AI: Gemma model '{model_name}' detected. System instruction will be prepended to the first user message.")

        # Initialize the GenerativeModel instance.
        # We need to re-initialize if the model name changes, or if the system_instruction content changes
        # for non-Gemma models (as it's a constructor argument).
        # For Gemma, system_instruction_for_model_init is None, so we don't check it.
        # We also want to re-init if the *type* of system instruction handling changes (Gemma vs. non-Gemma).
        
        # Placeholder for previous system instruction used for non-Gemma models
        previous_system_instruction = getattr(self.gemini_client, '_system_instruction', None) if self.gemini_client else None

        if self.gemini_client is None or \
           self.gemini_client._model_name != model_name or \
           (not is_gemma_family and previous_system_instruction != system_instruction_for_model_init) or \
           (is_gemma_family and previous_system_instruction is not None): # If it was non-Gemma with system_instruction, and now it's Gemma
            try:
                self.gemini_client = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction_for_model_init # Will be None for Gemma
                )
                logger.debug(f"Google AI GenerativeModel re-initialized for model '{model_name}'. System instruction used: {system_instruction_for_model_init is not None}")
            except Exception as e:
                logger.error(f"Failed to initialize Google AI GenerativeModel for {model_name}: {e}")
                self.is_online = False
                raise Exception(f"Failed to initialize Google AI model: {str(e)}")

        if not self.is_online: # Check connectivity from _init_google_ai
            raise Exception("Google AI API is not available or failed to initialize.")

        # Build the initial list of messages.
        raw_messages_for_gemini = self._build_messages_list(system_prompt, context, prompt)

        # --- Transform raw_messages_for_gemini into Gemini's expected 'contents' list ---
        contents_for_api = []
        gemma_prepended_system_content = None

        # Extract the system message if it exists (it's always the first if present from _build_messages_list)
        if raw_messages_for_gemini and raw_messages_for_gemini[0]['role'] == 'system':
            initial_system_message = raw_messages_for_gemini.pop(0) # Remove system message from the list
            if is_gemma_family: # If it's a Gemma model, we'll prepend this content later
                gemma_prepended_system_content = initial_system_message['content']
                logger.debug("Gemma: Stored system instruction content for prepending.")
            # If not Gemma, the system_instruction_for_model_init was already handled at model initialization.

        first_user_message_found = False
        for msg_dict in raw_messages_for_gemini:
            # Map roles: 'user' -> 'user', 'assistant' -> 'model'
            gemini_role = "user" if msg_dict['role'] == "user" else "model"
            current_content = msg_dict['content']

            # For Gemma models, prepend the system instruction to the first user message
            if is_gemma_family and gemini_role == "user" and gemma_prepended_system_content and not first_user_message_found:
                current_content = f"{gemma_prepended_system_content}\n\n{current_content}"
                gemma_prepended_system_content = None # Ensure it's only prepended once
                first_user_message_found = True
                logger.debug("Gemma: Prepending system instruction to first user message content.")
            
            # Append the message in Gemini's 'contents' format
            contents_for_api.append({
                'role': gemini_role,
                'parts': [{'text': current_content}]
            })

        # Final check for Gemma: If there was a system instruction but no user message was found
        # to prepend it to (e.g., only bot messages in context or empty history + system_prompt only).
        # In this rare case, add the system instruction as a standalone user message.
        if is_gemma_family and gemma_prepended_system_content:
            contents_for_api.append({
                'role': 'user',
                'parts': [{'text': gemma_prepended_system_content}]
            })
            logger.warning("Gemma: System instruction was added as a standalone user message (no existing user turn found to prepend).")

        # Configure generation parameters
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": 0.95,
            "top_k": 0 # Default value for many Gemini models, or can be set dynamically
        }

        # Define safety settings (optional, but good practice for public bots)
        safety_settings = [
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        # Debug payload for the actual API call
        debug_payload = {
            "model": model_name,
            "contents": contents_for_api, # This is the actual structure sent
            "generation_config": generation_config,
            "safety_settings": [str(s) for s in safety_settings], # Convert enum to string for logging
            "system_instruction_param_used": system_instruction_for_model_init is not None # For debug clarity
        }
        self._save_debug_payload(debug_payload, "Google AI API", "google_ai")

        try:
            # Make the request using the prepared client and contents list
            response = self.gemini_client.generate_content(
                contents=contents_for_api, # Pass the list of messages
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            # Extract the response text
            content = response.text
            
            # Google AI's generate_content result objects typically don't
            # have a direct 'usage' attribute like OpenAI/local LLMs for exact token counts.
            # We'll rely on character counts and approximate token counts for now.
            performance_metrics = self._calculate_performance_metrics(start_time, content)
            performance_metrics['has_token_data'] = False # Indicate no exact token data from API

            # Approximate prompt token counts based on char_count (rough estimate of 4 chars per token)
            approx_prompt_chars = sum(len(part['text']) for msg in contents_for_api for part in msg['parts'])
            performance_metrics['prompt_tokens'] = approx_prompt_chars // 4
            performance_metrics['completion_tokens'] = len(content) // 4
            performance_metrics['total_tokens'] = performance_metrics['prompt_tokens'] + performance_metrics['completion_tokens']


            logger.debug(f"Google AI request completed in {performance_metrics['elapsed_time']:.2f}s, "
                        f"{performance_metrics['chars_per_sec']:.1f} chars/s "
                        f"(~{performance_metrics['tokens_per_sec']:.1f} tokens/s)")

            # Convert text patterns to Discord format
            content = self.convert_text_to_discord_format(content, guild_id)

            return content, performance_metrics

        except StopCandidateException as e:
            # Handle safety filter
            safety_ratings = getattr(e.candidate, "safety_ratings", [])
            safety_info = ", ".join(f"{rating.category}: {rating.probability}" for rating in safety_ratings) if safety_ratings else "unknown"
            error_msg = f"Google AI safety filter triggered: {safety_info}. Rejection reason: {e.response.prompt_feedback.block_reason}"
            logger.warning(error_msg)
            raise Exception(f"Safety filter triggered: {error_msg}. Please rephrase your query or adjust bot's safety settings.")

        except Exception as e:
            logger.error(f"Error making Google AI request: {e}", exc_info=True)
            raise Exception(f"Failed to get response from Google AI: {str(e)}")

    async def _make_local_llm_request(self, prompt: Optional[str], system_prompt: str,
                                    context: Optional[str], max_tokens: int,
                                    temperature: float, guild_id: Optional[int],
                                    start_time: float) -> Tuple[str, Dict[str, Any]]:
        """Handle local LLM requests"""
        config = self.get_llm_config(guild_id)
        
        if not config.get('enabled', False):
            raise Exception("LLM is not enabled in configuration")
        
        # Check if we need to verify status
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_check_time > self.check_interval:
            await self.check_llm_status(guild_id)
            self.last_check_time = current_time
        
        if not self.is_online:
            # Try to reconnect
            logger.info("Attempting to reconnect to local LLM...")
            if not await self.check_llm_status(guild_id):
                raise Exception("Local LLM appears to be offline")

        # Use the detected model name or fallback to config
        model_name = self.current_model or config.get('model', 'local-model')
        
        # Build messages list as expected by local LLM (OpenAI-compatible)
        messages = self._build_messages_list(system_prompt, context, prompt)
        
        # Create payload
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        # Try different API endpoints (mostly for compatibility with LM Studio/Ollama)
        endpoints = ["/v1/chat/completions"]
        
        for endpoint in endpoints:
            try:
                timeout = aiohttp.ClientTimeout(total=config.get('timeout', 120))
                url = f"{config['base_url']}{endpoint}"
                
                # Save debug payload
                self._save_debug_payload(payload, url, "local")
                
                async with self.session.post(
                    url,
                    json=payload,
                    timeout=timeout,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = self._extract_content_from_response(result)
                        
                        if content:
                            # Extract model name from response if available
                            response_model = result.get('model')
                            if response_model and response_model != self.current_model:
                                logger.debug(f"Updating current local model from response: {response_model}")
                                self.current_model = response_model
                            
                            # Calculate performance metrics
                            usage = result.get('usage', {})
                            performance_metrics = self._calculate_performance_metrics(start_time, content, usage)
                            
                            if performance_metrics['has_token_data']:
                                logger.debug(f"LLM request completed in {performance_metrics['elapsed_time']:.2f}s, "
                                           f"{performance_metrics['tokens_per_sec']:.1f} tokens/s "
                                           f"({performance_metrics['completion_tokens']} tokens)")
                            else:
                                logger.debug(f"LLM request completed in {performance_metrics['elapsed_time']:.2f}s, "
                                           f"{performance_metrics['chars_per_sec']:.1f} chars/s "
                                           f"(~{performance_metrics['tokens_per_sec']:.1f} tokens/s)")
                            
                            # Convert text patterns to Discord format
                            content = self.convert_text_to_discord_format(content, guild_id)
                            
                            return content, performance_metrics
                        
            except Exception as e:
                logger.debug(f"Local LLM request failed for {endpoint}: {e}", exc_info=True)
                continue
        
        # If all attempts failed, mark as offline and raise error
        self.is_online = False
        raise Exception("Failed to get response from LLM after trying multiple formats")

    def _build_messages_list(self, system_prompt: str, context: Optional[str],
                          prompt: Optional[str]) -> List[Dict[str, str]]:
        """Build messages list with roles: 'system', 'user', 'assistant'"""
        messages = []

        # Add the initial system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Process dynamic context from chatbot_manager.format_context_for_llm
        if context:
            channel_info = ""
            user_info = ""
            pinned_messages_text = "" # NEW: For pinned messages
            conversation_history_text = ""

            # Use regex to split the context string by its known section headers
            # This regex handles cases where headers might be at the start or mid-string
            sections = re.split(r'(===\s*(Current Channel Info|Known Users|Recent Conversation History|Pinned Messages)\s*===)', context, flags=re.DOTALL)
            
            # Iterate through the parts to extract content for each section
            # The split operation results in: ["", HEADER_FULL, HEADER_NAME, CONTENT, HEADER_FULL, HEADER_NAME, CONTENT, ...]
            # We process every 3 elements starting from index 0 or 1 depending on initial empty string
            i = 0
            # If the first element is empty, start from the first header
            if sections and sections[0] == "":
                i = 1
            
            while i < len(sections):
                if i + 2 < len(sections) and sections[i].startswith("==="): # Check if it looks like a header section
                    header_name = sections[i+1].strip() # This is the captured group name
                    content_block = sections[i+2].strip()
                    
                    if header_name == "Current Channel Info":
                        channel_info = content_block
                    elif header_name == "Known Users":
                        user_info = content_block
                    elif header_name == "Recent Conversation History":
                        conversation_history_text = content_block
                    elif header_name == "Pinned Messages": # NEW
                        pinned_messages_text = content_block
                    
                    i += 3 # Move past header_tag, header_name, content_block
                else:
                    i += 1 # Skip non-header parts (e.g., initial empty string)

            # Combine Channel Info, Known Users, and Pinned Messages into a single 'user' message
            # This provides general context before the dynamic conversation history
            combined_static_context_block = []
            if channel_info:
                combined_static_context_block.append(f"Channel Information:\n{channel_info}")
            if user_info:
                combined_static_context_block.append(f"Known Users:\n{user_info}")
            if pinned_messages_text: # NEW
                combined_static_context_block.append(f"Pinned Messages:\n{pinned_messages_text}")
            
            if combined_static_context_block:
                llm_context_content = "\n\n".join(combined_static_context_block)
                messages.append({"role": "user", "content": llm_context_content})

            # Add the actual conversation history
            if conversation_history_text:
                messages.extend(self._parse_conversation_history_block(conversation_history_text))
        
        # Add the actual current user prompt
        if prompt:
            messages.append({"role": "user", "content": prompt})
            
        return messages

    def _parse_conversation_history_block(self, conversation_text: str) -> List[Dict[str, str]]:
        """Parse raw conversation history text into messages list with 'user' and 'assistant' roles.
        This function expects *only* the conversation lines, not including the '===' headers or channel info.
        """
        messages = []
        
        # Remove the '=== End of Conversation History ===' line if it's there
        conversation_text = conversation_text.split("=== End of Conversation History ===")[0].strip()

        conversation_lines = conversation_text.split('\n')
        
        current_role = None
        current_content = []
        
        for line in conversation_lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for role markers (e.g., "Username: ", "Helper Retirement Machine 9000: ")
            # Ensure it's not a context note line or channel information that might also have a colon
            if ": " in line and not line.startswith("Note:") and not line.startswith("Context:") and not line.startswith("Channel Information:") and not line.startswith("Pinned Messages:"):
                # If we were building a previous message, add it now
                if current_role is not None:
                    self._add_parsed_message(messages, current_role, current_content)
                    current_content = []
                
                # Start a new message
                parts = line.split(": ", 1)
                current_role = parts[0]
                current_content = [parts[1]] if len(parts) > 1 and parts[1].strip() else []
            else:
                # Continue the current message
                if current_role is not None:
                    # Filter out empty bot responses like "Helper Retirement Machine 9000:" or "Other Bot:" if the line is empty
                    if current_role in ["Mirrobot", "Other Bot"] and not line.strip():
                        continue
                    current_content.append(line)
                    
        # Add the last message if there is one
        if current_role is not None:
            self._add_parsed_message(messages, current_role, current_content)
            
        return messages

    def _add_parsed_message(self, messages: List[Dict[str, str]], current_role: str, 
                          current_content: List[str]):
        """Add a parsed message to the messages list, mapping roles to 'user'/'assistant'."""
        # Map specific roles to 'assistant', otherwise 'user'
        if current_role in ["Mirrobot", "Other Bot"]:
            role = "assistant"
        else:
            role = "user"
        
        # Always combine content before adding to ensure a single string
        combined_content = "\n".join(current_content).strip()
        
        if role == "assistant":
            # For assistant messages, only add if there's actual content
            if combined_content:
                messages.append({"role": "assistant", "content": combined_content})
        else: # For user messages, always add, preserving original username as part of content if needed
            if combined_content:
                # Include username for user messages in the content to help LLM distinguish speakers
                messages.append({"role": "user", "content": f"{current_role}: {combined_content}"})

    def _extract_content_from_response(self, result: dict) -> Optional[str]:
        """Extract content from different API response formats (OpenAI-compatible, Ollama)"""
        # OpenAI format
        if 'choices' in result and result['choices']:
            return result['choices'][0].get('message', {}).get('content', '')
        
        # Ollama format
        elif 'response' in result:
            return result['response']
        
        # Generic format
        elif 'text' in result:
            return result['text']
            
        return None
    
    async def send_llm_response(self, ctx, response: str, question: str, thinking: bool = False, performance_metrics: Optional[Dict[str, Any]] = None):
        """Helper function to send LLM response using the new unified embed system"""
        logger.debug(f"Sending LLM response for thinking={thinking}")
        model_name = self.current_model or "Unknown Model"
        
        # Choose color and title based on thinking mode
        color = discord.Color.purple() if thinking else discord.Color.blue()
        title = "LLM Thinking Response" if thinking else "LLM Response"
        
        logger.info(f"Sending LLM response to {ctx.author} in {ctx.guild.name if ctx.guild else 'DM'}")
        
        # Extract thinking content if present
        cleaned_response, thinking_content = self.strip_thinking_tokens(response)
        
        # Use the new unified LLM response creator
        await create_llm_response(
            ctx,
            response_text=cleaned_response,
            question=question,
            model_name=model_name,
            thinking_content=thinking_content,
            show_thinking=thinking and bool(thinking_content), # Only show thinking if thinking is enabled AND there's content
            title=title,
            color=color,
            performance_metrics=performance_metrics
        )        
        total_chars = len(cleaned_response) + len(thinking_content)
        logger.debug(f"Sent LLM response ({total_chars} total chars, {len(thinking_content)} thinking chars)")
        
        # Log performance metrics if available
        if performance_metrics:
            if performance_metrics.get('has_token_data', False):
                logger.info(f"LLM Performance: {performance_metrics['elapsed_time']:.2f}s, "
                           f"{performance_metrics['tokens_per_sec']:.1f} tokens/s, "
                           f"{performance_metrics['completion_tokens']} tokens generated")
            else:
                logger.info(f"LLM Performance: {performance_metrics['elapsed_time']:.2f}s, "
                           f"{performance_metrics['chars_per_sec']:.1f} chars/s, "
                           f"~{performance_metrics['tokens_per_sec']:.1f} tokens/s)")
    
    def strip_thinking_tokens(self, response: str) -> tuple[str, str]:
        """Strip thinking tokens from the response and return both cleaned response and thinking content"""
        logger.debug("Stripping thinking tokens from response")
        
        # Remove common thinking patterns and extract their content
        patterns = [
            (r'<think>(.*?)</think>', 'think'),  # <think></think> tags
            (r'<thinking>(.*?)</thinking>', 'thinking'),  # <thinking></thinking> tags
            (r'\[thinking\](.*?)\[/thinking\]', 'thinking'),  # [thinking][/thinking] tags
            (r'<thought>(.*?)</thought>', 'thought'),  # <thought></thought> tags
            (r'\*thinking\*(.*?)\*/thinking\*', 'thinking'),  # *thinking*...*thinking* pattern
        ]
        
        thinking_content_list = [] # Use a list to collect all thinking parts
        cleaned_response = response
        
        for pattern, tag_type in patterns:
            # Find all matches for the current pattern
            matches = re.findall(pattern, cleaned_response, flags=re.DOTALL | re.IGNORECASE)
            if matches:
                logger.debug(f"Found {len(matches)} {tag_type} sections")
                thinking_content_list.extend([m.strip() for m in matches if m.strip()]) # Add non-empty matches
                cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up extra whitespace and empty lines left after stripping
        cleaned_response = re.sub(r'\n\s*\n', '\n\n', cleaned_response)
        cleaned_response = cleaned_response.strip()
        
        # Combine all thinking content into a single string
        combined_thinking = '\n\n'.join(thinking_content_list).strip()
        
        if combined_thinking:
            logger.debug(f"Extracted {len(combined_thinking)} characters of thinking content.")
        
        return cleaned_response, combined_thinking
    
    def convert_text_to_discord_format(self, content: str, guild_id: Optional[int] = None) -> str:
        """Convert text patterns in LLM response to Discord format
        
        Handles:
        - <Ping> @Username -> actual Discord mention
        - @Username -> actual Discord mention
        - Removes self-mentions of the bot to prevent it from mentioning itself
        
        Args:
            content: Text content from LLM response
            guild_id: Optional guild ID to look up users
            
        Returns:
            Formatted text with proper Discord formatting
        """
        try:
            # Skip processing if content is empty
            if not content:
                return content
            
            # Check if this is a bot response message by looking for the bot's name
            # This helps us determine if we need to strip out self-references
            # Note: bot_user_id should ideally be fetched from bot.user.id in a listener,
            # but for a cog, assuming it's relatively static is okay for now.
            bot_user_id = self.bot.user.id if self.bot.user else 0 # Use bot's actual ID
            bot_names = ["Mirrobot", "Helper Retirement Machine 9000"] # Add your bot's names here
            is_bot_message = False
            
            # Check if message starts with bot name (this indicates it's likely a bot's own internal response)
            # This is a heuristic to guess if the *LLM* is generating a self-referential message,
            # not if the *bot* is sending a message. LLM should be told its name.
            # Removed this heuristic as it's unreliable; rely on the LLM's instruction not to self-mention in prompt.
            # The removal of self-mentions logic below will handle it based on bot_user_id.
            
            # Filter out "Username:" pattern at the beginning of messages or lines
            # This handles cases where a message starts with a username followed by a colon
            username_colon_pattern = r'^(?:(?:[a-zA-Z0-9_ -]+)|(?:<@!?\d+>)):|(?:\n)(?:(?:[a-zA-Z0-9_ -]+)|(?:<@!?\d+>)): '
            content = re.sub(username_colon_pattern, '', content, flags=re.MULTILINE).strip()
            # After removing, clean up potential empty lines or excessive whitespace
            content = re.sub(r'\n\s*\n', '\n\n', content).strip()


            # If this is from the bot, remove self-mentions to prevent self-talk
            # This happens if the LLM output itself contains the bot's mention or name
            if bot_user_id != 0: # Only apply if bot_user_id is known
                # Remove direct mentions of the bot
                bot_mention_pattern = f'<@!?{bot_user_id}>'
                content = re.sub(bot_mention_pattern, '', content)
                
                # Also remove text references to the bot's name
                for name in bot_names:
                    # Use word boundary to avoid partial replacements, and ignore case
                    content = re.sub(f'\\b{re.escape(name)}\\b', '', content, flags=re.IGNORECASE)
                
                # Clean up any double spaces or leading/trailing whitespace left by mention/name removals
                content = re.sub(r'\s+', ' ', content).strip()
            
            # Load user index for mentions (used by both mention formats)
            user_index = {}
            try:
                from utils.chatbot_manager import chatbot_manager
                if guild_id:
                    user_index = chatbot_manager.load_user_index(guild_id)
                    logger.debug(f"Loaded user index with {len(user_index)} users for mention conversion")
            except ImportError:
                logger.debug("Chatbot manager not available for user lookups")
            
            # Convert text ping format: <Ping> @Username
            # This pattern should be robust to various characters in username, but usually it's plain letters/numbers
            # Find all instances of this pattern (e.g., <Ping> @User_Name or <ping> @Another User)
            ping_pattern = r'<[Pp][Ii][Nn][Gg]>\s*@([a-zA-Z0-9_ ]+)' # Capture the username string
            ping_matches = re.findall(ping_pattern, content)
            
            if ping_matches:
                # Process each match
                for username_match in set(ping_matches): # Use set to process unique usernames once
                    user_id = None
                    # Look in user index first (case-insensitive and handle spaces)
                    for uid, user_entry in user_index.items():
                        if username_match.lower().strip() == user_entry.username.lower().strip() or \
                           username_match.lower().strip() == user_entry.display_name.lower().strip():
                            user_id = uid
                            break
                    
                    if user_id:
                        # Skip self-mentions (if the user ID matches the bot's own ID)
                        if int(user_id) == bot_user_id: # and is_bot_message: // is_bot_message heuristic removed
                            # Remove the original text ping pattern from content
                            content = re.sub(re.escape(f'<Ping> @{username_match}'), '', content, flags=re.IGNORECASE)
                            logger.debug(f"Removed self-mention of bot via <Ping> @{username_match}")
                            continue
                            
                        # Replace the text ping with actual Discord mention
                        # Use re.escape for the username_match to handle special characters correctly in regex
                        pattern_to_replace = r'<[Pp][Ii][Nn][Gg]>\s*@' + re.escape(username_match) + r'\b'
                        discord_mention = f'<@{user_id}>'
                        content = re.sub(pattern_to_replace, discord_mention, content, flags=re.IGNORECASE)
                        logger.debug(f"Converted text ping for '{username_match}' to Discord mention for user ID {user_id}")
                    else:
                        logger.debug(f"Could not find user ID for <Ping> @'{username_match}'")
            
            # Convert plain @Username format (without <Ping> tag)
            # Find all instances of @Username pattern (not preceded by < and not part of existing <@ID>)
            # This regex avoids matching inside existing Discord mentions like <@12345>
            username_pattern = r'(?<!<)(?<!<@)\B@([a-zA-Z0-9_]+)\b'
            username_matches = re.findall(username_pattern, content)
            
            if username_matches:
                logger.debug(f"Found {len(username_matches)} username mentions to convert")
                
                # Process each match
                for username in set(username_matches): # Use set for unique usernames
                    # Skip if username is one of the bot names and this is a bot message
                    if any(username.lower() == name.lower() for name in bot_names) and bot_user_id != 0: # and is_bot_message: // heuristic removed
                        logger.debug(f"Skipping @{username} as it's a self-mention of the bot.")
                        # Additionally, remove the self-mention
                        content = re.sub(f'@{re.escape(username)}\\b', '', content)
                        continue
                        
                    # Try to find the user by username or display name
                    user_id = None
                    
                    # Look in user index (case-insensitive)
                    for uid, user_entry in user_index.items():
                        if username.lower() == user_entry.username.lower() or username.lower() == user_entry.display_name.lower():
                            user_id = uid
                            break
                    
                    if user_id:
                        # Replace the username with actual Discord mention
                        # Use word boundary to ensure we don't replace partial matches
                        # Also ensure it's not already part of an existing mention
                        pattern = r'(?<!<)(?<!<@)\B@' + re.escape(username) + r'\b'
                        discord_mention = f'<@{user_id}>'
                        content = re.sub(pattern, discord_mention, content)
                        logger.debug(f"Converted @{username} to Discord mention for user ID {user_id}")
                    else:
                        logger.debug(f"Could not find user ID for username '@{username}'")
            
            # NEW: Convert plain Username format (without @ symbol)
            # We need to be more careful here to avoid false positives
            if user_index and len(user_index) > 0:
                # Build a list of usernames to look for - filter out short names to avoid false positives
                usernames_to_find = []
                for uid, user_entry in user_index.items():
                    # Only consider usernames that are at least 3 characters to avoid false positives
                    # and are not exclusively numbers (to avoid accidental ID matches)
                    if len(user_entry.username) >= 3 and not user_entry.username.isdigit():
                        usernames_to_find.append((user_entry.username, uid))
                    # Also include display names if they differ from username and are long enough
                    if user_entry.display_name != user_entry.username and len(user_entry.display_name) >= 3 and not user_entry.display_name.isdigit():
                        usernames_to_find.append((user_entry.display_name, uid))
                
                # Sort by length (descending) to prioritize longer matches and avoid replacing substrings
                usernames_to_find.sort(key=lambda x: len(x[0]), reverse=True)
                
                # Check for each username in the content
                for username_text, uid in usernames_to_find:
                    # Skip self-mentions (if the user ID matches the bot's own ID)
                    if int(uid) == bot_user_id: # and is_bot_message: // heuristic removed
                        continue
                        
                    # Look for the username with word boundaries to avoid partial matches
                    # Ensure it's not already part of a Discord mention (e.g., <@12345> or @username_part_of_mention)
                    # This pattern also ensures it's not part of a URL or code block
                    pattern = r'(?<![<@`/\.])\b' + re.escape(username_text) + r'\b(?![\d])'
                    
                    # Check if this pattern appears in the content
                    if re.search(pattern, content, re.IGNORECASE):
                        # Replace with Discord mention
                        discord_mention = f'<@{uid}>'
                        content = re.sub(pattern, discord_mention, content, flags=re.IGNORECASE)
                        logger.debug(f"Converted plain username '{username_text}' to Discord mention for user ID {uid}")
            
            # Final cleanup of any weird whitespace artifacts
            content = re.sub(r'\s+', ' ', content).strip()
            content = re.sub(r'\s+([.,!?:;])', r'\1', content)  # Fix spacing before punctuation
            
            return content
            
        except Exception as e:
            logger.error(f"Error converting text to Discord format: {e}", exc_info=True)
            # If something goes wrong, just return the original content
            return content
        
    def _init_google_ai(self, config):
        """Initialize the Google AI client and its GenerativeModel instance."""
        try:
            # Try to get API key from environment first, then from config
            api_key = os.environ.get("GOOGLE_AI_API_KEY") or config.get("google_ai_api_key")
            
            if api_key:
                # Configure the Gemini API with the API key
                genai.configure(api_key=api_key)
                logger.info("Google AI client configured successfully.")
                
                # List models to verify connectivity and get available models
                models = self._get_google_ai_models(apply_default_filter=False) # Get unfiltered list for init check
                if models:
                    self.is_online = True
                    logger.info(f"Google AI API connected successfully. Available models: {models}")
                    
                    # Set current model to preferred or first available
                    model_name = config.get("google_ai_model_name", "gemma-3-27b-it")
                    if model_name in models:
                        self.current_model = model_name
                    elif models: # If preferred model not found, use first available
                        self.current_model = models[0]
                    else: # Fallback if no models are found (shouldn't happen if API is connected)
                        self.current_model = "gemini-pro"
                    
                    logger.debug(f"Set current Google AI model to: {self.current_model}")

                    # Initialize the GenerativeModel instance.
                    # Note: system_instruction is NOT passed here, it's dynamic per request in _make_google_ai_request
                    self.gemini_client = genai.GenerativeModel(model_name=self.current_model)
                    logger.info(f"Initialized Google AI GenerativeModel instance for model: {self.current_model}")
                else:
                    self.is_online = False
                    logger.warning("No Google AI models available or failed to list models. Cloud models will not be available.")
            else:
                logger.warning("Google AI API key not found - Cloud models will not be available.")
                self.is_online = False
        except Exception as e:
            logger.error(f"Error initializing Google AI client: {e}", exc_info=True)
            self.is_online = False
    
    def _get_google_ai_models(self, apply_default_filter: bool = True, include_all_gemini_pro_vision_tts: bool = False) -> List[str]:
        """
        Get list of available Google AI models, with filtering options.

        Args:
            apply_default_filter (bool): If True, applies the strict default filter (gemma and 2.5 flash).
                                         If False, returns all supported models.
            include_all_gemini_pro_vision_tts (bool): If True, and apply_default_filter is also True,
                                                    expands the default filter to include all 'pro',
                                                    'vision', 'tts' models. This parameter is ignored if
                                                    apply_default_filter is False.
        Returns:
            List[str]: Filtered list of model names.
        """
        try:
            # List available models that support generateContent method
            all_models = [model.name.split('/')[-1] for model in genai.list_models() if 'generateContent' in model.supported_generation_methods]
            
            if not apply_default_filter:
                return sorted(all_models) # Return all models if no default filter requested
            
            filtered_models = set() # Use a set to avoid duplicates
            
            # Filter 1: Gemma models
            for model_name in all_models:
                if model_name.lower().startswith("gemma-"):
                    filtered_models.add(model_name)
            
            # Filter 2: Gemini 2.5 Flash models (excluding TTS variants)
            for model_name in all_models:
                if model_name.lower().startswith("gemini-2.5-flash-") and "tts" not in model_name.lower():
                    filtered_models.add(model_name)
                    
            # Filter 3 (Conditional): Include all 'pro', 'vision', 'tts' models if requested
            if include_all_gemini_pro_vision_tts:
                for model_name in all_models:
                    model_lower = model_name.lower()
                    # Only add if it contains 'pro', 'vision', or 'tts' and is a 'gemini' or 'gemma' model
                    if ("pro" in model_lower or "vision" in model_lower or "tts" in model_lower) and \
                       (model_lower.startswith("gemini-") or model_lower.startswith("gemma-")):
                         filtered_models.add(model_name)
            
            # Sort the final list for consistent display
            return sorted(list(filtered_models))
        except Exception as e:
            logger.error(f"Error getting Google AI models: {e}", exc_info=True)
            return []

    @commands.command(name='ask', help='Ask the LLM a question')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def ask_llm(self, ctx, *, question: str):
        """Ask the LLM a question without showing thinking process"""
        logger.info(f"User {ctx.author} asking LLM question in {ctx.guild.name if ctx.guild else 'DM'}: {question[:100]}{'...' if len(question) > 100 else ''}")
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)
        
        provider = config.get("provider", "local") # Get provider from the loaded LLM config
        
        if provider == "local" and not config.get('enabled', False):
            logger.warning(f"Local LLM request denied - feature disabled for guild {ctx.guild.id if ctx.guild else 'DM'}")
            await create_embed_response(
                ctx,
                "The local LLM feature is not enabled. Please ask an administrator to enable it in the bot configuration.",
                title="LLM Disabled",
                color=discord.Color.red()
            )
            return
        
        # For Google AI, check if it's initialized and online
        if provider == "google_ai" and not self.is_online:
            logger.warning(f"Google AI LLM request denied - API not initialized or offline.")
            await create_embed_response(
                ctx,
                "The Google AI LLM is not available. Please ensure your API key is set and valid (`!llm_set_api_key`).",
                title="Google AI Offline",
                color=discord.Color.red()
            )
            return


        # Send typing indicator
        async with ctx.typing():
            try:
                logger.debug(f"Making LLM request for user {ctx.author}")
                response, performance_metrics = await self.make_llm_request(question, thinking=False, guild_id=ctx.guild.id if ctx.guild else None)
                cleaned_response, _ = self.strip_thinking_tokens(response)
                await self.send_llm_response(ctx, cleaned_response, question, thinking=False, performance_metrics=performance_metrics)
                logger.info(f"Successfully processed LLM request for user {ctx.author}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"LLM request failed for user {ctx.author}: {e}", exc_info=True)
                if "offline" in error_msg.lower():
                    await create_embed_response(
                        ctx,
                        f"The LLM appears to be offline. Please check that your local LLM server is running at `{config.get('base_url', 'http://localhost:1234')}`.\n\nTrying to reconnect...",
                        title="LLM Offline",
                        color=discord.Color.orange()
                    )
                else:
                    await create_embed_response(
                        ctx,
                        f"An error occurred while communicating with the LLM:\n```{error_msg}```",
                        title="LLM Error",
                        color=discord.Color.red()
                    )
    
    @commands.command(name='think', help='Ask the LLM a question and show its thinking process\nArguments: display_thinking - Show thinking tokens (default: False), question - The question to ask\nExample: !think true What is 2+2?')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def think_llm(self, ctx, display_thinking: Optional[bool] = False, *, question: str):
        """Ask the LLM a question and show the thinking process"""
        logger.info(f"User {ctx.author} using think command in {ctx.guild.name if ctx.guild else 'DM'}: {question[:100]}{'...' if len(question) > 100 else ''}")
        
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)        # Check LLM provider and then check if enabled accordingly
        # Get current provider from chatbot_manager
        from utils.chatbot_manager import chatbot_manager, DEFAULT_CHATBOT_CONFIG
        global_config = chatbot_manager.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
        provider = global_config.get("llm_provider", "local")

        if provider == "local" and not config.get('enabled', False):
            logger.warning(f"Local LLM think request denied - feature disabled for guild {ctx.guild.id if ctx.guild else 'DM'}")
            await create_embed_response(
                ctx,
                "The local LLM feature is not enabled. Please ask an administrator to enable it in the bot configuration.",
                title="LLM Disabled",
                color=discord.Color.red()
            )
            return
        
        # For Google AI, check if it's initialized and online
        if provider == "google_ai" and not self.is_online:
            logger.warning(f"Google AI LLM think request denied - API not initialized or offline.")
            await create_embed_response(
                ctx,
                "The Google AI LLM is not available. Please ensure your API key is set and valid (`!llm_set_api_key`).",
                title="Google AI Offline",
                color=discord.Color.red()
            )
            return

        # Send typing indicator
        async with ctx.typing():
            try:
                logger.debug(f"Making LLM thinking request for user {ctx.author}")
                response, performance_metrics = await self.make_llm_request(question, thinking=True, guild_id=ctx.guild.id if ctx.guild else None)
                # Strip thinking tokens if display_thinking is False
                if not display_thinking:
                    cleaned_response, _ = self.strip_thinking_tokens(response)
                    response = cleaned_response
                
                await self.send_llm_response(ctx, response, question, thinking=True, performance_metrics=performance_metrics)
                logger.info(f"Successfully processed LLM thinking request for user {ctx.author}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"LLM thinking request failed for user {ctx.author}: {e}", exc_info=True)
                if "offline" in error_msg.lower():
                    await create_embed_response(
                        ctx,
                        f"The LLM appears to be offline. Please check that your local LLM server is running at `{config.get('base_url', 'http://localhost:1234')}`.\n\nTrying to reconnect...",
                        title="LLM Offline",
                        color=discord.Color.orange()
                    )
                else:
                    await create_embed_response(
                        ctx,
                        f"An error occurred while processing your request: {error_msg}",
                        title="LLM Error",
                        color=discord.Color.red()
                    )
    
    @commands.command(name='llm_status', help='Check the status of the LLM connection')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def llm_status(self, ctx):
        """Check the status of the LLM connection"""
        logger.info(f"User {ctx.author} checking LLM status in {ctx.guild.name if ctx.guild else 'DM'}")
        
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)
        provider = config.get("provider", "local") # Get provider from the loaded LLM config
        
        status_emoji = "❓"
        status_text = "Unknown"
        color = discord.Color.greyple()
        model_display = self.current_model or "Not configured"
        
        if provider == "local":
            if not config.get('enabled', False):
                logger.debug(f"LLM status check - local LLM disabled for guild {ctx.guild.id if ctx.guild else 'DM'}")
                await create_embed_response(
                    ctx,
                    "❌ Local LLM is disabled in configuration.",
                    title="LLM Status",
                    color=discord.Color.red()
                )
                return

            # Force a status check for local LLM
            logger.debug("Performing local LLM status check")
            is_online = await self.check_llm_status(ctx.guild.id if ctx.guild else None)
            
            status_emoji = "✅" if is_online else "❌"
            status_text = "Online" if is_online else "Offline"
            color = discord.Color.green() if is_online else discord.Color.red()
            model_display = self.current_model or config.get('model', 'Not configured')
            
            await create_embed_response(
                ctx,
                f"{status_emoji} **Status**: {status_text}\n"
                f"🌐 **Provider**: Local LLM at `{config.get('base_url', 'Not configured')}`\n"
                f"🤖 **Model**: `{model_display}`\n"
                f"⏱️ **Timeout**: {config.get('timeout', 120)} seconds",
                title="LLM Status",
                color=color
            )
        elif provider == "google_ai":
            # For Google AI, status is determined by _init_google_ai
            is_online = self.is_online
            status_emoji = "✅" if is_online else "❌"
            status_text = "Online" if is_online else "Offline"
            color = discord.Color.green() if is_online else discord.Color.red()
            
            model_display = self.current_model or config.get("google_ai_model_name", "gemma-3-27b-it")
            
            await create_embed_response(
                ctx,
                f"{status_emoji} **Status**: {status_text}\n"
                f"🌐 **Provider**: Google AI (Cloud)\n"
                f"🤖 **Model**: `{model_display}`\n"
                f"🔑 **API Key Status**: {'Configured' if config.get('google_ai_api_key') else 'Not Set'}",
                title="LLM Status",
                color=color
            )
        
        logger.info(f"LLM status check result: {status_text}, model: {model_display}")
    
    @commands.command(name='llm_models', help='List available models for the current LLM provider (local or Google AI)\nArguments: filters - "all", "pro_vision_tts", or leave empty for default (gemma/2.5-flash)\nExample: !llm_models pro_vision_tts')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def list_models(self, ctx, filters: Optional[str] = None):
        """List all available models for the current LLM provider with optional filters"""
        logger.info(f"User {ctx.author} requesting model list in {ctx.guild.name if ctx.guild else 'DM'} with filters: {filters}")
        
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)        # Get current provider from chatbot_manager
        provider = config.get("provider", "local")
        
        # For local provider, check if LLM is enabled
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)
        if provider == "local" and not config.get('enabled', False):
            logger.warning(f"Model list request denied - local LLM feature disabled for guild {ctx.guild.id if ctx.guild else 'DM'}")
            await create_embed_response(
                ctx,
                "The local LLM feature is not enabled. Please ask an administrator to enable it in the bot configuration.",
                title="LLM Disabled",
                color=discord.Color.red()
            )
            return
        
        async with ctx.typing():
            try:
                # Determine filtering parameters for _get_google_ai_models
                apply_default_filter = True
                include_all_gemini_pro_vision_tts = False
                filter_description = "gemma and 2.5 flash variants"

                if filters:
                    filters_lower = filters.lower()
                    if filters_lower == "all":
                        apply_default_filter = False
                        filter_description = "all supported models"
                    elif filters_lower == "pro_vision_tts":
                        apply_default_filter = True # Still applies default filter but expands it
                        include_all_gemini_pro_vision_tts = True
                        filter_description = "pro, vision, tts, gemma, and 2.5 flash models"
                    else:
                        await create_embed_response(
                            ctx,
                            f"Invalid filter option: `{filters}`. Use `all`, `pro_vision_tts`, or leave empty for default.",
                            title="Invalid Filter",
                            color=discord.Color.orange()
                        )
                        return
                
                # Get models based on provider
                if provider == "google_ai":
                    models = self._get_google_ai_models(apply_default_filter=apply_default_filter,
                                                        include_all_gemini_pro_vision_tts=include_all_gemini_pro_vision_tts)
                    provider_name = "Google AI"
                    current_model = config.get("google_ai_model_name", "gemma-3-27b-it")
                    provider_info = "Google AI (cloud)"
                else: # local provider
                    models = await self.get_available_models(ctx.guild.id if ctx.guild else None, verbose_logging=True)
                    provider_name = "Local LLM"
                    current_model = self.current_model # This should reflect the model chosen by cog_load or a previous select
                    filter_description = "all local models" # Filters don't apply to local models
                    provider_info = f"local server at `{config.get('base_url', 'http://localhost:1234')}`"
                
                if not models:
                    logger.warning(f"No models found for {provider} provider for guild {ctx.guild.id if ctx.guild else 'DM'}")
                    
                    if provider == "google_ai":
                        error_message = "No Google AI models found. Please check your API key with `!llm_set_api_key` and ensure connectivity."
                    else:
                        error_message = f"No models found on the local LLM server at `{config.get('base_url', 'http://localhost:1234')}`. Please check that the server is running and has models loaded."
                    
                    await create_embed_response(
                        ctx,
                        error_message,
                        title="No Models Found",
                        color=discord.Color.orange()
                    )
                    return
                
                # Format the models list
                model_list = []
                for i, model in enumerate(models, 1):
                    # Mark current model with an indicator
                    indicator = "🟢 " if model == current_model else "⚪ "
                    
                    preferred_mark = ""
                    if provider == "local":
                        # For local LLM, we save a preferred model in server config
                        server_config = self.get_llm_config(ctx.guild.id if ctx.guild else None)
                        if model == server_config.get("preferred_model"):
                            preferred_mark = " (preferred for this server)"
                    elif provider == "google_ai":
                        # For Google AI, the selected model is global
                        if model == config.get("google_ai_model_name"):
                            preferred_mark = " (selected)"

                    model_list.append(f"{indicator}{i}. `{model}`{preferred_mark}")
                
                description = f"Available {provider_name} models ({filter_description}) on {provider_info}:\n\n"
                description += "\n".join(model_list)
                description += f"\n\n🟢 = Currently active/selected model\nUse `!llm_select <model_name>` or `!llm_select <number>` to select a different model"
                
                logger.info(f"Successfully retrieved {len(models)} models for user {ctx.author}")
                await create_embed_response(
                    ctx,
                    description,
                    title="Available LLM Models",
                    color=discord.Color.blue()
                )
                
            except Exception as e:
                logger.error(f"Failed to retrieve models for user {ctx.author}: {e}", exc_info=True)
                await create_embed_response(
                    ctx,
                    f"Failed to retrieve models from the LLM server: {str(e)}",
                    title="Error",
                    color=discord.Color.red()
                )
    
    @commands.command(name='llm_select', help='Select a specific model to use for LLM requests (works with both local and Google AI models)\nArguments: model_name - The name or number of the model to select\nExample: !llm_select gpt-3.5-turbo OR !llm_select 2 OR !llm_select gemini-pro')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def select_model(self, ctx, *, model_input: str):
        """Select a specific model for LLM requests for both local and Google AI providers"""
        logger.info(f"User {ctx.author} attempting to select model '{model_input}' in {ctx.guild.name if ctx.guild else 'DM'}")
        
        config = self.get_llm_config(ctx.guild.id if ctx.guild else None)        # Get the global configuration to check the provider
        provider = config.get("provider", "local")
        
        # Get the appropriate config based on provider
        
        if not config.get('enabled', False) and provider == "local":
            logger.warning(f"Model selection denied - feature disabled for guild {ctx.guild.id if ctx.guild else 'DM'}")
            await create_embed_response(
                ctx,
                "The LLM feature is not enabled. Please ask an administrator to enable it in the bot configuration.",
                title="LLM Disabled",
                color=discord.Color.red()
            )
            return
        
        async with ctx.typing():
            try:
                # Get ALL available models for validation (both by name and number)
                models = []
                if provider == "google_ai":
                    models = self._get_google_ai_models(apply_default_filter=False) # Get unfiltered list for selection
                    if not models:
                        await create_embed_response(
                            ctx,
                            f"Failed to get available Google AI models.\nPlease check your API key with `!llm_set_api_key`.",
                            title="Error",
                            color=discord.Color.red()
                        )
                        return
                else:  # local provider
                    models = await self.get_available_models(ctx.guild.id if ctx.guild else None, verbose_logging=True)
                    
                    if not models:
                        logger.warning(f"No models available for selection in guild {ctx.guild.id if ctx.guild else 'DM'}")
                        await create_embed_response(
                            ctx,
                            f"No models found on the LLM server. Please check that the server is running.",
                            title="No Models Available",
                            color=discord.Color.orange()
                        )
                        return
                
                # Check if user provided a number instead of a model name
                model_name = model_input.strip()
                try:
                    model_number = int(model_input.strip())
                    # If input is a valid number and within range, convert to model name
                    if 1 <= model_number <= len(models):
                        model_name = models[model_number - 1]
                        logger.debug(f"Converted model number {model_number} to model name '{model_name}'")
                    else:
                        await create_embed_response(
                            ctx,
                            f"Model number {model_number} is out of range. Available models are numbered from 1 to {len(models)}.",
                            title="Invalid Model Number",
                            color=discord.Color.orange()
                        )
                        return
                except ValueError:
                    # Input was not a number, continue with model name
                    pass
                
                # Check if the requested model is available
                if model_name not in models:
                    logger.info(f"Model '{model_name}' not found, looking for partial matches")
                    # Try to find a partial match
                    partial_matches = [m for m in models if model_name.lower() in m.lower()]
                    
                    # If exactly one partial match, auto-select it
                    if len(partial_matches) == 1:
                        model_name = partial_matches[0]
                        logger.info(f"Auto-selecting the only matching model: {model_name}")
                    elif partial_matches:
                        suggestion = f"\n\nDid you mean one of these?\n" + "\n".join([f"• `{m}`" for m in partial_matches[:5]])
                        await create_embed_response(
                            ctx,
                            f"Model `{model_name}` not found.{suggestion}",
                            title="Model Not Found",
                            color=discord.Color.orange()
                        )
                        return
                    else:
                        suggestion = f"\n\nAvailable models:\n" + "\n".join([f"• `{m}`" for m in models[:10]])
                        await create_embed_response(
                            ctx,
                            f"Model `{model_name}` not found.{suggestion}",
                            title="Model Not Found",
                            color=discord.Color.orange()
                        )
                        return
                
                # Handle model selection based on provider
                if provider == "google_ai":
                    # Update model in the global config
                    old_model = config.get("google_ai_model_name", "gemma-3-27b-it")
                    # Save the updated model name to the LLM config file
                    try:
                        from config.llm_config_manager import load_llm_config, save_llm_config
                        
                        # Load the actual LLM config
                        llm_config_to_save = load_llm_config()
                        
                        # Update the model name
                        llm_config_to_save["google_ai_model_name"] = model_name
                        
                        # Save the updated config
                        success = save_llm_config(llm_config_to_save)
                        config_for_init = llm_config_to_save # Use this config for re-initialization
                        
                    except ImportError:
                        # Fallback to chatbot_manager if llm_config_manager is not available
                        logger.warning("LLM config manager not available for saving Google AI model, falling back to chatbot_manager")
                        from utils.chatbot_manager import chatbot_manager, DEFAULT_CHATBOT_CONFIG
                        global_config = chatbot_manager.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
                        
                        # Update API key in the config
                        global_config["google_ai_model_name"] = model_name
                        
                        # Save the config
                        chatbot_manager.config_cache["global"] = global_config
                        success = chatbot_manager.save_config()
                        config_for_init = global_config # Use this config for re-initialization
                    
                    if not success:
                        await create_embed_response(
                            ctx,
                            f"Failed to save configuration. Model not changed.",
                            title="Error",
                            color=discord.Color.red()
                        )
                        return
                    
                    # Update current model and re-initialize Google AI client for new model
                    self.current_model = model_name
                    self._init_google_ai(config_for_init) # Re-init the client with the saved config
                    
                    if not self.is_online:
                        await create_embed_response(
                            ctx,
                            f"Successfully set Google AI model to `{model_name}`, but failed to connect.\nPlease check your API key with `!llm_set_api_key`.",
                            title="Model Updated - Connection Failed",
                            color=discord.Color.orange()
                        )
                        return

                    await create_embed_response(
                        ctx,
                        f"Successfully set Google AI model to `{model_name}`. This model will now be used globally.",
                        title="Model Updated",
                        color=discord.Color.green()
                    )
                    
                    logger.info(f"Google AI model changed from {old_model} to {model_name} by {ctx.author}")
                else:  # local provider
                    # Update preferred model and save to config
                    old_model = self.preferred_model
                    self.preferred_model = model_name
                    self.current_model = model_name # Set current model here immediately
                    logger.debug(f"Updated current local model from '{old_model}' to '{model_name}'")
                    
                    # Save to config
                    await self.save_model_to_config(model_name, ctx.guild.id if ctx.guild else None)
                    
                    # Test the model by making a simple request
                    try:
                        logger.debug(f"Testing local model '{model_name}' with simple request")
                        _, _ = await self.make_llm_request("Hello", max_tokens=10, guild_id=ctx.guild.id if ctx.guild else None)
                        
                        logger.info(f"Successfully selected and tested local model '{model_name}' for user {ctx.author}")
                        await create_embed_response(
                            ctx,
                            f"Successfully selected local model: `{model_name}`\n\nThis model will now be used for all local LLM requests and will be remembered for future sessions.",
                            title="Model Selected",
                            color=discord.Color.green()
                        )
                        
                    except Exception as test_error:
                        # Revert to old model if test fails
                        logger.warning(f"Local model test failed for '{model_name}', reverting to '{old_model}': {test_error}")
                        self.preferred_model = old_model
                        self.current_model = old_model
                        
                        await create_embed_response(
                            ctx,
                            f"Failed to connect to local model `{model_name}`: {str(test_error)}\n\nModel selection reverted to previous model.",
                            title="Model Test Failed",
                            color=discord.Color.red()
                        )
                    
            except Exception as e:
                logger.error(f"Failed to select model '{model_name}' for user {ctx.author}: {e}", exc_info=True)
                await create_embed_response(
                    ctx,
                    f"Failed to select model: {str(e)}",
                    title="Error",
                    color=discord.Color.red()
                )    
    
    @commands.command(name='llm_provider', help='Switch between locally hosted LLM and Google AI (cloud)\nArguments: provider - "local" or "google_ai"\nExample: !llm_provider google_ai')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def set_llm_provider(self, ctx, provider: str):
        """Set the LLM provider to use (local or google_ai)"""
        logger.info(f"User {ctx.author} attempting to set LLM provider to '{provider}' in {ctx.guild.name if ctx.guild else 'DM'}")
        
        provider = provider.lower()
        if provider not in ["local", "google_ai"]:
            await create_embed_response(
                ctx,
                f"Invalid provider: '{provider}'. Valid options are 'local' or 'google_ai'.",
                title="Invalid Provider",
                color=discord.Color.red()
            )
            return
        
        async with ctx.typing():
            try:
                from config.llm_config_manager import load_llm_config, save_llm_config
                
                # Load current config
                llm_config = load_llm_config()
                old_provider = llm_config.get("provider", "local")
                
                # Update provider in the config
                llm_config["provider"] = provider
                
                # Save the config
                success = save_llm_config(llm_config)
                
                if not success:
                    await create_embed_response(
                        ctx,
                        f"Failed to save configuration. Provider not changed.",
                        title="Error",
                        color=discord.Color.red()
                    )
                    return
            except ImportError:
                # Fallback to chatbot_manager if llm_config_manager is not available
                logger.warning("LLM config manager not available, falling back to chatbot_manager")
                from utils.chatbot_manager import chatbot_manager, DEFAULT_CHATBOT_CONFIG
                global_config = chatbot_manager.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
                old_provider = global_config.get("llm_provider", "local")
                
                # Update provider in the config
                global_config["llm_provider"] = provider
                
                # Save the config
                chatbot_manager.config_cache["global"] = global_config
                success = chatbot_manager.save_config()
                
                if not success:
                    await create_embed_response(
                        ctx,
                        f"Failed to save configuration. Provider not changed.",
                        title="Error",
                        color=discord.Color.red()
                    )
                    return
            
            # Update current provider in instance
            self.llm_provider = provider
            
            # Get config for provider initialization
            try:
                from config.llm_config_manager import load_llm_config
                config_for_init = load_llm_config()
            except ImportError:
                from utils.chatbot_manager import chatbot_manager
                config_for_init = chatbot_manager.config_cache.get("global", {})
            
            # Initialize provider-specific components
            if provider == "google_ai":
                # Try to initialize Google AI client
                self._init_google_ai(config_for_init)
                
                if not self.is_online:
                    # If we can't initialize, provide detailed error
                    await create_embed_response(
                        ctx,
                        f"Failed to connect to Google AI API. Please check your API key with `!llm_set_api_key`.\n\nProvider changed to {provider}, but connection failed.",
                        title="Connection Failed",
                        color=discord.Color.orange()
                    )
                    return
                
                await create_embed_response(
                    ctx,
                    f"Successfully switched to Google AI provider.\n\nUse `!llm_models` to see available models and `!llm_select` to select one.",
                    title="Provider Changed",
                    color=discord.Color.green()
                )
                
            else:  # local
                # Check if the local LLM is online
                await self.check_llm_status()
                
                if not self.is_online:
                    await create_embed_response(
                        ctx,
                        f"Provider changed to {provider}, but local LLM appears to be offline.\nMake sure your local LLM server is running.",
                        title="Provider Changed - Warning",
                        color=discord.Color.orange()
                    )
                    return
                    
                await create_embed_response(
                    ctx,
                    f"Successfully switched to local LLM provider.\n\nUse `!llm_models` to see available models and `!llm_select` to select one.",
                    title="Provider Changed",
                    color=discord.Color.green()
                )
            
            logger.info(f"LLM provider changed from {old_provider} to {provider} by {ctx.author}")
            


    @commands.command(name='llm_set_api_key', help='Set Google AI API key for cloud LLM\nArguments: api_key - Your Google AI API key\nExample: !llm_set_api_key YOUR_API_KEY')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def set_google_ai_api_key(self, ctx, api_key: str):
        """Set the Google AI API key for cloud LLM"""
        logger.info(f"User {ctx.author} attempting to set Google AI API key in {ctx.guild.name if ctx.guild else 'DM'}")
        
        # Delete the user's message to protect the API key
        try:
            await ctx.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message with API key: {e}")
        
        async with ctx.typing():
            try:
                # Use the new LLM config system
                from config.llm_config_manager import load_llm_config, save_llm_config
                
                # Load current config
                llm_config = load_llm_config()
                
                # Update API key in the config
                llm_config["google_ai_api_key"] = api_key
                
                # Save the config
                success = save_llm_config(llm_config)
            except ImportError:
                # Fall back to chatbot_manager if llm_config_manager is not available
                logger.warning("LLM config manager not available, falling back to chatbot_manager")
                from utils.chatbot_manager import chatbot_manager, DEFAULT_CHATBOT_CONFIG
                global_config = chatbot_manager.config_cache.get("global", DEFAULT_CHATBOT_CONFIG)
                
                # Update API key in the config
                global_config["google_ai_api_key"] = api_key
                
                # Save the config
                chatbot_manager.config_cache["global"] = global_config
                success = chatbot_manager.save_config()
            
            if not success:
                await create_embed_response(
                    ctx,
                    f"Failed to save configuration. API key not updated.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            # Try to initialize Google AI client with the new key
            # Pass the updated config, which now includes the new API key
            self._init_google_ai(llm_config) # Use llm_config here as it's updated
            
            if not self.is_online:
                await create_embed_response(
                    ctx,
                    f"API key saved, but failed to connect to Google AI API.\nPlease check that the key is valid and you have models available.",
                    title="API Key Saved - Connection Failed",
                    color=discord.Color.orange()
                )
                return
                
            await create_embed_response(
                ctx,
                f"API key saved successfully and connection verified.\n\nUse `!llm_provider google_ai` to switch to Google AI provider.",
                title="API Key Saved",
                color=discord.Color.green()
            )
            
            logger.info(f"Google AI API key updated by {ctx.author}")
    
    @commands.command(name='chatbot_enable')
    @has_command_permission("chatbot_enable")
    @command_category("AI Assistant")
    async def chatbot_enable(self, ctx):
        """Enable chatbot mode for this channel"""
        try:
            from utils.chatbot_manager import chatbot_manager
            
            guild_id = ctx.guild.id if ctx.guild else None
            channel_id = ctx.channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "Chatbot mode can only be enabled in server channels, not in DMs.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            # Check if LLM is configured and online for the current provider
            current_llm_config = self.get_llm_config(guild_id)
            current_provider = current_llm_config.get("provider", "local")

            is_online = False
            if current_provider == "local":
                is_online = await self.check_llm_status(guild_id)
            elif current_provider == "google_ai":
                is_online = self.is_online # Status is set by _init_google_ai

            if not is_online:
                provider_name = "LLM service"
                if current_provider == "local":
                    provider_name = f"Local LLM server at `{current_llm_config.get('base_url', 'http://localhost:1234')}`"
                elif current_provider == "google_ai":
                    provider_name = "Google AI API"
                    if not current_llm_config.get('google_ai_api_key'):
                        provider_name += " (API key not set)"

                await create_embed_response(
                    ctx,
                    f"The {provider_name} is not available. Please ensure it is running and accessible.",
                    title="LLM Service Unavailable",
                    color=discord.Color.red()
                )
                return

            # Pass guild and channel objects to enable_chatbot for indexing
            success = await chatbot_manager.enable_chatbot(guild_id, channel_id, ctx.guild, ctx.channel)

            if success:
                channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
                await create_embed_response(
                    ctx,
                    f"✅ Chatbot mode enabled for {ctx.channel.mention}\n\n"
                    f"**Configuration:**\n"
                    f"• Responds to mentions: {'Yes' if channel_config.auto_respond_to_mentions else 'No'}\n"
                    f"• Responds to replies: {'Yes' if channel_config.auto_respond_to_replies else 'No'}\n"
                    f"• Context window: {channel_config.context_window_hours} hours\n"
                    f"• Max context messages: {channel_config.max_context_messages}\n"
                    f"• Max user context messages: {channel_config.max_user_context_messages}\n\n"
                    f"The bot will now respond when mentioned or when users reply to its messages in this channel.",
                    title="Chatbot Mode Enabled",
                    color=discord.Color.green()
                )
                logger.info(f"Chatbot mode enabled for channel {ctx.channel.name} ({channel_id}) in guild {ctx.guild.name} ({guild_id}) by {ctx.author}")
            else:
                await create_embed_response(
                    ctx,
                    "Failed to enable chatbot mode. Please try again.",
                    title="Error",
                    color=discord.Color.red()
                )
                
        except Exception as e:
            logger.error(f"Error enabling chatbot mode: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while enabling chatbot mode: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )   
    
    @commands.command(name='chatbot_disable')
    @has_command_permission("chatbot_disable")
    @command_category("AI Assistant")
    async def chatbot_disable(self, ctx):
        """Disable chatbot mode for this channel"""
        try:
            from utils.chatbot_manager import chatbot_manager
            
            guild_id = ctx.guild.id if ctx.guild else None
            channel_id = ctx.channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "This command can only be used in server channels, not in DMs.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            # Get current conversation history count before clearing
            current_history = chatbot_manager.load_conversation_history(guild_id, channel_id)
            message_count = len(current_history)
            
            success = chatbot_manager.disable_chatbot(guild_id, channel_id)
            
            if success:
                # Clear conversation history when disabling chatbot
                history_cleared = chatbot_manager.save_conversation_history(guild_id, channel_id, [])
                
                # Also delete the physical conversation file
                conversation_file_path = chatbot_manager.get_conversation_file_path(guild_id, channel_id)
                file_deleted = False
                try:
                    if os.path.exists(conversation_file_path):
                        os.remove(conversation_file_path)
                        file_deleted = True
                        logger.debug(f"Deleted conversation file: {conversation_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete conversation file {conversation_file_path}: {e}")
                
                history_msg = ""
                if history_cleared and message_count > 0:
                    history_msg = f"\n\n🗑️ Cleared {message_count} messages from conversation history"
                    if file_deleted:
                        history_msg += " and deleted conversation file."
                    else:
                        history_msg += "."
                
                await create_embed_response(
                    ctx,
                    f"❌ Chatbot mode disabled for {ctx.channel.mention}\n\n"
                    f"The bot will no longer automatically respond to mentions or replies in this channel. "
                    f"You can still use regular LLM commands like `ask` and `think`.{history_msg}",
                    title="Chatbot Mode Disabled",
                    color=discord.Color.orange()
                )
                logger.info(f"Chatbot mode disabled for channel {ctx.channel.name} ({channel_id}) in guild {ctx.guild.name} ({guild_id}) by {ctx.author}. Cleared {message_count} messages from history.")
            else:
                await create_embed_response(
                    ctx,
                    "Failed to disable chatbot mode. Please try again.",
                    title="Error",
                    color=discord.Color.red()
                )
                
        except Exception as e:
            logger.error(f"Error disabling chatbot mode: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while disabling chatbot mode: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )    
    
    @commands.command(name='chatbot_status')
    @has_command_permission("chatbot_status")
    @command_category("AI Assistant")
    async def chatbot_status(self, ctx):
        """Show chatbot mode status and configuration for this channel"""
        try:
            from utils.chatbot_manager import chatbot_manager
            
            guild_id = ctx.guild.id if ctx.guild else None
            channel_id = ctx.channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "This command can only be used in server channels, not in DMs.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
            conversation_history = chatbot_manager.load_conversation_history(guild_id, channel_id)
            
            status_emoji = "🟢" if channel_config.enabled else "🔴"
            status_text = "Enabled" if channel_config.enabled else "Disabled"
            
            # Calculate conversation stats
            total_messages = len(conversation_history)
            user_messages = len([msg for msg in conversation_history if not msg.is_bot_response])
            bot_messages = len([msg for msg in conversation_history if msg.is_bot_response])
            
            # Get recent activity
            if conversation_history:
                latest_msg = max(conversation_history, key=lambda x: x.timestamp)
                last_activity = datetime.fromtimestamp(latest_msg.timestamp).strftime("%Y-%m-%d %H:%M")
            else:
                last_activity = "No activity"
            
            embed_description = f"**Status:** {status_emoji} {status_text}\n\n"
            
            if channel_config.enabled:
                embed_description += (
                    f"**Configuration:**\n"
                    f"• Auto-respond to mentions: {'✅' if channel_config.auto_respond_to_mentions else '❌'}\n"
                    f"• Auto-respond to replies: {'✅' if channel_config.auto_respond_to_replies else '❌'}\n"
                    f"• Context window: {channel_config.context_window_hours} hours\n"
                    f"• Max context messages: {channel_config.max_context_messages}\n"
                    f"• Max user context messages: {channel_config.max_user_context_messages}\n"
                    f"• Response delay: {channel_config.response_delay_seconds} seconds\n"
                    f"• Max response length: {channel_config.max_response_length} characters\n"
                    f"• Auto prune: {'✅' if channel_config.auto_prune_enabled else '❌'} (every {channel_config.prune_interval_hours} hrs)\n\n"
                    f"**Conversation Stats:**\n"
                    f"• Total messages in context: {total_messages}\n"
                    f"• User messages: {user_messages}\n"
                    f"• Bot responses: {bot_messages}\n"
                    f"• Last activity: {last_activity}\n\n"
                )
            else:
                embed_description += "Use `chatbot_enable` to enable chatbot mode for this channel."
            
            color = discord.Color.green() if channel_config.enabled else discord.Color.red()
            
            await create_embed_response(
                ctx,
                embed_description,
                title=f"Chatbot Status - #{ctx.channel.name}",
                color=color
            )
            
        except Exception as e:
            logger.error(f"Error getting chatbot status: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while getting chatbot status: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

    @commands.command(name='chatbot_config')
    @has_command_permission("chatbot_config")
    @command_category("AI Assistant")
    async def chatbot_config(self, ctx, setting: str = None, value: str = None):
        """Configure chatbot settings for this channel
        
        Available settings:
        - context_window: Hours to keep messages in context (1-168)
        - max_messages: Maximum messages in context (10-200)
        - max_user_messages: Max messages from requesting user (5-50)
        - response_delay: Delay before responding in seconds (0-10)
        - max_response_length: Maximum response length in characters (100-4000)
        - auto_prune: Enable/disable automatic conversation pruning (true/false)
        - prune_interval: Hours between auto-prune runs (1-48)
        - mentions: Enable/disable auto-response to mentions (true/false)
        - replies: Enable/disable auto-response to replies (true/false)
        """
        try:
            from utils.chatbot_manager import chatbot_manager
            
            guild_id = ctx.guild.id if ctx.guild else None
            channel_id = ctx.channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "This command can only be used in server channels, not in DMs.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            # If no parameters, show help
            if not setting:
                help_text = (
                    "**Available Settings:**\n\n"
                    "• `context_window <hours>` - Hours to keep messages in context (1-168)\n"
                    "• `max_messages <number>` - Maximum messages in context (10-200)\n"
                    "• `max_user_messages <number>` - Max messages from requesting user (5-50)\n"
                    "• `response_delay <seconds>` - Delay before responding (0-10)\n"
                    "• `max_response_length <chars>` - Maximum response length (100-4000)\n"
                    "• `auto_prune <true/false>` - Enable automatic conversation pruning\n"
                    "• `prune_interval <hours>` - Hours between auto-prune runs (1-48)\n"
                    "• `mentions <true/false>` - Auto-respond to mentions\n"
                    "• `replies <true/false>` - Auto-respond to replies\n\n"
                    "**Example:** `!chatbot_config context_window 12`"
                )
                await create_embed_response(
                    ctx,
                    help_text,
                    title="Chatbot Configuration Help",
                    color=discord.Color.blue()
                )
                return
            
            if not value:
                await create_embed_response(
                    ctx,
                    f"Please provide a value for setting '{setting}'",
                    title="Missing Value",
                    color=discord.Color.red()
                )
                return
            
            # Get current config
            channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
            
            # Update setting
            setting = setting.lower()
            if setting == "context_window":
                try:
                    hours = int(value)
                    if 1 <= hours <= 168:  # 1 hour to 1 week
                        channel_config.context_window_hours = hours
                    else:
                        raise ValueError("Hours must be between 1 and 168")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for context_window: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            elif setting == "max_messages":
                try:
                    count = int(value)
                    if 10 <= count <= 200:
                        channel_config.max_context_messages = count
                    else:
                        raise ValueError("Message count must be between 10 and 200")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for max_messages: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            elif setting == "max_user_messages":
                try:
                    count = int(value)
                    if 5 <= count <= 50:
                        channel_config.max_user_context_messages = count
                    else:
                        raise ValueError("User message count must be between 5 and 50")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for max_user_messages: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            elif setting == "response_delay":
                try:
                    delay = float(value)
                    if 0 <= delay <= 10:
                        channel_config.response_delay_seconds = delay
                    else:
                        raise ValueError("Delay must be between 0 and 10 seconds")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for response_delay: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
            
            elif setting == "max_response_length":
                try:
                    length = int(value)
                    if 100 <= length <= 4000: # Discord message limit is 2000, but LLM might produce more
                        channel_config.max_response_length = length
                    else:
                        raise ValueError("Max response length must be between 100 and 4000 characters")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for max_response_length: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
            
            elif setting == "auto_prune":
                if value.lower() in ["true", "yes", "1", "on", "enable"]:
                    channel_config.auto_prune_enabled = True
                elif value.lower() in ["false", "no", "0", "off", "disable"]:
                    channel_config.auto_prune_enabled = False
                else:
                    await create_embed_response(
                        ctx,
                        "Invalid value for auto_prune. Use: true/false, yes/no, 1/0, on/off, enable/disable",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return

            elif setting == "prune_interval":
                try:
                    hours = int(value)
                    if 1 <= hours <= 48:
                        channel_config.prune_interval_hours = hours
                    else:
                        raise ValueError("Prune interval must be between 1 and 48 hours")
                except ValueError as e:
                    await create_embed_response(
                        ctx,
                        f"Invalid value for prune_interval: {str(e)}",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            elif setting == "mentions":
                if value.lower() in ["true", "yes", "1", "on", "enable"]:
                    channel_config.auto_respond_to_mentions = True
                elif value.lower() in ["false", "no", "0", "off", "disable"]:
                    channel_config.auto_respond_to_mentions = False
                else:
                    await create_embed_response(
                        ctx,
                        "Invalid value for mentions. Use: true/false, yes/no, 1/0, on/off, enable/disable",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            elif setting == "replies":
                if value.lower() in ["true", "yes", "1", "on", "enable"]:
                    channel_config.auto_respond_to_replies = True
                elif value.lower() in ["false", "no", "0", "off", "disable"]:
                    channel_config.auto_respond_to_replies = False
                else:
                    await create_embed_response(
                        ctx,
                        "Invalid value for replies. Use: true/false, yes/no, 1/0, on/off, enable/disable",
                        title="Invalid Value",
                        color=discord.Color.red()
                    )
                    return
                    
            else:
                await create_embed_response(
                    ctx,
                    f"Unknown setting '{setting}'. Use the command without parameters to see available settings.",
                    title="Unknown Setting",
                    color=discord.Color.red()
                )
                return
            
            # Save the updated config
            success = chatbot_manager.set_channel_config(guild_id, channel_id, channel_config)
            
            if success:
                await create_embed_response(
                    ctx,
                    f"✅ Updated setting `{setting}` to `{value}`",
                    title="Configuration Updated",
                    color=discord.Color.green()
                )
                logger.info(f"Updated chatbot config for channel {ctx.channel.name} ({channel_id}): {setting} = {value}")
            else:
                await create_embed_response(
                    ctx,
                    "Failed to save configuration. Please try again.",
                    title="Save Failed",
                    color=discord.Color.red()
                )
                
        except Exception as e:
            logger.error(f"Error configuring chatbot: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while configuring chatbot: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )    
    
    @commands.command(name='chatbot_clear_history')
    @has_command_permission("chatbot_clear_history")
    @command_category("AI Assistant")
    async def chatbot_clear_history(self, ctx):
        """Clear conversation history for this channel"""
        try:
            from utils.chatbot_manager import chatbot_manager
            
            guild_id = ctx.guild.id if ctx.guild else None
            channel_id = ctx.channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "This command can only be used in server channels, not in DMs.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            # Load current history to show count
            current_history = chatbot_manager.load_conversation_history(guild_id, channel_id)
            message_count = len(current_history)
            
            # Clear history by saving empty list
            success = chatbot_manager.save_conversation_history(guild_id, channel_id, [])
            
            if success:
                await create_embed_response(
                    ctx,
                    f"✅ Cleared {message_count} messages from conversation history.\n\n"
                    f"The chatbot will start fresh with no previous context in this channel.",
                    title="History Cleared",
                    color=discord.Color.green()
                )
                logger.info(f"Cleared {message_count} messages from chatbot history for channel {ctx.channel.name} ({channel_id}) by {ctx.author}")
            else:
                await create_embed_response(
                    ctx,
                    "Failed to clear conversation history. Please try again.",
                    title="Clear Failed",
                    color=discord.Color.red()
                )
                
        except Exception as e:
            logger.error(f"Error clearing chatbot history: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while clearing history: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

    @commands.command(name='debug_message_filter', aliases=['dbg_filter'])
    @commands.has_permissions(administrator=True)
    async def debug_message_filter(self, ctx, *, test_message: str):
        """Test a message through the filter system (dev only)
        
        Arguments:
        - test_message: The message content to test
        """
        try:
            from utils.chatbot_manager import chatbot_manager, ConversationMessage
            import time
            
            # Create a mock discord.Message object with content and empty attachments/embeds for filter test
            # This is a simplification; a real test might need more mock details.
            class MockAttachment:
                def __init__(self, url, content_type, filename=None):
                    self.url = url
                    self.content_type = content_type
                    self.filename = filename if filename else url.split('/')[-1]

            class MockEmbed:
                def __init__(self, type, url=None, video=None):
                    self.type = type
                    self.url = url
                    self.video = video

            class MockMessage:
                def __init__(self, content, author, id, created_at, attachments=None, embeds=None, reference=None):
                    self.content = content
                    self.author = author
                    self.id = id
                    self.created_at = created_at
                    self.attachments = attachments if attachments is not None else []
                    self.embeds = embeds if embeds is not None else []
                    self.reference = reference
                    self.mentions = [] # simplified for this test
                    self.type = discord.MessageType.default

            mock_author = ctx.author # Use actual author for realistic user ID
            
            # Extract content and potential media from the test_message string for processing
            # This part simulates how a real message would be processed before being added to history
            dummy_discord_message = MockMessage(
                content=test_message,
                author=mock_author,
                id=1234567890,
                created_at=datetime.fromtimestamp(time.time()),
                attachments=[], # For simplicity in this debug, assume no attachments direct from user input string
                embeds=[] # For simplicity, assume no embeds direct from user input string
            )
            
            cleaned_content, image_urls, embed_urls = chatbot_manager._process_discord_message_for_context(dummy_discord_message)
            
            # Create the ConversationMessage using the processed content and extracted URLs
            test_conv_msg = ConversationMessage(
                user_id=mock_author.id,
                username=mock_author.display_name,
                content=cleaned_content, # Use cleaned content
                timestamp=time.time(),
                message_id=12345,
                is_bot_response=False,
                is_self_bot_response=False,
                attachment_urls=image_urls,
                embed_urls=embed_urls
            )
            
            # Test the filter WITH DEBUG MODE ENABLED
            is_valid, debug_steps = chatbot_manager._is_valid_context_message(test_conv_msg, debug_mode=True)
            
            result_emoji = "✅" if is_valid else "❌"
            result_text = "KEPT" if is_valid else "FILTERED"
            
            # Build the analysis results
            analysis_text = "\n".join(debug_steps)
            
            # Create fields for better organization
            fields = [
                {
                    "name": "🔍 Analysis Results",
                    "value": analysis_text,
                    "inline": False
                }
            ]
            
            await create_embed_response(
                ctx,
                f"**Test Message (Initial Content):** `{test_message}`\n"
                f"**Processed Content (to LLM):** `{cleaned_content if cleaned_content else 'No textual content'}`\n"
                f"**Extracted Images:** {', '.join(image_urls) if image_urls else 'None'}\n"
                f"**Extracted Embeds (other):** {', '.join(embed_urls) if embed_urls else 'None'}\n\n"
                f"**Final Result:** {result_emoji} **{result_text}**",
                fields=fields,
                title="Message Filter Test",
                color=discord.Color.green() if is_valid else discord.Color.red()
            )
                
        except Exception as e:
            logger.error(f"Error testing message filter: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while testing the message filter: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

    @commands.command(name='debug_full_context', aliases=['dbg_full'])
    @commands.has_permissions(administrator=True)
    async def debug_full_context(self, ctx, channel: Optional[discord.abc.Messageable] = None, user_id: int = None):
        """Export the complete LLM context to a file (dev only)
        
        Arguments:
        - channel: The channel to debug (defaults to current channel)
        - user_id: The user ID to generate context for (defaults to command author)
        """
        try:
            from utils.chatbot_manager import chatbot_manager
            import tempfile
            import io
            
            guild_id = ctx.guild.id if ctx.guild else None
            # Use specified channel or current channel
            target_channel = channel or ctx.channel
            channel_id = target_channel.id
            
            if not guild_id:
                await create_embed_response(
                    ctx,
                    "This command can only be used in server channels.",
                    title="Error",
                    color=discord.Color.red()
                )
                return
            
            # Check if chatbot is enabled for the target channel
            if not chatbot_manager.is_chatbot_enabled(guild_id, channel_id):
                await create_embed_response(
                    ctx,
                    f"Chatbot mode is not enabled for {target_channel.mention}.",
                    title="Chatbot Not Enabled",
                    color=discord.Color.orange()
                )
                return
            
            # Use provided user_id or default to command author
            target_user_id = user_id if user_id else ctx.author.id
            
            # Get all context components
            context_messages = chatbot_manager.get_prioritized_context(guild_id, channel_id, target_user_id)
            conversation_context = chatbot_manager.format_context_for_llm(context_messages, guild_id, channel_id)
            system_prompt = self.load_system_prompt(guild_id)
            server_context_file_content = self.load_context(guild_id) # Renamed to avoid confusion with conversation context
            channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
            
            # NEW: Get pinned messages context
            pinned_messages_context = chatbot_manager.get_pinned_context_for_llm(guild_id, channel_id)

            # Build complete context file
            content_lines = []
            content_lines.append("=" * 80)
            content_lines.append("LLM CONTEXT DEBUG EXPORT")
            content_lines.append(f"Generated for: {ctx.guild.name} #{target_channel.name}")
            content_lines.append(f"Target User ID: {target_user_id}")
            content_lines.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            content_lines.append("=" * 80)
            content_lines.append("")
            
            # Channel configuration details
            content_lines.append("CHANNEL CONFIGURATION:")
            content_lines.append("-" * 40)
            content_lines.append(f"Enabled: {channel_config.enabled}")
            content_lines.append(f"Max context messages: {channel_config.max_context_messages}")
            content_lines.append(f"Max user context messages: {channel_config.max_user_context_messages}")
            content_lines.append(f"Context window hours: {channel_config.context_window_hours}")
            content_lines.append(f"Response delay seconds: {channel_config.response_delay_seconds}")
            content_lines.append(f"Max response length: {channel_config.max_response_length}")
            content_lines.append(f"Auto prune enabled: {channel_config.auto_prune_enabled}")
            content_lines.append(f"Prune interval hours: {channel_config.prune_interval_hours}")
            content_lines.append(f"Auto respond to mentions: {channel_config.auto_respond_to_mentions}")
            content_lines.append(f"Auto respond to replies: {channel_config.auto_respond_to_replies}")
            content_lines.append("")
            
            # Context statistics
            content_lines.append("CONTEXT STATISTICS:")
            content_lines.append("-" * 40)
            content_lines.append(f"Total messages in context: {len(context_messages)}")
            content_lines.append(f"Messages from target user: {len([msg for msg in context_messages if msg.user_id == target_user_id])}")
            content_lines.append(f"Messages from other users: {len([msg for msg in context_messages if msg.user_id != target_user_id and not msg.is_bot_response])}")
            content_lines.append(f"Bot responses: {len([msg for msg in context_messages if msg.is_bot_response])}")
            
            # Get indexing stats
            indexing_stats = chatbot_manager.get_indexing_stats(guild_id)
            content_lines.append(f"Total users indexed: {indexing_stats['users_indexed']}")
            content_lines.append(f"Total channels indexed: {indexing_stats['channels_indexed']}")
            content_lines.append(f"Total user messages tracked: {indexing_stats['total_user_messages']}")
            content_lines.append("")
            
            # System prompt
            content_lines.append("SYSTEM PROMPT (from file):")
            content_lines.append("-" * 40)
            if system_prompt:
                content_lines.append(system_prompt)
            else:
                content_lines.append("*No custom system prompt configured*")
            content_lines.append("")
            
            # Server context
            content_lines.append("ADDITIONAL SERVER CONTEXT (from file):")
            content_lines.append("-" * 40)
            if server_context_file_content:
                content_lines.append(server_context_file_content)
            else:
                content_lines.append("*No additional server context configured*")
            content_lines.append("")

            # NEW: Pinned Messages
            content_lines.append("PINNED MESSAGES (from index):")
            content_lines.append("-" * 40)
            if pinned_messages_context:
                content_lines.append(pinned_messages_context) # This is already formatted
            else:
                content_lines.append("*No pinned messages indexed for this channel*")
            content_lines.append("")
            
            # Full conversation context
            content_lines.append("FORMATTED CONVERSATION CONTEXT (as sent to LLM):")
            content_lines.append("-" * 40)
            if conversation_context:
                content_lines.append(conversation_context)
            else:
                content_lines.append("*No conversation history available*")
            content_lines.append("")
            
            # Raw message data
            content_lines.append("RAW CONVERSATION MESSAGE DATA (internal storage):")
            content_lines.append("-" * 40)
            if context_messages:
                for i, msg in enumerate(context_messages, 1):
                    content_lines.append(f"Message {i}:")
                    content_lines.append(f"  User ID: {msg.user_id}")
                    content_lines.append(f"  Username: {msg.username}")
                    content_lines.append(f"  Content: {msg.content}")
                    content_lines.append(f"  Timestamp: {msg.timestamp} ({datetime.fromtimestamp(msg.timestamp).strftime('%Y-%m-%d %H:%M:%S')})")
                    content_lines.append(f"  Message ID: {msg.message_id}")
                    content_lines.append(f"  Is bot response: {msg.is_bot_response}")
                    content_lines.append(f"  Is self bot response: {msg.is_self_bot_response}") # Added
                    if msg.referenced_message_id:
                        content_lines.append(f"  Referenced message ID: {msg.referenced_message_id}")
                    if msg.attachment_urls:
                        content_lines.append(f"  Attachment URLs: {', '.join(msg.attachment_urls)}") # Added
                    if msg.embed_urls:
                        content_lines.append(f"  Embed URLs: {', '.join(msg.embed_urls)}") # Added
                    content_lines.append("")
            else:
                content_lines.append("*No raw message data available*")
            
            # Create file content
            file_content = "\n".join(content_lines)
            
            # Create a file-like object
            file_obj = io.StringIO(file_content)
            file_obj.seek(0)
            
            # Send as file attachment
            filename = f"llm_context_debug_{guild_id}_{channel_id}_{target_user_id}.txt"
            discord_file = discord.File(io.BytesIO(file_content.encode('utf-8')), filename=filename)
            await ctx.send(
                embed=discord.Embed(
                    title="LLM Context Debug Export",
                    description=f"Complete context export for user {target_user_id} in {target_channel.mention}",
                    color=discord.Color.green()
                ),
                file=discord_file
            )
                
        except Exception as e:
            logger.error(f"Error exporting full debug context: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while exporting debug context: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(LLMCommands(bot))
