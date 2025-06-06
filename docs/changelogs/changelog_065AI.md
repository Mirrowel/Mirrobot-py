# Mirrobot v0.65 AI Changelog

Welcome to the **Mirrobot v0.65 AI** update! This version introduces significant new capabilities focused around integrating Large Language Models (LLMs) into the bot, providing both direct querying and a persistent, conversational chatbot mode. Alongside these major features, I've also improved infrastructure and maintenance.

## ✨ New Features

**1. Large Language Model (LLM) Integration**

*   **Flexible Backend Support:** Mirrobot can now connect to either:
    *   A **local LLM server** (compatible with OpenAI API format, like LM Studio or Ollama with `--api` flag).
    *   The **Google AI API** (supporting models like Gemma and Gemini).
*   **Direct LLM Queries with Distinct Modes:** The bot now offers two primary commands for direct interaction, utilizing different system prompts and LLM behaviors:
    *   `!ask <question>`: **For standard, non-thinking responses.** Use this when you need a direct, concise answer without seeing the LLM's step-by-step reasoning. This command uses the standard system prompt (`llm_data/system_prompt.txt` or default).
    *   `!think [display_thinking] <question>`: **Engages the LLM's internal thinking process.** This command uses a *separate, thinking-oriented* system prompt (`llm_data/system_prompt_thinking.txt` or default) designed to encourage the model to show its reasoning (often via thinking tokens like ``).
        *   The optional `display_thinking` argument (defaulting to `False`) controls whether the extracted thinking tokens are shown in the final output embed (wrapped in spoilers) or stripped away. Use `!think true <question>` to display the thinking process.
*   **Model Management:**
    *   `!llm_status`: Check the connection status, provider, and currently used model.
    *   `!llm_models [filters]`: List available models from the current provider. Supports filters like `all` or `pro_vision_tts` for Google AI to control which models are shown. Marks the currently selected model with 🟢.
    *   `!llm_select <model_name or number>`: Change the model the bot uses for all LLM requests. For local LLMs, this preference is saved per server. For Google AI, this sets the global default model.
*   **Provider Configuration:**
    *   `!llm_provider <local|google_ai>`: Switch between using a local LLM server and the Google AI cloud service. This affects which models are available and used.
    *   `!llm_set_api_key <api_key>`: (For Google AI provider) Set your Google AI API key. **Your message containing the key will be automatically deleted for security.**
*   **Intelligent Response Formatting:** LLM responses are now automatically formatted into clean, multi-part embeds. This system intelligently handles very long answers by splitting them across multiple fields and even multiple embed messages if needed. It automatically extracts and handles thinking tokens (displaying them based on the `show_thinking` flag, often spoiler-tagged) and includes performance metrics (time taken, tokens/characters per second).
*   **Automatic Text-to-Mention Conversion:** The bot attempts to convert text references like `@Username` or even just `Username` found in LLM responses into actual Discord mentions (`<@UserID>`) where possible. This is done by referencing a local user index. Crucially, self-mentions of the bot itself (by name or mention) are automatically removed from the response to prevent self-talk loops.

**2. Conversational AI (Chatbot Mode)**

*   **Channel-Specific Enablement:** Turn Mirrobot into a persistent, conversational chatbot in specific channels.
    *   `!chatbot_enable`: Activate chatbot mode in the current channel. When enabled, the bot starts tracking conversation history and indexes users and pinned messages for context.
    *   `!chatbot_disable`: Deactivate chatbot mode in the current channel. This also clears the conversation history for that channel.
*   **Persistent Conversation Context:** The bot remembers recent conversation history (messages) in enabled channels. This history is saved to disk, allowing conversations to persist across bot restarts and maintenance.
*   **Automatic Responses:** When enabled, the bot can automatically generate an LLM response based on the conversation context when:
    *   It is directly mentioned (`@Mirrobot`).
    *   A user replies directly to one of its messages.
    *   **Chatbot Mode Defaults to Non-Thinking:** Responses generated in chatbot mode use the **same standard, non-thinking system prompt** as the `!ask` command.
