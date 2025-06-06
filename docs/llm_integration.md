# LLM and Chatbot Integration Guide

This guide provides detailed information on setting up, configuring, and using the LLM (Large Language Model) and Chatbot features within Mirrobot.

## Overview

Mirrobot can integrate with both locally hosted Large Language Models (like those running on LM Studio or Ollama) and cloud-based services like Google AI (Gemini). This integration allows the bot to respond to queries and engage in persistent conversations within designated channels.

The LLM and Chatbot features are managed through separate configuration files and commands:

* **LLM Configuration (`data/llm_config.json`):** Controls the connection details for the LLM provider (local or cloud), timeouts, retry settings, and server-specific model preferences.
* **Chatbot Configuration (`data/chatbot_config.json`):** Controls the behaviour of the persistent chatbot feature, including per-channel enablement, conversation context settings (window size, message limits), auto-response triggers, response delays, and pruning.
* **User and Channel Indexes (`data/user_index/`, `data/channel_index/`):** These directories store metadata about users and channels the bot interacts with, which can be included in the LLM context to provide the model with awareness of the server environment and its members.
* **Conversation Data (`data/conversations/`):** Stores the history of messages in chatbot-enabled channels for conversational context.
* **Pinned Message Data (`data/pins/`):** Stores indexed pinned messages from channels to provide important context to the LLM.

If these directories and files (except for conversation data, which is created per channel) do not exist, they will be created with default values on bot startup or when relevant commands are used.

## Configuration Files

### `data/llm_config.json` Structure and Options

This file manages the connection details and model preferences for the LLM service.

```jsonc
{
    "base_url": "http://localhost:1234", // Base URL for local LLM servers (e.g., LM Studio, Ollama)
    "timeout": 120,           // Request timeout in seconds for LLM requests
    "max_retries": 3,         // Number of retry attempts for failed LLM requests
    "retry_delay": 2,         // Delay between retries in seconds
    "provider": "local",      // Global LLM provider: "local" or "google_ai"
    "google_ai_api_key": null,// API key for Google AI services (Can also be set via GOOGLE_AI_API_KEY env var)
    "google_ai_model_name": "gemma-3-27b-it", // Default model for Google AI provider
    "servers": {              // Server-specific configurations (primarily for local provider)
        "YOUR_GUILD_ID_HERE": {
            "enabled": true,          // Enable/disable local LLM requests specifically for this server
            "preferred_model": null,  // Preferred local model for this server (overrides global default)
            "last_used_model": null   // Last successfully used model for this server (updated automatically)
        }
        // Add entries for other guilds as needed. If a guild is not listed, global settings apply.
    }
}
```

