import re
import discord
from discord.ext import commands
import asyncio
import json
import time
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List, Union, AsyncGenerator
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from utils.embed_helper import create_embed_response, create_llm_response
from utils.discord_utils import handle_streaming_text_response
from lib.rotator_library import RotatingClient
from config.llm_config_manager import load_llm_config, save_llm_config, load_api_keys_from_env, get_safety_settings, save_server_safety_settings, get_reasoning_budget, save_reasoning_budget, get_all_reasoning_budgets
from utils.chatbot.manager import chatbot_manager
from utils.file_processor import extract_text_from_attachment, extract_text_from_url

logger = get_logger()

class LLMCommands(commands.Cog):
    """Commands for interacting with Large Language Models via a rotating key client."""
    
    def __init__(self, bot):
        self.bot = bot
        self.llm_config = load_llm_config()
        self.api_keys = load_api_keys_from_env()
        # Global default models
        self.global_models = self.llm_config.get("models", {})
        self.provider_status: Dict[str, bool] = {}
        self.multimodal_models_whitelist = ["gemini", "gemma"]
        #self.multimodal_models_whitelist = ["big", "balls"]

    async def cog_load(self):
        """Initialize the LLM client and check provider status on cog load."""
        logger.info("LLMCommands cog loaded. Initializing client and checking providers.")
        await self.check_all_providers_status()

    def get_llm_config(self, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get LLM configuration. Now primarily loads from the central config manager.
        Guild-specific settings can be added here if needed in the future.
        """
        # The main config is now loaded in __init__
        # This function can be adapted if server-specific overrides are needed later.
        return self.llm_config

    def get_model_for_guild(self, guild_id: Optional[int], model_type: str) -> str:
        """Get the configured model for a specific type, falling back to globals."""
        if guild_id:
            server_config = self.llm_config.get("servers", {}).get(str(guild_id), {})
            # Check if a specific model for the type exists in the server config
            if server_config.get("models", {}).get(model_type):
                return server_config["models"][model_type]
            # Check for a server-level default model
            if server_config.get("models", {}).get("default"):
                return server_config["models"]["default"]

        # Fallback to global model for the specific type
        if self.global_models.get(model_type):
            return self.global_models[model_type]
        
        # Final fallback to the global default model
        return self.global_models.get("default")

    async def save_model_to_config(self, guild_id: int, model_name: str, model_type: str = "default"):
        """Save the selected model for a specific type to the server's config."""
        logger.debug(f"Saving model '{model_name}' for type '{model_type}' for guild {guild_id}.")
        
        servers = self.llm_config.setdefault("servers", {})
        server_config = servers.setdefault(str(guild_id), {})
        server_models = server_config.setdefault("models", self.global_models.copy())
        
        server_models[model_type] = model_name
        
        if save_llm_config(self.llm_config):
            logger.info(f"Saved model '{model_name}' for type '{model_type}' for guild {guild_id} to llm_config.json")
        else:
            logger.error(f"Failed to save model for guild {guild_id}.")
    
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
    
    def get_system_prompt_path(self, guild_id: Optional[int] = None, prompt_type: str = "chat") -> str:
        """Get the path to the system prompt file"""
        data_path = self.get_llm_data_path(guild_id)
        return os.path.join(data_path, f"system_prompt_{prompt_type}.txt")
    
    def get_context_file_path(self, guild_id: Optional[int] = None) -> str:
        """Get the path to the context file"""
        data_path = self.get_llm_data_path(guild_id)
        return os.path.join(data_path, "context.txt")
    
    def load_system_prompt(self, guild_id: Optional[int] = None, prompt_type: str = "chat") -> str:
        """Load the system prompt from file or return default"""
        prompt_path = self.get_system_prompt_path(guild_id, prompt_type)
        default_path = f"llm_data/default_system_prompt_{prompt_type}.txt"
        
        prompt = None
        
        # Try to load guild-specific prompt first
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to load guild-specific system prompt from {prompt_path}: {e}")
        
        # Fall back to default prompt if guild-specific not found
        if not prompt and os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to load default system prompt from {default_path}: {e}")
        
        # Final fallback to hardcoded prompt
        if not prompt:
            if prompt_type == "think":
                prompt = "You are a helpful AI assistant named Helper Retirement Machine 9000, here to answer questions about the bot and its functionality, as well as general questions. Think through your response step by step, showing your reasoning process clearly before providing your final answer."
            elif prompt_type == "ask":
                prompt = "You are a helpful AI assistant named Helper Retirement Machine 9000, here to answer questions about the bot and its functionality, as well as general questions. Provide clear, concise, and accurate responses."
            else: # chat
                prompt = "You are a helpful AI assistant named Helper Retirement Machine 9000, here to answer questions about the bot and its functionality, as well as general questions. Provide clear, concise, and accurate responses."
        
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
    
    def save_system_prompt(self, prompt: str, guild_id: Optional[int] = None, prompt_type: str = "chat") -> bool:
        """Save a system prompt to file"""
        try:
            self.ensure_llm_data_directory(guild_id)
            prompt_path = self.get_system_prompt_path(guild_id, prompt_type)
            
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            logger.info(f"Saved {prompt_type} system prompt to {prompt_path}")
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
    
    async def check_provider_status(self, provider: str) -> bool:
        """Check the status of a single provider by trying to list its models."""
        try:
            async with RotatingClient(api_keys=self.api_keys) as client:
                models = await client.get_available_models(provider)
                is_online = bool(models)
                self.provider_status[provider] = is_online
                if is_online:
                    logger.info(f"Provider '{provider}' is online. Found {len(models)} models.")
                else:
                    logger.warning(f"Provider '{provider}' is offline or has no models.")
                return is_online
        except Exception as e:
            logger.error(f"Failed to check status for provider '{provider}': {e}")
            self.provider_status[provider] = False
            return False

    async def check_all_providers_status(self):
        """Check the status of all configured providers."""
        logger.info("Checking status of all configured LLM providers...")
        providers = list(self.api_keys.keys())
        # Add 'local' provider if base_url is configured
        if self.llm_config.get("base_url"):
            providers.append("local")
        
        status_checks = [self.check_provider_status(provider) for provider in providers]
        await asyncio.gather(*status_checks)
    
    async def make_llm_request(
        self,
        prompt: Optional[str] = None,
        model_type: str = "default",
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        history: Optional[List[Dict[str, any]]] = None,  # New history parameter
        model: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], Tuple[AsyncGenerator, str]]:
        """
        Make a request to the LLM API using the RotatingClient and return the response
        with performance metrics. If stream is True, returns an AsyncGenerator.
        """
        start_time = time.time()
        
        # Determine the model to use
        target_model = model or self.get_model_for_guild(guild_id, model_type)
        if not target_model:
            raise ValueError("No model specified and no default model configured.")

        # Prepare prompts
        system_prompt, context = self._prepare_prompts(system_prompt, context, model_type, guild_id)
        
        is_multimodal = any(keyword in target_model for keyword in self.multimodal_models_whitelist)
        
        # Build the messages list using the new structured history
        messages = self._build_messages_list(
            system_prompt=system_prompt,
            static_context=context,
            history=history,
            prompt=prompt,
            image_urls=image_urls,
            is_multimodal=is_multimodal
        )
        
        # Prepare kwargs for the rotating client
        request_kwargs = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": self.llm_config.get("timeout", 120),
            "safety_settings": get_safety_settings(guild_id, channel_id),
            "stream": stream
        }

        if stream:
            request_kwargs["stream_options"] = {"include_usage": True}

        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens

        # Apply reasoning budget
        reasoning_budget_level, custom_reasoning_budget = get_reasoning_budget(target_model, model_type, guild_id)
        if reasoning_budget_level is not None:
            #logger.info(f"Applying reasoning budget for model '{target_model}' in mode '{model_type}' with level '{reasoning_budget_level}'.")
            if reasoning_budget_level == -1 or reasoning_budget_level == "auto":
                request_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": -1
                }
            else:
                reasoning_map = {0: "disable", 1: "low", 2: "medium", 3: "high"}
                level_str = reasoning_map.get(reasoning_budget_level)
                if not level_str:
                    level_map_str = {"none": "disable", "low": "low", "medium": "medium", "high": "high"}
                    level_str = level_map_str.get(reasoning_budget_level)

                if level_str:
                    request_kwargs["reasoning_effort"] = level_str
        
        if custom_reasoning_budget:
            request_kwargs["custom_reasoning_budget"] = True

        # Handle local provider by setting api_base
        if target_model.startswith("local/"):
            request_kwargs["api_base"] = self.llm_config.get("base_url")
            # The rotator client expects the format `provider/model_name`, but for local
            # models litellm might just need the model name itself.
            # Let's adjust this based on how the rotator/litellm handles it.
            # For now, we assume litellm needs the full `local/model_name` string.

        self._save_debug_request(request_kwargs, "RotatingClient", target_model.split('/')[0])

        try:
            async with RotatingClient(api_keys=self.api_keys, max_retries=self.llm_config.get("max_retries", 2)) as client:
                if stream:
                    response_generator = client.acompletion(**request_kwargs)
                    return response_generator, target_model
                
                response = await client.acompletion(**request_kwargs)
            
            # This part only runs for non-streaming responses
            self._save_debug_response(response, target_model.split('/')[0])
            
            # The rotator client returns the litellm response object directly for non-streaming
            content = response.choices[0].message.content
            usage = response.usage
            
            performance_metrics = self._calculate_performance_metrics(start_time, content, usage)
            
            if performance_metrics.get('has_token_data', False):
                logger.debug(f"LLM request to '{target_model}' completed in {performance_metrics['elapsed_time']:.2f}s, "
                           f"{performance_metrics['tokens_per_sec']:.1f} tokens/s "
                           f"({performance_metrics['completion_tokens']} tokens)")
            else:
                logger.debug(f"LLM request to '{target_model}' completed in {performance_metrics['elapsed_time']:.2f}s, "
                           f"{performance_metrics['chars_per_sec']:.1f} chars/s")

            return content, performance_metrics

        except Exception as e:
            logger.error(f"Error making LLM request via RotatingClient to model {target_model}: {e}", exc_info=True)
            raise  # Re-raise the exception to be handled by the command

    def _prepare_prompts(self, system_prompt: Optional[str], context: Optional[str],
                        model_type: str, guild_id: Optional[int]) -> Tuple[str, Optional[str]]:
        """Prepare system prompt and context for both providers"""
        # Prepare the system prompt
        if system_prompt is None:
            system_prompt = self.load_system_prompt(guild_id, prompt_type=model_type)

        # Load context if available and not provided
        # (This is for static context from file, dynamic chatbot context is passed directly)
        if context is None:
            context = self.load_context(guild_id)
            
        return system_prompt, context

    def _save_debug_request(self, payload: dict, endpoint: str, provider: str):
        """Save debug request payload to file for debugging purposes"""
        try:
            debug_dir = os.path.join("llm_data", "debug_prompts")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"llm_request_{provider}.json"
            debug_filepath = os.path.join(debug_dir, debug_filename)
            
            with open(debug_filepath, 'w', encoding='utf-8') as f:
                f.write(f"// filepath: {debug_filepath}\n")
                f.write(f"// Provider: {provider}\n")
                f.write(f"// Endpoint: {endpoint}\n")
                f.write(f"// Timestamp: {timestamp}\n")
                f.write("// REQUEST PAYLOAD:\n")
                # Use json.dumps from standard library
                f.write(json.dumps(payload, indent=2, ensure_ascii=False))
            logger.debug(f"Saved debug request payload to {debug_filepath}")
        except Exception as e:
            logger.warning(f"Failed to save debug request payload: {e}")

    def _save_debug_response(self, response: Any, provider: str):
        """Save debug response to file for debugging purposes"""
        try:
            debug_dir = os.path.join("llm_data", "debug_prompts")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"llm_response_{provider}.json"
            debug_filepath = os.path.join(debug_dir, debug_filename)
            
            response_data = {}
            if hasattr(response, 'dict'):
                response_data = response.dict()
            else:
                # For non-pydantic objects, just convert to string
                response_data = str(response)

            with open(debug_filepath, 'w', encoding='utf-8') as f:
                f.write(f"// filepath: {debug_filepath}\n")
                f.write(f"// Provider: {provider}\n")
                f.write(f"// Timestamp: {timestamp}\n")
                f.write("// RESPONSE:\n")
                f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
            logger.debug(f"Saved debug response to {debug_filepath}")
        except Exception as e:
            logger.warning(f"Failed to save debug response: {e}")

    def _calculate_performance_metrics(self, start_time: float, content: str,
                                     usage: Optional[Any] = None) -> Dict[str, Any]:
        """Calculate performance metrics for LLM response."""
        end_time = time.time()
        elapsed_time = end_time - start_time
        char_count = len(content) if content else 0
        chars_per_sec = char_count / elapsed_time if elapsed_time > 0 else 0
        
        if isinstance(usage, dict):
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
        else:
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
            completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
            total_tokens = getattr(usage, 'total_tokens', 0) if usage else 0
        
        tokens_per_sec = 0
        if completion_tokens > 0 and elapsed_time > 0:
            tokens_per_sec = completion_tokens / elapsed_time
        elif char_count > 0 and elapsed_time > 0:
            tokens_per_sec = (char_count / 4) / elapsed_time  # Rough estimation

        return {
            'elapsed_time': elapsed_time,
            'char_count': char_count,
            'chars_per_sec': chars_per_sec,
            'tokens_per_sec': tokens_per_sec,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'has_token_data': total_tokens > 0
        }

    def _build_messages_list(
        self,
        system_prompt: str,
        static_context: Optional[str],
        history: Optional[List[Dict[str, any]]],
        prompt: Optional[str],
        image_urls: Optional[List[str]] = None,
        is_multimodal: bool = False
    ) -> List[Dict[str, Any]]:
        """Builds the final list of messages for the LLM API."""
        messages = []

        # 1. Add the main system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 2. Add the static context (channel info, user info, pins) as another system message
        if static_context:
            messages.append({"role": "system", "content": static_context})

        # 3. Add the structured conversation history
        if history:
            # The history is already formatted with roles, so we just extend the list.
            # We need to ensure the content is correctly formatted for multimodal.
            for msg in history:
                # For now, we assume the content is a string.
                # If multimodal content needs to be passed as a list of parts,
                # this is where that logic would go.
                messages.append(msg)

        # 4. Add the current user's prompt
        if prompt:
            content_parts = []
            # The 'prompt' can be a string (from /ask) or a list of parts (from the chatbot formatter)
            if isinstance(prompt, list):
                content_parts.extend(prompt)
            elif isinstance(prompt, str):
                content_parts.append({"type": "text", "text": prompt})

            # Add any extra image_urls that weren't part of the initial prompt object
            if image_urls and is_multimodal:
                logger.info(f"Adding {len(image_urls)} image URLs to user message for multimodal model")
                for url in image_urls:
                    # Prevent adding duplicate images if they were already processed into the prompt
                    if not any(part.get("type") == "image_url" and part.get("image_url", {}).get("url") == url for part in content_parts):
                        content_parts.append({"type": "image_url", "image_url": {"url": url}})
            
            if not content_parts:
                return messages # Nothing to add

            # If there's only one text part, send it as a simple string for compatibility.
            # Otherwise, send the list of parts.
            final_prompt_content = content_parts[0]['text'] if len(content_parts) == 1 and content_parts[0]['type'] == 'text' else content_parts
            messages.append({"role": "user", "content": final_prompt_content})
            
        return messages

    def _add_parsed_message(self, messages: List[Dict[str, str]], current_role: str,
                          current_content: List[str]):
        """Add a parsed message to the messages list, mapping roles to 'user'/'assistant'."""
        # This function is now largely superseded by the logic in _parse_conversation_history_block,
        # but we'll keep it for now in case it's used elsewhere.
        # The new implementation in _parse_conversation_history_block is more robust for multimodal content.
        
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
    
    async def send_llm_response(self, ctx, response: str, question: str, model_type: str = "default", performance_metrics: Optional[Dict[str, Any]] = None):
        """Helper function to send LLM response using the new unified embed system"""
        thinking = model_type == "think"
        logger.debug(f"Sending LLM response for model_type={model_type}")
        guild_id = ctx.guild.id if ctx.guild else None
        model_name = self.get_model_for_guild(guild_id, model_type) or "Unknown Model"
        
        # Choose color and title based on thinking mode
        color = discord.Color.purple() if thinking else discord.Color.blue()
        title = "LLM Thinking Response" if thinking else "LLM Response"
        
        logger.info(f"Sending LLM response to {ctx.author} in {ctx.guild.name if ctx.guild else 'DM'}")
        
        # Extract thinking content if present
        cleaned_response, thinking_content, _ = self.strip_thinking_tokens(response)
        
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

    async def handle_streaming_embed_response(self, ctx, stream_generator: AsyncGenerator, model_name: str, question: str, command_type: str, show_thinking: bool):
        """
        Process a streaming LLM response and update one or more Discord embeds in real-time.
        """
        messages_to_edit = []
        answer_buffer, reasoning_buffer = "", ""
        last_update_time, start_time = time.time(), time.time()
        stream_chunks, last_known_summaries = [], []
        usage_data, thinking_completed = None, False

        try:
            async for chunk in stream_generator:
                try:
                    chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else str(chunk)
                    if chunk_str.startswith('data: '): chunk_str = chunk_str[6:]
                    if not chunk_str.strip() or chunk_str.strip() == '[DONE]': continue
                    
                    data = json.loads(chunk_str)
                    stream_chunks.append(data)

                    if "error" in data:
                        error_embed = discord.Embed(title="LLM Error", description=data.get("error", "Unknown error"), color=discord.Color.red())
                        if messages_to_edit: await messages_to_edit[0].edit(embed=error_embed)
                        else: await ctx.send(embed=error_embed)
                        return

                    if "usage" in data: usage_data = data["usage"]
                    delta = data.get('choices', [{}])[0].get('delta', {})
                    if delta.get('content'): answer_buffer += delta['content']
                    if delta.get('reasoning_content'): reasoning_buffer += delta['reasoning_content']

                except (json.JSONDecodeError, IndexError) as e:
                    logger.warning(f"Skipping invalid stream chunk: {chunk_str[:100]} | Error: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing stream chunk: {e}", exc_info=True)
                    error_embed = discord.Embed(title="Streaming Error", description=f"An unexpected error occurred: {e}", color=discord.Color.red())
                    if messages_to_edit: await messages_to_edit[0].edit(embed=error_embed)
                    else: await ctx.send(embed=error_embed)
                    return

                current_time = time.time()
                if current_time - last_update_time > 1.2:
                    last_update_time = current_time
                    full_response_text = f"<thinking>{reasoning_buffer}</thinking>{answer_buffer}"
                    cleaned_response, thinking_content, is_thinking_only, current_summaries = self.strip_thinking_tokens(full_response_text, model_name)

                    # Universal summary display
                    if is_thinking_only and current_summaries and current_summaries != last_known_summaries:
                        last_known_summaries = current_summaries
                        summary_text = f"**Thinking...** ({current_summaries[-1]})"
                        summary_embed = discord.Embed(description=summary_text, color=discord.Color.purple())
                        try:
                            if not messages_to_edit:
                                messages_to_edit.append(await ctx.send(embed=summary_embed))
                            else:
                                await messages_to_edit[0].edit(embed=summary_embed)
                        except discord.errors.HTTPException as e:
                            logger.warning(f"Failed to update thinking summary: {e}")
                        continue

                    if not is_thinking_only: thinking_completed = True
                    if not thinking_completed: continue

                    try:
                        messages_to_edit = await create_llm_response(
                            ctx, cleaned_response, question, model_name, command_type,
                            thinking_content, show_thinking, None, messages_to_edit
                        )
                    except discord.errors.HTTPException as e:
                        if e.status == 429:
                            logger.warning("Rate limited on streaming update, slowing down.")
                            last_update_time += 2.0
                        else:
                            logger.error(f"Failed to edit message during stream: {e}")
                            return
        finally:
            if 'stream_generator' in locals() and hasattr(stream_generator, 'aclose'):
                await stream_generator.aclose()

            self._save_debug_stream_response_raw(stream_chunks, model_name.split('/')[0])
            assembled_response = self._save_debug_stream_response_assembled(stream_chunks, model_name.split('/')[0])
            
            if not assembled_response:
                logger.error("Failed to assemble final response from stream chunks.")
                return

            final_message = assembled_response.get("choices", [{}])[0].get("message", {})
            final_content = final_message.get("content", "")
            final_reasoning = final_message.get("reasoning_content", "")
            
            # Reconstruct the full text to correctly strip thinking content for the final update
            full_final_text = f"<thinking>{final_reasoning}</thinking>{final_content}"

            performance_metrics = self._calculate_performance_metrics(start_time, final_content, usage_data)
            cleaned_response, thinking_content, _, _ = self.strip_thinking_tokens(full_final_text, model_name)

            try:
                await create_llm_response(
                    ctx, cleaned_response, question, model_name, command_type,
                    thinking_content, show_thinking, performance_metrics, messages_to_edit
                )
            except discord.errors.NotFound:
                logger.warning("Message to edit for final update was deleted.")
            except Exception as e:
                logger.error(f"Failed to send final update for streaming response: {e}", exc_info=True)
    
    def strip_thinking_tokens(self, response: str, model_name: str) -> Tuple[str, str, bool, List[str]]:
        """
        Strip thinking tokens from the response using a state machine to handle unclosed tags.
        
        Returns:
            - cleaned_response (str): The response with all thinking blocks removed.
            - thinking_content (str): The combined content of all thinking blocks.
            - is_thinking_only (bool): True if the response contains only thinking content (or is empty).
            - summaries (List[str]): A list of extracted summary titles (only for supported models).
        """
        thinking_content_parts = []
        answer_parts = []
        
        in_thinking_block = False
        last_pos = 0
        
        # This regex finds any of the opening or closing thinking tags
        tag_regex = re.compile(r'<(/?)(?:think|thinking|thought)>|(\[/?thinking\])|(\*/?thinking\*)', re.IGNORECASE)

        for match in tag_regex.finditer(response):
            start, end = match.span()
            
            # Add the text between the last tag and this one
            text_slice = response[last_pos:start]
            if text_slice:
                if in_thinking_block:
                    thinking_content_parts.append(text_slice)
                else:
                    answer_parts.append(text_slice)
            
            # Determine if it's an opening or closing tag
            tag_content = match.group(0)
            is_closing = tag_content.startswith(('</', '[/', '*/'))
            
            if is_closing:
                in_thinking_block = False
            else:
                in_thinking_block = True
            
            last_pos = end
            
        # Add any remaining text after the last tag
        remaining_text = response[last_pos:]
        if remaining_text:
            if in_thinking_block:
                thinking_content_parts.append(remaining_text)
            else:
                answer_parts.append(remaining_text)

        cleaned_response = "".join(answer_parts).strip()
        combined_thinking = "".join(thinking_content_parts).strip()
        
        # Stage 2: Extract summaries from the isolated thinking content
        summaries = []
        if "gemini-2.5" in model_name and combined_thinking:
            # This regex finds markdown bold sections (summaries) that are on their own line
            summary_regex = re.compile(r'^\s*\*\*(.*?)\*\*\s*$', re.MULTILINE)
            for summary_match in summary_regex.finditer(combined_thinking):
                summaries.append(summary_match.group(1).strip())
        
        # Determine if the response is only thinking content
        # This is true if there is thinking content but the cleaned response is empty.
        is_thinking_only = bool(combined_thinking) and not bool(cleaned_response)

        if combined_thinking:
            logger.debug(f"Extracted {len(combined_thinking)} chars of thinking. Summaries: {summaries}. Is only thinking: {is_thinking_only}")
            
        return cleaned_response, combined_thinking, is_thinking_only, summaries
    
    def _save_debug_stream_response_raw(self, response_chunks: List[Dict[str, Any]], provider: str):
        """Save the raw streaming response chunks to a file for debugging."""
        try:
            debug_dir = os.path.join("llm_data", "debug_prompts")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"llm_stream_response_raw_{provider}.json"
            debug_filepath = os.path.join(debug_dir, debug_filename)
            
            with open(debug_filepath, 'w', encoding='utf-8') as f:
                f.write(f"// filepath: {debug_filepath}\n")
                f.write(f"// Provider: {provider}\n")
                f.write(f"// Timestamp: {timestamp}\n")
                f.write("// RAW STREAM RESPONSE CHUNKS:\n")
                json.dump(response_chunks, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved raw debug stream response to {debug_filepath}")
        except Exception as e:
            logger.warning(f"Failed to save raw debug stream response: {e}", exc_info=True)

    def _save_debug_stream_response_assembled(self, response_chunks: List[Dict[str, Any]], provider: str) -> Optional[Dict[str, Any]]:
        """
        Assembles the full streaming response, saves it for debugging, and returns it.
        """
        if not response_chunks:
            return None

        try:
            # Initialize the final response object with potential top-level fields
            final_response = {
                "id": None, "model": None, "created": None,
                "object": "chat.completion", "choices": [], "usage": None
            }
            # ... (rest of the assembly logic is the same)
            for chunk in response_chunks:
                for key, value in chunk.items():
                    if key not in ['choices', 'usage'] and key not in final_response:
                        final_response[key] = value

            for chunk in response_chunks:
                if not final_response.get("id") and chunk.get("id"): final_response["id"] = chunk.get("id")
                if not final_response.get("model") and chunk.get("model"): final_response["model"] = chunk.get("model")
                if not final_response.get("created") and chunk.get("created"): final_response["created"] = chunk.get("created")
                if all(final_response.get(k) for k in ["id", "model", "created"]): break

            full_content, full_reasoning_content, final_finish_reason = "", "", None
            
            for chunk in response_chunks:
                if choice := chunk.get("choices", [{}])[0]:
                    if delta := choice.get("delta", {}):
                        if content := delta.get("content"): full_content += content
                        if reasoning := delta.get("reasoning_content"): full_reasoning_content += reasoning
                    if reason := choice.get("finish_reason"): final_finish_reason = reason
                if usage := chunk.get("usage"): final_response["usage"] = usage

            final_message = {"role": "assistant", "content": full_content}
            if full_reasoning_content:
                final_message["reasoning_content"] = full_reasoning_content

            final_response["choices"].append({
                "finish_reason": final_finish_reason, "index": 0, "message": final_message
            })

            # Save the assembled response for debugging
            debug_dir = os.path.join("llm_data", "debug_prompts")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"llm_stream_response_assembled_{provider}.json"
            debug_filepath = os.path.join(debug_dir, debug_filename)
            
            with open(debug_filepath, 'w', encoding='utf-8') as f:
                json.dump(final_response, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved assembled debug stream response to {debug_filepath}")
            return final_response

        except Exception as e:
            logger.warning(f"Failed to save or assemble debug stream response: {e}", exc_info=True)
            return None

    async def _process_multimodal_input(self, message: discord.Message, question: str) -> Tuple[str, List[str]]:
        """Helper to process attachments and URLs from a message for multimodal input."""
        image_urls = []
        extracted_text = []

        # Process attachments
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image_urls.append(attachment.url)
            else:
                text = await extract_text_from_attachment(attachment)
                if text:
                    extracted_text.append(text)

        # Process URLs in the question string
        url_pattern = re.compile(r'https?://\S+')
        found_urls = url_pattern.findall(question)
        for url in found_urls:
            # Check if the URL is an image
            if any(url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']):
                image_urls.append(url)
                question = question.replace(url, '').strip()
            # Check if the URL is a text-based file
            elif any(url.lower().endswith(ext) for ext in ['.pdf', '.txt', '.log', '.ini']):
                text = await extract_text_from_url(url)
                if text:
                    extracted_text.append(text)
                question = question.replace(url, '').strip()

        if extracted_text:
            question = f"{' '.join(extracted_text)}\n\n{question}"
        
        return question, image_urls

    @commands.command(name='ask', help='Ask the LLM a question')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def ask_llm(self, ctx, *, question: str):
        """Ask the LLM a question without showing thinking process."""
        logger.info(f"User {ctx.author} asking LLM: {question[:100]}")

        if not self.api_keys and not self.llm_config.get("base_url"):
            await create_embed_response(ctx, "No API keys or local server configured.", title="LLM Not Configured", color=discord.Color.red())
            return

        async with ctx.typing():
            try:
                question, image_urls = await self._process_multimodal_input(ctx.message, question)
                guild_id = ctx.guild.id if ctx.guild else None
                
                channel_context = await chatbot_manager.formatter.format_channel_context_for_llm_from_object(ctx.channel)
                user_context = await chatbot_manager.formatter.format_user_context_for_llm(ctx.author)
                full_context = f"{channel_context}\n{user_context}"
                
                # Use the unified streaming response handler for a consistent look
                stream_generator, model_name = await self.make_llm_request(
                    prompt=f"{ctx.author.display_name}: {question}",
                    model_type="ask",
                    guild_id=guild_id,
                    channel_id=ctx.channel.id,
                    image_urls=image_urls,
                    context=full_context,
                    stream=True
                )
                await self.handle_streaming_embed_response(ctx, stream_generator, model_name, question, command_type="ask", show_thinking=False)

            except Exception as e:
                logger.error(f"Error in !ask command: {e}", exc_info=True)
                await create_embed_response(ctx, f"An error occurred: {e}", title="LLM Error", color=discord.Color.red())

    @commands.command(name='think', help='Ask the LLM a question and show its thinking process.')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def think_llm(self, ctx, display_thinking: Optional[bool] = False, *, question: str):
        """Ask the LLM a question, with an option to show the thinking process."""
        logger.info(f"User {ctx.author} using think command: {question[:100]}")

        if not self.api_keys and not self.llm_config.get("base_url"):
            await create_embed_response(ctx, "No API keys or local server configured.", title="LLM Not Configured", color=discord.Color.red())
            return

        async with ctx.typing():
            try:
                question, image_urls = await self._process_multimodal_input(ctx.message, question)
                guild_id = ctx.guild.id if ctx.guild else None

                channel_context = await chatbot_manager.formatter.format_channel_context_for_llm_from_object(ctx.channel)
                user_context = await chatbot_manager.formatter.format_user_context_for_llm(ctx.author)
                full_context = f"{channel_context}\n{user_context}"

                # Use the unified streaming response handler
                stream_generator, model_name = await self.make_llm_request(
                    prompt=f"{ctx.author.display_name}: {question}",
                    model_type="think",
                    guild_id=guild_id,
                    channel_id=ctx.channel.id,
                    image_urls=image_urls,
                    context=full_context,
                    stream=True
                )
                await self.handle_streaming_embed_response(ctx, stream_generator, model_name, question, command_type="think", show_thinking=display_thinking)

            except Exception as e:
                logger.error(f"Error in !think command: {e}", exc_info=True)
                await create_embed_response(ctx, f"An error occurred: {e}", title="LLM Error", color=discord.Color.red())
    
    @commands.command(name='llm_status', help='Check the status of all configured LLM providers.')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def llm_status(self, ctx):
        """Checks the status of all configured LLM providers."""
        logger.info(f"User {ctx.author} checking LLM provider status.")
        await ctx.typing()
        
        await self.check_all_providers_status()
        
        embed = discord.Embed(title="LLM Provider Status", color=discord.Color.blue())
        
        if not self.provider_status:
            embed.description = "No providers configured or checked."
            await ctx.send(embed=embed)
            return

        for provider, is_online in self.provider_status.items():
            status_emoji = "✅" if is_online else "❌"
            status_text = "Online" if is_online else "Offline"
            embed.add_field(name=f"{status_emoji} {provider.title()}", value=status_text, inline=True)
        
        guild_id = ctx.guild.id if ctx.guild else None
        models_info = []
        for model_type in ["default", "chat", "ask", "think"]:
            model_name = self.get_model_for_guild(guild_id, model_type)
            models_info.append(f"**{model_type.title()}**: `{model_name}`")
        
        embed.add_field(name="Configured Models for this Server", value="\n".join(models_info), inline=False)

        await ctx.send(embed=embed)
    
    def load_model_filters(self) -> Dict[str, Any]:
        """Load model filters from data/model_filters.json"""
        filters_path = "data/model_filters.json"
        if os.path.exists(filters_path):
            try:
                with open(filters_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load model filters from {filters_path}: {e}")
        return {}

    @commands.command(name='llm_models', help='List available models from providers with filtering.')
    @has_command_permission('manage_messages')
    @command_category("AI Assistant")
    async def list_models(self, ctx, *args):
        """
        List available models with advanced filtering.
        Usage: !llm_models [full] [provider] [filter] [file]
        - No args: List whitelisted models from all providers.
        - [full]: List all models from provider(s), ignoring the whitelist.
        - [provider]: List models for a specific provider.
        - [filter]: Apply a text filter to the model list.
        - [file]: Outputs the list to a file.
        """
        # Parse arguments
        provider_filter = None
        text_filter = None
        output_to_file = False
        show_all_models = False

        possible_args = list(args)

        # Extract keywords 'file' and 'full'
        if "file" in [arg.lower() for arg in possible_args]:
            output_to_file = True
            possible_args = [arg for arg in possible_args if arg.lower() != "file"]
        
        if "full" in [arg.lower() for arg in possible_args]:
            show_all_models = True
            possible_args = [arg for arg in possible_args if arg.lower() != "full"]

        # Determine provider and text filter from the rest of the arguments
        all_providers = list(self.api_keys.keys())
        if self.llm_config.get("base_url"):
            all_providers.append("local")
        
        remaining_args = []
        for arg in possible_args:
            # Check if the argument is a known provider
            if arg.lower() in [p.lower() for p in all_providers]:
                provider_filter = arg
            else:
                remaining_args.append(arg)
        
        # Whatever is left is the text filter
        if remaining_args:
            text_filter = " ".join(remaining_args)

        logger.info(f"User {ctx.author} requesting model list. Full: {show_all_models}, Provider: {provider_filter}, Filter: {text_filter}, File: {output_to_file}")
        await ctx.typing()

        try:
            async with RotatingClient(api_keys=self.api_keys) as client:
                all_models_from_provider = await client.get_all_available_models(grouped=True)
                if self.llm_config.get("base_url"):
                    try:
                        local_models = await client.get_available_models("local")
                        if local_models:
                            all_models_from_provider["local"] = local_models
                    except Exception as e:
                        logger.warning(f"Could not fetch local models: {e}")

            if not all_models_from_provider:
                await create_embed_response(ctx, "No models found for any provider.", title="No Models Found", color=discord.Color.orange())
                return

            model_whitelist = self.load_model_filters()
            
            sections = []
            total_model_count = 0
            unavailable_whitelisted_models = []

            providers_to_show = sorted(all_models_from_provider.keys())
            if provider_filter:
                providers_to_show = [p for p in providers_to_show if provider_filter.lower() == p.lower()]
                if not providers_to_show:
                    await create_embed_response(ctx, f"Provider '{provider_filter}' not found or has no models.", title="Provider Not Found", color=discord.Color.orange())
                    return

            for provider in providers_to_show:
                provider_models = all_models_from_provider.get(provider, [])
                
                # Determine the base list of models to show
                if show_all_models:
                    models_to_filter = provider_models
                else:
                    whitelisted_provider_models = model_whitelist.get(provider, {}).get("models", [])
                    # Find available models that are on the whitelist
                    models_to_filter = [m for m in provider_models if m in whitelisted_provider_models]
                    # Find whitelisted models that are NOT available
                    unavailable = [m for m in whitelisted_provider_models if m not in provider_models]
                    if unavailable:
                        unavailable_whitelisted_models.extend(unavailable)

                # Apply user's text filter if any
                if text_filter:
                    final_models_to_display = sorted([m for m in models_to_filter if text_filter.lower() in m.lower()])
                else:
                    final_models_to_display = sorted(models_to_filter)

                if final_models_to_display:
                    model_lines = []
                    guild_id = ctx.guild.id if ctx.guild else None
                    for model in final_models_to_display:
                        indicators = []
                        for model_type in ["default", "chat", "ask", "think"]:
                            if model == self.get_model_for_guild(guild_id, model_type):
                                indicators.append(model_type.title())
                        
                        indicator_str = f"🟢 ({', '.join(indicators)})" if indicators else "⚪️"
                        model_lines.append(f"{indicator_str} `{model}`")
                    
                    sections.append({
                        "name": f"{provider.upper()} ({len(final_models_to_display)} models)",
                        "content": "\n".join(model_lines),
                        "inline": False
                    })
                    total_model_count += len(final_models_to_display)

            if not sections:
                await create_embed_response(ctx, "No models match the specified criteria.", title="No Models Found", color=discord.Color.orange())
                return

            # Prepare for output
            title = "Available LLM Models"
            
            guild_id = ctx.guild.id if ctx.guild else None
            models_info = []
            for model_type in ["default", "chat", "ask", "think"]:
                model_name = self.get_model_for_guild(guild_id, model_type)
                models_info.append(f"**{model_type.title()}**: `{model_name}`")

            description = f"Found **{total_model_count}** models matching your criteria.\n\n**Models for this Server:**\n" + "\n".join(models_info)
            
            warning_footer = ""
            if unavailable_whitelisted_models and not show_all_models:
                warning_footer = f"\n\n⚠️ The following whitelisted models are currently unavailable: {', '.join(f'`{m}`' for m in unavailable_whitelisted_models)}"

            if output_to_file:
                file_content = f"{title}\n{description}\n\n"
                for section in sections:
                    file_content += f"--- {section['name']} ---\n"
                    clean_content = section['content'].replace('`', '').replace('🟢', '->').replace('⚪️', '  ')
                    file_content += f"{clean_content}\n\n"
                
                file_content += "Use `!llm_select [type] <model_name>` to choose a model (e.g., `!llm_select think <model>`)."
                if warning_footer:
                    file_content += warning_footer.replace('`', '')

                with open("model_list.txt", "w", encoding="utf-8") as f:
                    f.write(file_content)
                await ctx.send("Here is the list of models as a file:", file=discord.File("model_list.txt"))
                os.remove("model_list.txt")
            else:
                await create_embed_response(
                    ctx,
                    description=description,
                    sections=sections,
                    title=title,
                    footer_text=f"Use `!llm_select [type] <model_name>` to choose a model.{warning_footer}",
                    color=discord.Color.blue()
                )

        except Exception as e:
            logger.error(f"Failed to retrieve models: {e}", exc_info=True)
            await create_embed_response(ctx, f"An error occurred: {e}", title="Error", color=discord.Color.red())
    
    @commands.command(name='llm_select', help='Select a preferred model to use for LLM requests. Usage: `!llm_select [manual] [type] <model_name>`')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def select_model(self, ctx, *args):
        """
        Select a preferred model for a specific type (chat, ask, think) or default for this server.
        Usage: !llm_select [manual] [type] <model_name>
               !llm_select [manual] <model_name> (sets default for this server)
        """
        if not ctx.guild:
            await create_embed_response(ctx, "This command can only be used in a server.", title="Error", color=discord.Color.red())
            return

        is_manual = False
        model_type = "default"
        
        arg_list = list(args)

        if arg_list and arg_list[0].lower() == "manual":
            is_manual = True
            arg_list.pop(0)

        valid_types = ["default", "chat", "ask", "think"]
        if arg_list and arg_list[0].lower() in valid_types:
            model_type = arg_list.pop(0).lower()
        
        model_name = " ".join(arg_list)

        logger.info(f"User {ctx.author} in guild {ctx.guild.id} attempting to select model. Type: {model_type}, Name: {model_name}, Manual: {is_manual}")
        await ctx.typing()

        if not model_name:
            await create_embed_response(ctx, "You must provide a model name.", title="Missing Model Name", color=discord.Color.orange())
            return

        try:
            # Owner check for manual mode
            if is_manual:
                app_info = await self.bot.application_info()
                if ctx.author.id != app_info.owner.id:
                    await create_embed_response(ctx, "The `manual` flag is only available to the bot owner.", title="Permission Denied", color=discord.Color.red())
                    return

            if not is_manual:
                # Fetch available models and filter by whitelist
                async with RotatingClient(api_keys=self.api_keys) as client:
                    all_models_from_provider = await client.get_all_available_models(grouped=True)
                
                model_whitelist = self.load_model_filters()
                
                # Flatten the list of all whitelisted models
                all_whitelisted_models = [model for provider_rules in model_whitelist.values() for model in provider_rules.get("models", [])]
                
                # Flatten the list of all available models from the provider
                all_available_models_flat = [model for models in all_models_from_provider.values() for model in models]

                # The list of models users can select from is the intersection of what's available and what's whitelisted
                selectable_models = [m for m in all_available_models_flat if m in all_whitelisted_models]

                if model_name not in selectable_models:
                    # Try to find a partial match within the selectable models
                    partial_matches = [m for m in selectable_models if model_name.lower() in m.lower()]
                    if len(partial_matches) == 1:
                        model_name = partial_matches[0]
                    else:
                        suggestions = "\n".join(f"- `{m}`" for m in partial_matches[:5])
                        msg = f"Model `{model_name}` is not on the approved list or is currently unavailable."
                        if suggestions:
                            msg += f"\n\nDid you mean one of these?\n{suggestions}"
                        await create_embed_response(ctx, msg, title="Model Not Selectable", color=discord.Color.orange())
                        return

            # If we're here, the model is valid (or manual mode is on for the owner)
            await self.save_model_to_config(ctx.guild.id, model_name, model_type)
            
            response_msg = f"Set **{model_type}** model for this server to:\n`{model_name}`"
            if is_manual:
                response_msg += "\n*(Manual selection by owner: Model was set regardless of availability or whitelist.)*"
            
            await create_embed_response(ctx, response_msg, title="Model Selected", color=discord.Color.green())

        except Exception as e:
            logger.error(f"Failed to select model: {e}", exc_info=True)
            await create_embed_response(ctx, f"An error occurred: {e}", title="Error", color=discord.Color.red())
    
    # Note: The llm_provider and llm_set_api_key commands are now obsolete,
    # as the provider is determined by the model name and keys are loaded from .env.
    # They are removed to avoid confusion.
    
    @commands.command(name='chatbot_enable')
    @has_command_permission("chatbot_enable")
    @command_category("AI Assistant")
    async def chatbot_enable(self, ctx):
        """Enable chatbot mode for this channel."""
        try:
            from utils.chatbot.manager import chatbot_manager
            
            guild_id = ctx.guild.id
            if not guild_id:
                await create_embed_response(ctx, "Chatbot mode can only be enabled in server channels.", title="Error", color=discord.Color.red())
                return

            # Check if any LLM provider is online
            await self.check_all_providers_status()
            if not any(self.provider_status.values()):
                await create_embed_response(ctx, "No LLM providers are online. Cannot enable chatbot mode.", title="LLM Service Unavailable", color=discord.Color.red())
                return

            success = await chatbot_manager.enable_chatbot(guild_id, ctx.channel.id, ctx.guild, ctx.channel)
            if success:
                channel_config = chatbot_manager.get_channel_config(guild_id, ctx.channel.id)
                await create_embed_response(
                    ctx,
                    f"✅ Chatbot mode enabled for {ctx.channel.mention}\n\n"
                    f"**Configuration:**\n"
                    f"• Responds to mentions: {'Yes' if channel_config.auto_respond_to_mentions else 'No'}\n"
                    f"• Responds to replies: {'Yes' if channel_config.auto_respond_to_replies else 'No'}\n"
                    f"• Context window: {channel_config.context_window_hours} hours\n"
                    f"• Max context messages: {channel_config.max_context_messages}\n"
                    f"• Max user context messages: {channel_config.max_user_context_messages}",
                    title="Chatbot Mode Enabled",
                    color=discord.Color.green()
                )
            else:
                await create_embed_response(ctx, "Failed to enable chatbot mode.", title="Error", color=discord.Color.red())
        except Exception as e:
            logger.error(f"Error enabling chatbot mode: {e}", exc_info=True)
            await create_embed_response(ctx, f"An error occurred: {str(e)}", title="Error", color=discord.Color.red())
    
    @commands.command(name='chatbot_disable')
    @has_command_permission("chatbot_disable")
    @command_category("AI Assistant")
    async def chatbot_disable(self, ctx):
        """Disable chatbot mode for this channel"""
        try:
            from utils.chatbot.manager import chatbot_manager
            
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
            current_history = await chatbot_manager.load_conversation_history(guild_id, channel_id)
            message_count = len(current_history)
            
            success = chatbot_manager.disable_chatbot(guild_id, channel_id)
            
            if success:
                # Clear conversation history when disabling chatbot
                await chatbot_manager.clear_conversation_history(guild_id, channel_id)
                history_cleared = True  # Assume success if no exception is raised
                
                history_msg = ""
                if history_cleared and message_count > 0:
                    history_msg = f"\n\n🗑️ Cleared {message_count} messages from conversation history and deleted the conversation file."
                
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
            from utils.chatbot.manager import chatbot_manager
            
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
            conversation_history = await chatbot_manager.load_conversation_history(guild_id, channel_id)
            
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
            from utils.chatbot.manager import chatbot_manager
            
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
        """Clear conversation history and set a checkpoint for this channel."""
        try:
            from utils.chatbot.manager import chatbot_manager
            
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
            
            await chatbot_manager.clear_channel_data(guild_id, channel_id)
            
            await create_embed_response(
                ctx,
                f"✅ Cleared channel data and set a checkpoint.\n\n"
                f"The chatbot will start fresh, and messages from before this point will not be re-indexed.",
                title="Channel Data Cleared",
                color=discord.Color.green()
            )
            logger.info(f"Cleared channel data for channel {ctx.channel.name} ({channel_id}) by {ctx.author}")
                
        except Exception as e:
            logger.error(f"Error clearing channel data: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while clearing channel data: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

    @commands.command(name='chatbot_remove_checkpoint')
    @has_command_permission("chatbot_clear_history")
    @command_category("AI Assistant")
    async def chatbot_remove_checkpoint(self, ctx):
        """Remove the indexing checkpoint for this channel."""
        try:
            from utils.chatbot.manager import chatbot_manager
            
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
            channel_config.last_cleared_timestamp = None
            chatbot_manager.set_channel_config(guild_id, channel_id, channel_config)
            
            await create_embed_response(
                ctx,
                f"✅ Removed indexing checkpoint.\n\n"
                f"The chatbot will now re-index messages from before the last clear.",
                title="Checkpoint Removed",
                color=discord.Color.green()
            )
            logger.info(f"Removed indexing checkpoint for channel {ctx.channel.name} ({channel_id}) by {ctx.author}")
                
        except Exception as e:
            logger.error(f"Error removing checkpoint: {e}", exc_info=True)
            await create_embed_response(
                ctx,
                f"An error occurred while removing the checkpoint: {str(e)}",
                title="Error",
                color=discord.Color.red()
            )

    @commands.command(name='debug_message_filter', aliases=['dbg_filter'])
    @has_command_permission()
    @command_category("AI Assistant(Debug)")
    async def debug_message_filter(self, ctx, *, test_message: str):
        """Test a message through the filter system (dev only)
        
        Arguments:
        - test_message: The message content to test
        """
        try:
            from utils.chatbot.manager import chatbot_manager, ConversationMessage
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
            
            cleaned_content, image_urls, embed_urls = await chatbot_manager._process_discord_message_for_context(dummy_discord_message)
            
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
    @has_command_permission()
    @command_category("AI Assistant(Debug)")
    async def debug_full_context(self, ctx, channel: Optional[discord.abc.Messageable] = None, user_id: int = None):
        """Export the complete LLM context to a file (dev only)
        
        Arguments:
        - channel: The channel to debug (defaults to current channel)
        - user_id: The user ID to generate context for (defaults to command author)
        """
        try:
            from utils.chatbot.manager import chatbot_manager
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
            context_messages = await chatbot_manager.get_prioritized_context(guild_id, channel_id, target_user_id)
            conversation_context, _ = await chatbot_manager.format_context_for_llm(context_messages, guild_id, channel_id)
            system_prompt = self.load_system_prompt(guild_id)
            server_context_file_content = self.load_context(guild_id) # Renamed to avoid confusion with conversation context
            channel_config = chatbot_manager.get_channel_config(guild_id, channel_id)
            
            # NEW: Get pinned messages context
            pinned_messages_context = await chatbot_manager.get_pinned_context_for_llm(guild_id, channel_id)

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
            content_lines.append(f"Messages from target user: {len([msg for msg in context_messages if int(msg.user_id) == target_user_id])}")
            content_lines.append(f"Messages from other users: {len([msg for msg in context_messages if int(msg.user_id) != target_user_id and not msg.is_bot_response])}")
            content_lines.append(f"Bot responses: {len([msg for msg in context_messages if msg.is_bot_response])}")
            
            # Get indexing stats
            indexing_stats = await chatbot_manager.get_indexing_stats(guild_id)
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

    @commands.group(name='llm_safety', invoke_without_command=True, help="""View or configure LLM safety settings.

    This command group allows you to manage content safety settings for the LLM.
    You can view and set safety thresholds for different harm categories at both the server and channel level.
    
    Use `!llm_safety view` to see the current settings.
    Use `!llm_safety set` to change the settings.
    
    If no subcommand is given, this help message will be shown.
    """)
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def llm_safety(self, ctx):
        """View or configure LLM safety settings for this server/channel."""
        if ctx.invoked_subcommand is None:
            help_embed = discord.Embed(
                title="LLM Safety Feature Help",
                description=self.llm_safety.help,
                color=discord.Color.blue()
            )
            
            for command in self.llm_safety.commands:
                # Format the signature to show parameters
                signature = f"`!llm_safety {command.name}"
                for param in command.clean_params.values():
                    signature += f" <{param.name}>"
                signature += "`"
                
                help_embed.add_field(
                    name=f"**{command.name.capitalize()}**",
                    value=f"{signature}\n{command.help}",
                    inline=False
                )
            
            await ctx.send(embed=help_embed)

    @llm_safety.command(name='view', help="""View the current safety settings.

    Shows the safety settings for the current channel, a specific channel, or the server.
    The settings shown are the result of the channel > server > global hierarchy.
    
    Usage:
    - `!llm_safety view`: Shows settings for the current channel.
    - `!llm_safety view #other-channel`: Shows settings for a specific channel.
    """)
    async def view_safety_settings(self, ctx, channel: Optional[discord.TextChannel] = None):
        """View the current safety settings for the server or a specific channel."""
        target_channel = channel or ctx.channel
        guild_id = ctx.guild.id
        
        server_settings = get_safety_settings(guild_id)
        channel_settings = get_safety_settings(guild_id, target_channel.id)

        sections = []
        server_fields = []
        for category, threshold in server_settings.items():
            server_fields.append(f"**{category.replace('_', ' ').title()}:** `{threshold}`")
        sections.append({
            "name": "Server Settings",
            "content": "\n".join(server_fields),
            "inline": True
        })

        channel_specific_fields = []
        channel_config = chatbot_manager.get_channel_config(guild_id, target_channel.id)
        if channel_config and channel_config.safety_settings:
            for category, threshold in channel_settings.items():
                channel_specific_fields.append(f"**{category.replace('_', ' ').title()}:** `{threshold}`")
            sections.append({
                "name": f"#{target_channel.name} Settings (Overrides Server)",
                "content": "\n".join(channel_specific_fields),
                "inline": True
            })
        else:
            sections.append({
                "name": f"#{target_channel.name} Settings",
                "content": "Inherits all settings from the server.",
                "inline": True
            })

        await create_embed_response(
            ctx,
            title=f"Safety Settings Overview",
            sections=sections,
            color=discord.Color.blue()
        )

    @llm_safety.command(name='set', help="""Set a safety setting for the server or a channel.

    Usage: `!llm_safety set <level> <category> <threshold>`

    Arguments:
    - `level`: `server` or a channel mention (e.g., #general).
    - `category`: `all`, `harassment`, `hate_speech`, `sexually_explicit`, `dangerous_content`.
    - `threshold`: `block_none`, `block_low_and_above`, `block_medium_and_above`, `block_only_high`.

    Examples:
    - `!llm_safety set server all block_none`
    - `!llm_safety set #general hate_speech block_medium_and_above`
    """)
    async def set_safety_settings(self, ctx, level: Optional[Union[discord.TextChannel, str]] = None, category: Optional[str] = None, threshold: Optional[str] = None):
        """Set a safety setting for the server or a specific channel."""
        if level is None or category is None or threshold is None:
            help_embed = discord.Embed(
                title=f"Help for: `!llm_safety {ctx.command.name}`",
                description=ctx.command.help,
                color=discord.Color.orange()
            )
            await ctx.send(embed=help_embed)
            return

        valid_categories = ["harassment", "hate_speech", "sexually_explicit", "dangerous_content"]
        categories_to_set = []

        if category.lower() == 'all':
            categories_to_set = valid_categories
        elif category.lower() in valid_categories:
            categories_to_set.append(category.lower())
        else:
            await create_embed_response(ctx, f"Invalid category. Use 'all' or one of: {', '.join(valid_categories)}", title="Error", color=discord.Color.red())
            return

        valid_thresholds = ["block_none", "block_low_and_above", "block_medium_and_above", "block_only_high"]
        if threshold.lower() not in valid_thresholds:
            await create_embed_response(ctx, f"Invalid threshold. Use one of: {', '.join(valid_thresholds)}", title="Error", color=discord.Color.red())
            return

        guild_id = ctx.guild.id
        
        if isinstance(level, str) and level.lower() == 'server':
            settings = get_safety_settings(guild_id)
            for cat in categories_to_set:
                settings[cat] = threshold.lower()
            save_server_safety_settings(guild_id, settings)
            await create_embed_response(ctx, f"Server safety setting for `{category}` updated to `{threshold}`.", title="✅ Success", color=discord.Color.green())
        elif isinstance(level, discord.TextChannel):
            channel = level
            channel_config = chatbot_manager.get_channel_config(guild_id, channel.id)
            if not channel_config.safety_settings:
                channel_config.safety_settings = get_safety_settings(guild_id, channel.id)
            
            for cat in categories_to_set:
                channel_config.safety_settings[cat] = threshold.lower()
            chatbot_manager.set_channel_config(guild_id, channel.id, channel_config)
            await create_embed_response(ctx, f"Channel safety setting for `{category}` in #{channel.name} updated to `{threshold}`.", title="✅ Success", color=discord.Color.green())
        else:
            await create_embed_response(ctx, "Invalid level. Use 'server' or a channel mention.", title="Error", color=discord.Color.red())
            return

    @commands.command(name='set_reasoning_budget', help="""Set the reasoning budget for a model.

    Usage: `!set_reasoning_budget <model> <level> [mode] [custom_budget]`

    Arguments:
    - `model`: The name of the model to configure.
    - `level`: `auto`, `none`, `low`, `medium`, or `high`.
    - `mode` (optional): `all`, `default`, `chat`, `ask`, or `think`. Defaults to `default`.
    - `custom_budget` (optional): `true` or `false`.
    """)
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def set_reasoning_budget(self, ctx, model: Optional[str] = None, level: Optional[str] = None, mode: Optional[str] = None, custom_reasoning_budget: bool = False):
        """Sets the reasoning budget for a specific model and mode."""
        if not model or not level:
            await ctx.send_help(ctx.command)
            return

        if not ctx.guild:
            await create_embed_response(ctx, "This command can only be used in a server.", title="Error", color=discord.Color.red())
            return

        # Workaround for optional positional bool argument
        if mode and mode.lower() in ['true', 'false']:
            custom_reasoning_budget = (mode.lower() == 'true')
            mode = None

        guild_id = ctx.guild.id
        level_map = {"auto": -1, "none": 0, "low": 1, "medium": 2, "high": 3}
        
        level_val = level_map.get(level.lower())
        if level_val is None:
            await create_embed_response(ctx, "Invalid level. Use 'auto', 'none', 'low', 'medium', or 'high'.", title="Error", color=discord.Color.red())
            return

        valid_modes = ["default", "chat", "ask", "think", "all"]
        if mode and mode.lower() not in valid_modes:
            await create_embed_response(ctx, f"Invalid mode. Use one of: `{'`, `'.join(valid_modes)}`", title="Error", color=discord.Color.red())
            return

        if mode and mode.lower() == 'all':
            modes_to_set = ["default", "chat", "ask", "think"]
            for target_mode in modes_to_set:
                save_reasoning_budget(model, target_mode, level_val, guild_id, custom_reasoning_budget=custom_reasoning_budget)
            await create_embed_response(ctx, f"Reasoning budget for model `{model}` for all modes set to `{level}` (Custom Reasoning Budget: {custom_reasoning_budget}).", title="Reasoning Budget Set", color=discord.Color.green())
        else:
            target_mode = mode.lower() if mode else "default"
            save_reasoning_budget(model, target_mode, level_val, guild_id, custom_reasoning_budget=custom_reasoning_budget)
            
            if mode:
                await create_embed_response(ctx, f"Reasoning budget for model `{model}` in mode `{mode}` set to `{level}` (Custom Reasoning Budget: {custom_reasoning_budget}).", title="Reasoning Budget Set", color=discord.Color.green())
            else:
                await create_embed_response(ctx, f"Default reasoning budget for model `{model}` set to `{level}` (Custom Reasoning Budget: {custom_reasoning_budget}).", title="Reasoning Budget Set", color=discord.Color.green())

    @commands.command(name='view_reasoning_budget', help='View the reasoning budget for all models.')
    @has_command_permission('manage_guild')
    @command_category("AI Assistant")
    async def view_reasoning_budget(self, ctx):
        """Displays the reasoning budget for all models on the server."""
        if not ctx.guild:
            await create_embed_response(ctx, "This command can only be used in a server.", title="Error", color=discord.Color.red())
            return

        guild_id = ctx.guild.id
        all_budgets = get_all_reasoning_budgets(guild_id)

        if not all_budgets:
            await create_embed_response(ctx, "No reasoning budgets have been set for this server.", title="No Reasoning Budgets Found", color=discord.Color.orange())
            return

        embed = discord.Embed(title="Reasoning Budget Configuration", color=discord.Color.blue())
        embed.description = "Showing configured reasoning budgets for all models on this server."
        
        level_map_inv = {-1: "auto", 0: "none", 1: "low", 2: "medium", 3: "high"}

        for model, budgets in all_budgets.items():
            budget_lines = []
            for mode, setting in budgets.items():
                if isinstance(setting, dict):
                    level = setting.get('level')
                    custom = setting.get('custom_reasoning_budget', setting.get('custom', False)) # Added backward compatibility
                    level_str = level_map_inv.get(level, str(level))
                    budget_lines.append(f"**{mode.title()}:** `{level_str}` (Custom Reasoning Budget: {'Yes' if custom else 'No'})")
                else: # Fallback for old format
                    level_str = level_map_inv.get(setting, str(setting))
                    budget_lines.append(f"**{mode.title()}:** `{level_str}` (Custom Reasoning Budget: No)")

            if budget_lines:
                embed.add_field(name=f"Model: `{model}`", value="\n".join(budget_lines), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='indexing_stats', help='Show indexing statistics for this server.')
    @has_command_permission()
    @command_category("AI Assistant")
    async def indexing_stats(self, ctx):
        """Displays statistics about the user and channel indexes for this server."""
        if not ctx.guild:
            await create_embed_response(ctx, "This command can only be used in a server.", title="Error", color=discord.Color.red())
            return

        guild_id = ctx.guild.id
        stats = await chatbot_manager.index_manager.get_indexing_stats(guild_id)

        embed = discord.Embed(title=f"Indexing Statistics for {ctx.guild.name}", color=discord.Color.blue())
        embed.add_field(name="👥 Users Indexed", value=f"`{stats['users_indexed']}`", inline=True)
        embed.add_field(name="＃ Channels Indexed", value=f"`{stats['channels_indexed']}`", inline=True)
        embed.add_field(name="💬 Total User Messages", value=f"`{stats['total_user_messages']}`", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name='cleanup_users', help='Manually clean up stale users from the index.')
    @has_command_permission()
    @command_category("AI Assistant")
    async def cleanup_users(self, ctx, hours: int = 168):
        """Manually cleans up users who have not been seen in the specified number of hours."""
        if not ctx.guild:
            await create_embed_response(ctx, "This command can only be used in a server.", title="Error", color=discord.Color.red())
            return

        if not (24 <= hours <= 8760): # 1 day to 1 year
            await create_embed_response(ctx, "Please provide a value for `hours` between 24 and 8760.", title="Invalid Input", color=discord.Color.orange())
            return

        async with ctx.typing():
            removed_count = await chatbot_manager.index_manager.cleanup_stale_users(ctx.guild.id, hours)
            await create_embed_response(
                ctx,
                f"Removed `{removed_count}` stale users who haven't been seen in the last {hours} hours.",
                title="User Cleanup Complete",
                color=discord.Color.green()
            )

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(LLMCommands(bot))