*   **Configurable Context:**
    *   `!chatbot_config <setting> <value>`: Customize how the bot manages context and responses for the specific channel the command is used in. Settings include:
        *   `context_window <hours>`: How far back in time messages are considered relevant for context (1-168 hours).
        *   `max_messages <number>`: Maximum total messages (user and bot) to include in the context provided to the LLM (10-200).
        *   `max_user_messages <number>`: Maximum messages specifically from the *requesting user* to prioritize in the context, ensuring their recent inputs are included (5-50).
        *   `response_delay <seconds>`: An optional delay before the bot starts typing and sends a response (0-10 seconds).
        *   `max_response_length <chars>`: Maximum character length for the bot's response in chatbot mode (100-4000). Responses exceeding Discord's 2000-character limit will be split.
        *   `auto_prune <true/false>`: Enable/disable automatic cleanup of old messages from the channel's history file based on `context_window` and `max_messages`.
        *   `prune_interval <hours>`: How often the automatic pruning task runs for this channel (1-48 hours).
        *   `mentions <true/false>`: Enable/disable automatic responses when the bot is mentioned.
        *   `replies <true/false>`: Enable/disable automatic responses when a user replies to a bot message.
    *   `!chatbot_config`: Use the command without arguments to view a list of available configuration settings and their descriptions.
*   **Contextual Understanding:** The chatbot mode builds a richer understanding of the conversation environment. It utilizes an internal index of:
    *   **Users:** Tracks users who participate in conversations, including their Discord username (user.name), display name (nickname), roles, and basic activity. This allows the LLM to refer to participants by their actual Discord usernames.
    *   **Channels:** Indexes metadata about the channel itself (name, topic, category, NSFW status) to provide context about the discussion environment.
    *   **Pinned Messages:** Indexes messages pinned in the channel, treating them as important, persistent context for the LLM.
*   **Message Filtering:** Messages are intelligently filtered before being added to the channel's conversation history. This includes ignoring common command prefixes, messages that are only whitespace or special characters, and filtering out media like videos/GIFs while retaining image attachments.
*   **Conversation Management Commands:**
    *   `!chatbot_status`: Show the current chatbot configuration and conversation statistics for the channel (enabled status, config values, total messages in context, user/bot message counts, last activity).
    *   `!chatbot_clear_history`: Manually clear the conversation history for the current channel, allowing the bot to start fresh.
*   **Background Indexing & Cleanup:** Users, channels, and pinned messages are indexed in the background. A regular task prunes old conversation messages based on channel configuration. A separate periodic task cleans up stale user entries from the index (default: users not seen in 7 days) across all guilds. Automatic re-indexing of enabled channels and pins occurs on bot startup.
*   **Developer Debug Commands (Owner Only):**
    *   `!debug_message_filter <test_message>`: Test how a specific message would be filtered for conversation history, showing detailed analysis steps.
    *   `!debug_full_context [channel] [user_id]`: Export the complete structured context that would be sent to the LLM for a specific channel and user, including system prompt, channel info, user info, pinned messages, and conversation history, into a file.

## ⚡ Improvements

*   **Dedicated Maintenance Cog:** Maintenance commands and the auto-restart task have been moved to a new `Maintenance` cog for better modularity and organization.
*   **Enhanced Auto-Restart Configuration:** The automatic restart functionality is now more configurable and managed via commands:
    *   `!toggle_auto_restart`: Easily enable or disable the scheduled restart task.
    *   `!set_restart_time <time>`: Set the uptime threshold before an automatic restart occurs (e.g., `!set_restart_time 24h`, `!set_restart_time 12h30m`, `!set_restart_time 45m`). Minimum interval is 30 minutes.
    *   `!show_restart_settings`: Display the current auto-restart status, interval threshold, and check frequency.