* `base_url`: The URL where your local LLM server is hosted. Required and used only when `provider` is `local`.
* `timeout`: The maximum time in seconds to wait for a response from the LLM server.
* `max_retries`: The number of times the bot will attempt to retry a failed LLM request.
* `retry_delay`: The delay in seconds between retry attempts.
* `provider`: Specifies the global LLM service to use. Can be `local` (your own server) or `google_ai` (Google's cloud models). Set using the `!llm_provider` command.
* `google_ai_api_key`: Your API key for accessing Google AI services. It is highly recommended to set this via the `GOOGLE_AI_API_KEY` environment variable on your system for security. If the environment variable is set, it will override this setting in the file. Can be set using the `!llm_set_api_key` command (message is deleted). Only used when `provider` is `google_ai`.
* `google_ai_model_name`: The default model to use when the `provider` is `google_ai`. Set using the `!llm_select` command.
* `servers`: This optional section allows server-specific overrides.
    * `YOUR_GUILD_ID_HERE`: Replace with the actual Discord server (guild) ID (as a string).
        * `enabled`: A boolean (`true`/`false`). If `provider` is `local`, setting this to `false` disables the `!ask` and `!think` commands specifically for this server. Default is `true` if no entry exists for the guild. This setting has no effect when `provider` is `google_ai`.
        * `preferred_model`: The name of a specific local model you want this server to use. If set, it overrides any global default model for this server when the `provider` is `local`. Set using `!llm_select` within the server.
        * `last_used_model`: Automatically updated field storing the last model name successfully used for this server.

### `data/chatbot_config.json` Structure and Options

This file manages the settings for the persistent chatbot feature. Settings can be global or overridden per channel.

```jsonc
{
    "channels": {
        "YOUR_GUILD_ID_HERE": {
            "YOUR_CHANNEL_ID_HERE": {
                "enabled": true,             // Enable/disable chatbot in this channel (default: false)
                "max_context_messages": 100, // Max total messages in context (default: 100, range 10-200)
                "max_user_context_messages": 20,// Max messages from the requesting user in context (default: 20, range 5-50)
                "context_window_hours": 24,  // Time window for context messages in hours (default: 24, range 1-168)
                "response_delay_seconds": 1, // Delay before typing indicator and response (default: 1, range 0-10)
                "max_response_length": 2000, // Max length of bot's response in characters (default: 2000, range 100-4000)
                "auto_prune_enabled": true,  // Enable automatic pruning of old history (default: true)
                "prune_interval_hours": 6,   // How often auto-pruning runs in hours (default: 6, range 1-48)
                "auto_respond_to_mentions": true, // Bot responds when mentioned (default: true)
                "auto_respond_to_replies": true   // Bot responds when replied to (default: true)
            }
            // Add entries for other channels in this guild
        }
        // Add entries for other guilds
    },
    "global": { // Default settings apply to any channel/setting not specified in the "channels" section
        "max_context_messages": 100,
        "max_user_context_messages": 20,
        "context_window_hours": 24,
        "response_delay_seconds": 1,
        "max_response_length": 2000,
        "auto_prune_enabled": true,
        "prune_interval_hours": 6,
        "user_index_cleanup_hours": 168, // How often to remove stale users from index (default: 168 hrs/7 days)
        "auto_index_on_restart": true,   // Automatically re-index enabled channels and pins on bot startup (default: true)
        "auto_index_on_enable": true     // Automatically index a channel and its pins when chatbot is enabled (default: true)
    }
}
```

* `channels`: This section holds channel-specific configurations. An entry for a guild and channel overrides the global defaults.
    * `YOUR_GUILD_ID_HERE`: Replace with the actual Discord server (guild) ID (as a string).
        * `YOUR_CHANNEL_ID_HERE`: Replace with the actual Discord channel ID (as a string).
            * `enabled`: A boolean (`true`/`false`) to enable or disable the chatbot in this specific channel. Can be toggled using `!chatbot_enable` and `!chatbot_disable`. Defaults to `false` if the channel/guild is not listed.
            * `max_context_messages`: Maximum total messages from the conversation history (including user and bot messages) to include in the context sent to the LLM. Higher values increase memory but use more tokens.
            * `max_user_context_messages`: Maximum number of messages from the *requesting user* specifically to prioritize and include in the context. This ensures the LLM remembers the user's recent contributions.
            * `context_window_hours`: Only messages posted within this time window (relative to the current time) will be considered for context, even if `max_context_messages` hasn't been reached.
            * `response_delay_seconds`: The minimum time in seconds the bot will wait after receiving a trigger message before starting to type and send a response. Set to 0 for instant response.
            * `max_response_length`: The maximum character length of the bot's generated response. Responses exceeding Discord's 2000 character limit will be automatically truncated.
            * `auto_prune_enabled`: If `true`, the bot will periodically prune the saved conversation history for this channel based on `context_window_hours` and `max_context_messages` to manage file size and memory.
            * `prune_interval_hours`: How often the automatic pruning task will run for this channel if `auto_prune_enabled` is true.
            * `auto_respond_to_mentions`: If `true`, the bot will automatically respond if its mention is present in a message in this channel.
            * `auto_respond_to_replies`: If `true`, the bot will automatically respond if a message in this channel is a reply to a message previously sent by the bot.
* `global`: Default settings applied to any channel or configuration option not specifically defined in the `channels` section.
    * `user_index_cleanup_hours`: How often users who haven't been seen (interacted with the bot or appeared in context) are removed from the user index files. This helps keep the user index relevant and smaller.
    * `auto_index_on_restart`: If `true`, the bot will automatically re-index all chatbot-enabled channels (fetch recent history, update channel/user indexes, index pins) upon startup. This ensures the context is fresh after a bot restart.
    * `auto_index_on_enable`: If `true`, the bot will automatically index a channel and its pins when chatbot mode is enabled for that channel using the `!chatbot_enable` command.

## Core Functionality

### LLM Providers (`local` and `google_ai`)

The bot supports connecting to different LLM services configured via `data/llm_config.json`:

* **Local LLM:** Connects to a server running locally or on your network, exposing an OpenAI-compatible API (like LM Studio, Ollama, etc.) at the `base_url`. This provider is active when `llm_config.json`'s `provider` is set to `"local"`. Server-specific `enabled` and `preferred_model` settings apply here.
* **Google AI:** Connects to Google's cloud-based Gemini models using your API key. This provider is active when `llm_config.json`'s `provider` is set to `"google_ai"`. Requires an API key set via config or environment variable. Server-specific `enabled` and `preferred_model` settings in `llm_config.json` do *not* apply to Google AI; Google AI settings are global (`google_ai_api_key`, `google_ai_model_name`).

You can switch the active provider using the `!llm_provider` command.

### LLM Status and Model Management

* **Status Checks:** The bot automatically checks if the configured LLM is online when needed. For local LLMs, it attempts to connect to health endpoints or make a test request. For Google AI, it verifies successful initialization with the API key and lists models. You can manually trigger a status check with `!llm_status`.
* **Listing Models:** The `!llm_models` command lists models available from the *currently active provider*.
    * For **local LLMs**, it queries the `/v1/models` (LM Studio compatible) and `/api/tags` (Ollama compatible) endpoints on your `base_url`. It lists all models found.
    * For **Google AI**, it lists models available via the API that support text generation. By default, it shows a curated list (Gemma, Gemini 2.5 Flash). You can use filters (`all`, `pro_vision_tts`) to see more models.
* **Selecting Models:** The `!llm_select <model_name_or_number>` command allows you to choose which specific model to use from the available list.
    * For **local LLMs**, this sets the `preferred_model` for the guild the command was used in (or globally if used outside a guild). This preference is saved and loaded on startup. The bot will attempt to use this preferred model if it's available.
    * For **Google AI**, this sets the global `google_ai_model_name`. This affects all interactions using the Google AI provider.

### System Prompts and Additional Context

The bot can utilize a system prompt and additional static context files to guide the LLM's behaviour and provide persistent information.

* **System Prompt:** A `system_prompt.txt` file (or `system_prompt_thinking.txt`) can be placed in `llm_data/` (for a global default) or `llm_data/guild_<guild_id>/` (for a server-specific override). This file contains instructions for the LLM, defining its persona, rules, or format requirements.
    * `system_prompt.txt` is used for standard `!ask` commands and chatbot responses.
    * `system_prompt_thinking.txt` is used for `!think` commands. If a thinking-specific prompt doesn't exist, the standard one is used.
    * These are loaded by the bot on startup and when needed.
* **Additional Context:** A `context.txt` file can be placed in `llm_data/` (global) or `llm_data/guild_<guild_id>/` (server-specific). This file can contain static information the LLM should be aware of (e.g., common abbreviations in the server, lore details).
* **Loading Order:** Server-specific files (in `llm_data/guild_<guild_id>/`) override the global files (in `llm_data/`).

### Chatbot Mode (`!chatbot_enable`, `!chatbot_disable`)

This feature enables the bot to act as a conversational agent in specific channels.

* **Enabling/Disabling:** Use `!chatbot_enable` in a channel to turn on chatbot mode. The bot will automatically begin indexing the channel's recent history and pinned messages (if `auto_index_on_enable` is true) and start monitoring for trigger messages. Use `!chatbot_disable` to turn it off; this also clears the stored conversation history for that channel.
* **Triggering Responses:** In an enabled channel, the bot will automatically generate a response if:
    * Its mention (`@Mirrobot`) is in the message (if `auto_respond_to_mentions` is true).
    * The message is a reply to a message previously sent by the bot in that channel (if `auto_respond_to_replies` is true).
    * **Note:** Unlike some simpler chatbots, there is no keyword list trigger in this implementation. Mentions and replies are the primary triggers.

### Conversation Context Management

When chatbot mode is enabled in a channel, the bot actively manages the conversation history to provide context to the LLM.

* **Storage:** Messages in enabled channels are stored in `data/conversations/guild_<guild_id>/channel_<channel_id>.json`.
* **Filtering:** Not all messages are stored or included in context. System messages, command invocations, messages that become empty after filtering media (like filtered videos/GIFs), and messages consisting only of whitespace/special characters are excluded by the `_is_valid_context_message` filter.
* **Media Handling:** Image attachments and image embeds are noted (via URL) and included as indicators in the context provided to the LLM. Video and GIF attachments/embeds are filtered out of the textual content.
* **Context Limits:** The `chatbot_config.json` settings control the size and relevance of the context:
    * `context_window_hours`: Messages older than this time window are ignored.
    * `max_context_messages`: The absolute maximum number of messages to include, even within the time window.
    * `max_user_context_messages`: A preference to prioritize including this many recent messages specifically from the user who triggered the response. The system attempts to include the most recent `max_user_context_messages` from the requesting user, then fills the remaining slots up to `max_context_messages` with other recent messages, while maintaining overall chronological order.
* **Pruning:** Conversation history files can grow large. Automatic pruning (`auto_prune_enabled`, `prune_interval_hours`) periodically trims the stored history based on the same time and message limits used for context retrieval. Manual clearing is also possible via `!chatbot_clear_history`.

### User and Channel Indexing

To provide the LLM with awareness about the Discord environment, the bot maintains simple indexes.

* **User Index:** Stored in `data/user_index/guild_<guild_id>_users.json`. This index stores basic information about users the bot has seen interact with it (send messages, get mentioned) in guilds where chatbot is enabled. It includes Discord username (`user.name`), display name (nickname), roles, avatar URL, status, first/last seen timestamps, and message count. This information is used to provide a "Known Users" context block to the LLM. The index is updated from incoming messages and periodically cleaned up (`user_index_cleanup_hours`) to remove stale entries.
* **Channel Index:** Stored in `data/channel_index/guild_<guild_id>_channels.json`. This index stores basic information about channels where chatbot mode is enabled, or channels indexed during other operations. It includes channel name, type (text, thread, etc.), topic, category, NSFW status, and associated guild info. This information is used to provide a "Current Channel Info" context block to the LLM. Indexed channels are updated automatically when chatbot is enabled.

### Pinned Message Indexing (NEW)

* **Storage:** Pinned messages for chatbot-enabled channels are indexed and stored separately in `data/pins/guild_<guild_id>_channel_<channel_id>_pins.json`.
* **Indexing:** When chatbot mode is enabled for a channel (`!chatbot_enable`) and when `auto_index_on_enable` is true, the bot fetches the current pinned messages from Discord and saves them. On bot restart, if `auto_index_on_restart` is true, it also re-indexes pins for all previously enabled channels.
* **Context:** Indexed pinned messages are included as a separate "Pinned Messages" block in the context provided to the LLM, indicating their importance. Pinned messages are processed through the same content filters as regular messages (`_is_valid_context_message`, `_process_discord_message_for_context`), ensuring only valid content is included.

### Automatic Features

* **Auto-respond to Mentions/Replies:** Configurable per channel via `chatbot_config.json` and `!chatbot_config`.
* **Auto-pruning:** Configurable per channel via `chatbot_config.json` and `!chatbot_config`. Runs periodically based on `prune_interval_hours`.
* **Auto-indexing on Restart:** Configurable globally via `chatbot_config.json`. Ensures enabled channels and their pins have up-to-date context loaded into the bot's manager instance when the bot starts.

### Discord Format Conversion

The bot performs conversions to make communication between Discord and the LLM smoother:

* **Discord to LLM:** When adding messages to history or preparing context, Discord mentions (`<@!ID>`, `<@ID>`) and custom emotes (`<:name:ID>`, `<a:name:ID>`) are converted to a more LLM-readable text format (e.g., `@Username`, `(emote_name emoji)`). Stray numerical IDs that might appear near emotes are also cleaned up. Image attachments and embeds are noted as `(Image: url)`. Video/GIF content is filtered out.
* **LLM to Discord:** When the LLM generates a response, text patterns that look like mentions (e.g., `@Username`, `<Ping> @Username`, or even just a plain `Username` that matches a known user) are converted into actual Discord mentions (`<@USER_ID>`) where possible, based on the user index. This allows the LLM to effectively "mention" users. The bot also attempts to remove any self-references or self-mentions the LLM might generate.

### Performance Metrics

For `!ask` and `!think` commands, and potentially logged for chatbot responses, the bot calculates and may display performance metrics like elapsed time, characters per second, and estimated/actual tokens per second/total tokens. This provides insight into the LLM's responsiveness and cost (for token-based models).

## Commands

The following commands are available for managing and interacting with the LLM and Chatbot features:

*(Commands are typically prefixed by the bot's configured command prefix, e.g., `!`)*

### LLM Connection and Model Commands

* `llm_provider <provider>`
    * **Description:** Sets the global LLM provider to use.
    * **Arguments:** `<provider>` - Must be `local` or `google_ai`.
    * **Examples:**
        * `!llm_provider google_ai` - Switch to using Google AI models.
        * `!llm_provider local` - Switch to using your locally hosted LLM.
    * **Permissions:** Requires `manage_guild` permission.
* `llm_set_api_key <api_key>`
    * **Description:** Sets the Google AI API key. The message containing the key is automatically deleted for security. This key is saved to `data/llm_config.json` but will be overridden by the `GOOGLE_AI_API_KEY` environment variable if set.
    * **Arguments:** `<api_key>` - Your Google AI API key.
    * **Example:** `!llm_set_api_key AIza...`
    * **Permissions:** Requires `manage_guild` permission.
* `llm_status`
    * **Description:** Displays the current LLM provider, connection status, active model, and key configuration details.
    * **Permissions:** Requires `manage_messages` permission.
* `llm_models [filters]`
    * **Description:** Lists available models for the currently active LLM provider.
    * **Arguments:** `[filters]` - Optional. Can be `all` (list all supported models for the provider) or `pro_vision_tts` (list Google AI `pro`, `vision`, `tts`, `gemma`, `2.5-flash` models - applies only if provider is `google_ai`). Leave empty for the default curated list (Gemma, 2.5-flash for Google AI; all for local).
    * **Examples:**
        * `!llm_models` - List default models.
        * `!llm_models all` - List all available models for the current provider.
        * `!llm_models pro_vision_tts` - List specific Google AI model types (if provider is google_ai).
    * **Permissions:** Requires `manage_messages` permission.
* `llm_select <model_name_or_number>`
    * **Description:** Selects a specific model to use. For local LLM, this sets the preferred model for the current server. For Google AI, this sets the global model. Can be specified by model name or its number in the `!llm_models` list.
    * **Arguments:** `<model_name_or_number>` - The name of the model or its corresponding number from the `!llm_models` list.
    * **Examples:**
        * `!llm_select llama-3.1-8b-instruct` - Select by name (local).
        * `!llm_select 3` - Select the 3rd model in the list (local or google_ai).
        * `!llm_select gemini-1.5-pro-latest` - Select by name (google_ai).
    * **Permissions:** Requires `manage_guild` permission.

### Direct LLM Query Commands

* `ask <question>`
    * **Description:** Sends a question to the LLM and provides the response. Does not show the LLM's internal "thinking" steps (if the model provides them via specific tokens).
    * **Arguments:** `<question>` - The question you want to ask the LLM.
    * **Example:** `!ask What is the capital of France?`
    * **Permissions:** Requires `manage_messages` permission.
* `think [display_thinking] <question>`
    * **Description:** Sends a question to the LLM using a "thinking" system prompt (if configured) and optionally displays the LLM's internal "thinking" steps (if the model provides them using specific tokens like ``).
    * **Arguments:**
        * `[display_thinking]` - Optional boolean (`true`/`false`). Set to `true` to include thinking steps in the response. Defaults to `false`.
        * `<question>` - The question you want to ask the LLM.
    * **Examples:**
        * `!think What are the steps to make a perfect sandwich?` - Ask the question, hide thinking.
        * `!think true Explain how a combustion engine works step-by-step` - Ask the question, show thinking steps.
    * **Permissions:** Requires `manage_guild` permission.

### Chatbot Control and Configuration Commands

* `chatbot_enable`
    * **Description:** Enables chatbot mode for the current channel. The bot will start monitoring for mentions and replies in this channel and respond using the configured LLM. Requires the configured LLM service to be online. Automatically indexes the channel's recent history and pins if `auto_index_on_enable` is true.
    * **Permissions:** Requires `chatbot_enable` permission (configured via `!perms` or similar).
* `chatbot_disable`
    * **Description:** Disables chatbot mode for the current channel. The bot will stop monitoring for triggers. Clears the conversation history for this channel.
    * **Permissions:** Requires `chatbot_disable` permission.
* `chatbot_status`
    * **Description:** Shows whether chatbot mode is enabled for the current channel and displays its configuration settings (context window, response triggers, etc.) and conversation history statistics.
    * **Permissions:** Requires `chatbot_status` permission.
* `chatbot_config [setting] [value]`
    * **Description:** Views or modifies the chatbot configuration for the current channel. Use without arguments to see available settings.
    * **Arguments:**
        * `[setting]` - The name of the setting to modify (e.g., `context_window`, `max_messages`, `mentions`).
        * `[value]` - The new value for the setting (e.g., `24`, `150`, `true`).
    * **Available Settings:**
        * `context_window <hours>`: Hours to keep messages in context (Range: 1-168).
        * `max_messages <number>`: Maximum total messages in context (Range: 10-200).
        * `max_user_messages <number>`: Maximum messages from the requesting user in context (Range: 5-50).
        * `response_delay <seconds>`: Delay before typing indicator and response (Range: 0-10, can be float).
        * `max_response_length <chars>`: Maximum character length of bot's response (Range: 100-4000).
        * `auto_prune <true/false>`: Enable/disable automatic conversation pruning.
        * `prune_interval <hours>`: Hours between auto-prune runs (Range: 1-48).
        * `mentions <true/false>`: Enable/disable auto-response to mentions.
        * `replies <true/false>`: Enable/disable auto-response to replies.
    * **Examples:**
        * `!chatbot_config` - Show available settings.
        * `!chatbot_config context_window 48` - Set context window to 48 hours.
        * `!chatbot_config max_messages 150` - Set max context messages to 150.
        * `!chatbot_config mentions false` - Disable auto-responding to mentions.
    * **Permissions:** Requires `chatbot_config` permission.
* `chatbot_clear_history`
    * **Description:** Clears the entire conversation history stored for the current channel. The bot will have no memory of previous conversations in this channel until new messages are added.
    * **Permissions:** Requires `chatbot_clear_history` permission.

### Debug Commands (Administrator Only)

These commands are primarily for troubleshooting and development.

* `debug_message_filter <test_message>` (Alias: `dbg_filter`)
    * **Description:** Tests a given message content string through the bot's internal message filtering and processing logic (`_process_discord_message_for_context` and `_is_valid_context_message`) to see if it would be included in conversation history and how its content would be cleaned/processed. Displays detailed debug steps.
    * **Arguments:** `<test_message>` - The string content you want to test.
    * **Example:** `!dbg_filter This is a test message with <@12345> and a link https://example.com and <:emote:67890>`
    * **Permissions:** Requires `administrator` permission.
* `debug_full_context [channel] [user_id]` (Alias: `dbg_full`)
    * **Description:** Exports the complete LLM context (system prompt, additional context, channel info, user info, pinned messages, prioritized conversation history, raw history data) as it would be prepared for a specific user interacting in a specific channel. Saves this detailed breakdown to a `.txt` file and uploads it.
    * **Arguments:**
        * `[channel]` - Optional. The channel to export context from. Defaults to the current channel.
        * `[user_id]` - Optional. The user ID for whom the context should be prioritized. Defaults to the command author's ID.
    * **Examples:**
        * `!dbg_full` - Export context for yourself in the current channel.
        * `!dbg_full #general` - Export context for yourself in the `#general` channel.
        * `!dbg_full 1234567890` - Export context for user ID `1234567890` in the current channel.
        * `!dbg_full #support 9876543210` - Export context for user ID `9876543210` in the `#support` channel.
    * **Permissions:** Requires `administrator` permission.

## Permissions

LLM and Chatbot commands use Mirrobot's internal permission system (`utils.permissions`). You will need to configure which roles/users have access using commands like `!perms grant` and `!perms revoke`. The command names used for permissions match the command names listed above (e.g., `chatbot_enable`, `llm_provider`).

Debug commands (`debug_message_filter`, `debug_full_context`) require the Discord `administrator` permission and cannot be controlled by the internal system.

## Running a Local LLM

If you choose the `local` provider, you will need to have an LLM server running on your machine or a reachable network location. Popular options include:

* **LM Studio:** A desktop application that allows you to download and run various LLMs locally. It provides an OpenAI-compatible API endpoint out-of-the-box, which Mirrobot can connect to using the `base_url`.
* **Ollama:** A command-line tool and server for running LLMs. It also provides an API. Mirrobot supports its `/api/tags` and `/v1/chat/completions` endpoints.

Ensure your chosen LLM server is running and configured to listen on the `base_url` specified in `data/llm_config.json` before attempting to use the local LLM features.

## Google AI Integration

To use Google AI models (`provider: google_ai`), you need to:

1. Obtain an API key from the [Google AI Studio](https://aistudio.google.com/).
2. Set the `GOOGLE_AI_API_KEY` environment variable on the system running the bot OR set the `google_ai_api_key` field in `data/llm_config.json` using the `!llm_set_api_key` command. Using an environment variable is the more secure method.
3. Set the `provider` in `data/llm_config.json` (or via `!llm_provider google_ai`) to `google_ai`.
4. Select a Google AI model using `!llm_select` (e.g., `!llm_select gemini-1.5-pro-latest`).

The bot will then communicate directly with Google's API. Note that using Google AI may incur costs depending on your usage and Google's pricing.