*   **Improved Embed Helper:** The utility for creating Discord embeds (`utils/embed_helper.py`) has been significantly upgraded to support:
    *   Intelligent text splitting that preserves paragraphs and sentences, ensuring long content fields are split correctly across multiple fields, making embeds more readable.
    *   Structured content sections (specifically utilized for LLM answers and thinking processes in `create_llm_response`) allowing for clearer presentation of different parts of a response with emoji prefixes and optional spoiler tags.
    *   Automatic splitting of very large embeds (either too many fields or exceeding Discord's total character limit per embed) into multiple sequential messages, clearly labelled as parts (Part 1/X, Part 2/X, etc.).
*   **More Robust Token Loading:** The bot's login process will now first look for the Discord token in the `config.json` file, then fall back to checking the `DISCORD_BOT_TOKEN` environment variable. This provides more flexibility for deployment and secret management. Similarly, the Google AI API key will check the environment variable `GOOGLE_AI_API_KEY` if not set in the dedicated `llm_config.json`.
*   **Raw Event Handling for History:** Added listeners for `on_raw_message_edit` and `on_raw_message_delete`. This allows the bot to update its conversation history correctly when messages are edited or deleted, even if those messages were too old to be present in the bot's local cache at the time of the event.
*   **Improved Command Error Handling:** Refined the global command error handler (`on_command_error`) for more specific logging. It now distinguishes between different error types (missing permissions, cooldown, etc.) and provides cleaner, less technical error messages to the user for unhandled exceptions. Permission denial errors from the custom check are now handled silently by the check itself, preventing duplicate error messages.
*   **New Intents Added:** Required Discord gateway intents (`members`, `presences`) have been added to allow the bot to accurately fetch necessary user data (roles, status, correct usernames) for building the user index and formatting LLM output. **Note:** These intents require specific approval in the Discord Developer Portal for large bots.
*   **Owner-Only LLM Provider/Model Commands:** Commands related to switching LLM models (`llm_models`, `llm_select`), setting the provider (`llm_provider`), and configuring the Google AI API key (`llm_set_api_key`) are now restricted to the bot owner (`commands.is_owner()`) for enhanced security and control over the bot's core AI configuration.

## 🛠️ Behind the Scenes

*   **Dedicated LLM Configuration File:** LLM settings (`base_url`, `provider`, `api_keys`, `model_names`, server-specific preferred models) are now stored in a separate `data/llm_config.json` file, improving configuration organization and separation of concerns from the main bot config.
*   **Automatic Configuration Migration:** On startup, the bot includes logic to automatically detect and migrate old LLM settings from the main `config.json` and the legacy `chatbot_config.json` (if they exist) to the new `data/llm_config.json`. This ensures a smooth transition for existing installations.
*   **New ChatbotManager Utility:** A comprehensive `utils/chatbot_manager.py` class has been implemented to encapsulate and handle all logic related to chatbot mode. This includes channel configuration, conversation history storage and retrieval, user and channel indexing, context formatting for the LLM, pruning, and determining when to respond. This significantly centralizes the code and makes the chatbot functionality more maintainable and extensible.
*   **Refactored LLM Request Logic:** The core `make_llm_request` method in `LLMCommands` now handles routing the request to the correct provider backend (local or Google AI) and preparing the message payload according to the provider's requirements, simplifying the command implementations (`!ask`, `!think`). System prompt and context loading is also unified.
*   **Integration with Google AI API:** Added necessary imports (`google.generativeai`, etc.) and implemented the logic to interact with the Google AI `generate_content` API, handling different model behaviors (like Gemma vs. non-Gemma prompt formats) and basic safety settings.
*   **Updated Dependencies:** Includes necessary imports and reflects refactored utility functions and configuration managers.

## 🐛 Bug Fixes

*   Corrected minor issues in permission checks and error logging to be more accurate and informative.
*   Ensured self-mentions of the bot itself (by name or mention) are consistently removed from LLM responses, particularly in chatbot mode, to prevent unwanted self-talk or loops.
*   Added more robust filtering logic for messages added to the conversation history to exclude various forms of commands, pure whitespace messages, and messages consisting solely of media types explicitly filtered (like videos/GIFs).
*   Addressed potential issues with loading older configuration formats during the migration process.
*   Resolved potential issues with correctly updating or deleting messages from the conversation history when messages are not present in Discord.py's local cache by using raw event data.
*   Fixed an issue where the Google AI client might not re-initialize correctly when the model name or system instruction (for non-Gemma models) changed.