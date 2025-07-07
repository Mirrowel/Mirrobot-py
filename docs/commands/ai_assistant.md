# AI Assistant Commands

The AI Assistant commands allow you to interact with the Large Language Model (LLM) and manage the chatbot features.

## LLM Commands

These commands control the LLM provider, model selection, and direct interaction with the AI.

### `ask`
Sends a question to the Large Language Model (LLM) and provides a direct response. This command is for quick questions and does not show the model's internal thinking process.

- **Usage:** `!ask <question>`
- **Arguments:**
    - `<question>` (Required): The question you want to ask the LLM.
- **Example:** `!ask What is the capital of France?`
- **Permissions:** `manage_messages`

### `think`
Sends a question to the LLM and can display the internal "thinking" steps of the model. This is useful for understanding how the model arrives at its conclusions.

- **Usage:** `!think [display_thinking] <question>`
- **Arguments:**
    - `[display_thinking]` (Optional): A boolean (`true` or `false`) that determines whether to show the model's thinking process. Defaults to `false`.
    - `<question>` (Required): The question you want to ask the LLM.
- **Example:** `!think true Explain how a combustion engine works.`
- **Permissions:** `manage_guild`

### `llm_status`
Displays the current LLM provider, connection status, and active model. This command is useful for diagnosing issues with the LLM integration.

- **Usage:** `!llm_status`
- **Permissions:** `manage_messages`

### `llm_models`
Lists available models from all configured providers with advanced filtering. This command helps you see which models are available for selection.

- **Usage:** `!llm_models [provider] [filter] [file]`
- **Arguments:**
    - `[provider]` (Optional): List models for a specific provider (e.g., `openai`, `gemini`).
    - `[filter]` (Optional): Apply a text filter to the model names. Use `all` to disable default filters.
    - `[file]` (Optional): Add the word `file` to the command to receive the output as a text file.
- **Examples:**
    - `!llm_models`: Shows models from all providers with default filters.
    - `!llm_models gemini`: Shows all available models from the Gemini provider.
    - `!llm_models gpt-4`: Shows models from all providers with "gpt-4" in their name.
    - `!llm_models openai all`: Shows all models from OpenAI, including those normally hidden by default filters.
    - `!llm_models file`: Outputs the full model list to a `model_list.txt` file.
- **Permissions:** `manage_messages`

### `llm_select`
Selects a preferred model to use for LLM requests for this server. You can set a default model or specific models for `chat`, `ask`, or `think` modes.

- **Usage:** `!llm_select [manual] [type] <model_name>`
- **Arguments:**
    - `[manual]` (Optional): If included, the model will be set regardless of whether it's currently available. Use with caution.
    - `[type]` (Optional): The type of model to set. Can be `default`, `chat`, `ask`, or `think`. Defaults to `default`.
    - `<model_name>` (Required): The full name of the model to select. You can get this from `!llm_models`.
- **Examples:**
    - `!llm_select gemma-3-27b-it`: Sets `gemma-3-27b-it` as the default model for all LLM interactions.
    - `!llm_select ask gpt-4`: Sets `gpt-4` as the model specifically for `!ask` commands.
    - `!llm_select manual my-custom-local-model`: Forces the bot to use `my-custom-local-model` even if it's not detected as available.
- **Permissions:** `manage_guild`

### `llm_safety` (Command Group)
This command group allows you to view or configure LLM content safety settings for the server or specific channels. These settings help control the types of content the LLM will generate or respond to.

- **Permissions:** `manage_guild`

#### `llm_safety view`
View the current safety settings for the server or a specific channel. The settings shown are the result of the channel > server > global hierarchy.

- **Usage:** `!llm_safety view [channel]`
- **Arguments:**
    - `[channel]` (Optional): A mention of the channel (e.g., `#general`) to view settings for. Defaults to the current channel.
- **Examples:**
    - `!llm_safety view`: Shows safety settings for the current channel.
    - `!llm_safety view #other-channel`: Shows safety settings for `#other-channel`.
- **Permissions:** `manage_guild`

#### `llm_safety set`
Set a safety setting for the server or a specific channel.

- **Usage:** `!llm_safety set <level> <category> <threshold>`
- **Arguments:**
    - `<level>` (Required): Specify `server` to apply to the entire server, or mention a channel (e.g., `#general`) to apply to that channel.
    - `<category>` (Required): The harm category to configure. Can be `all` (to apply to all categories), `harassment`, `hate_speech`, `sexually_explicit`, or `dangerous_content`.
    - `<threshold>` (Required): The blocking threshold. Options are:
        - `block_none`: Do not block content for this category.
        - `block_low_and_above`: Block content at low, medium, and high confidence levels.
        - `block_medium_and_above`: Block content at medium and high confidence levels.
        - `block_only_high`: Only block content at high confidence levels.
- **Examples:**
    - `!llm_safety set server all block_none`: Disables all safety filters for the entire server.
    - `!llm_safety set #general hate_speech block_medium_and_above`: Sets the hate speech filter for `#general` to block medium and high confidence content.
- **Permissions:** `manage_guild`

### `set_reasoning_budget`
Set the reasoning budget for a specific LLM model and mode. The reasoning budget controls how much "thinking" the model performs before generating a response, which can impact response quality and speed.

- **Usage:** `!set_reasoning_budget <model_name> <level> [mode]`
- **Arguments:**
    - `<model_name>` (Required): The name of the model to set the budget for (e.g., `gemma-3-27b-it`).
    - `<level>` (Required): The reasoning level. Options are:
        - `auto`: The model determines its own reasoning effort.
        - `none`: No explicit reasoning steps are shown.
        - `low`: Minimal reasoning steps.
        - `medium`: Moderate reasoning steps.
        - `high`: Detailed reasoning steps.
    - `[mode]` (Optional): The specific mode to apply the budget to. Can be `default`, `chat`, `ask`, or `think`. If not specified, it applies to the `default` mode for that model. Use `all` to apply to all modes.
- **Examples:**
    - `!set_reasoning_budget gemma-3-27b-it high think`: Sets the `gemma-3-27b-it` model to use `high` reasoning when used with the `!think` command.
    - `!set_reasoning_budget claude-3-opus-20240229 auto`: Sets the `claude-3-opus-20240229` model to `auto` reasoning for its default behavior.
    - `!set_reasoning_budget mistral-7b-instruct all none`: Disables reasoning for `mistral-7b-instruct` across all modes.
- **Permissions:** `manage_guild`

### `view_reasoning_budget`
View the configured reasoning budget for all LLM models on the server. This command provides an overview of how different models are set to handle their "thinking" process across various modes.

- **Usage:** `!view_reasoning_budget`
- **Permissions:** `manage_guild`

## Chatbot Commands

These commands manage the persistent chatbot feature in channels.

### `chatbot_enable`
Enables chatbot mode for the current channel. When enabled, the bot will maintain a conversation history and automatically respond to mentions and replies in that channel, acting as a persistent AI assistant.

- **Usage:** `!chatbot_enable`
- **Permissions:** `chatbot_enable`

### `chatbot_disable`
Disables chatbot mode for the current channel. This will stop the bot from automatically responding to mentions and replies in that channel and will clear its conversation history.

- **Usage:** `!chatbot_disable`
- **Permissions:** `chatbot_disable`

### `chatbot_status`
Shows the chatbot's current status and detailed configuration for the current channel. This includes whether it's enabled, its auto-response settings, context window, and conversation statistics.

- **Usage:** `!chatbot_status`
- **Permissions:** `chatbot_status`

### `chatbot_config`
Views or modifies the chatbot configuration for the current channel. This command allows fine-grained control over how the chatbot operates in a specific channel.

- **Usage:** `!chatbot_config [setting] [value]`
- **Arguments:**
    - `[setting]` (Optional): The name of the setting to view or modify. If no setting is provided, a list of all available settings and their descriptions will be displayed.
    - `[value]` (Optional): The new value for the specified setting.
- **Available Settings:**
    - `context_window <hours>`: How many hours to keep messages in context (1-168 hours).
    - `max_messages <number>`: Maximum number of messages to keep in context (10-200 messages).
    - `max_user_messages <number>`: Maximum number of messages from the requesting user to keep in context (5-50 messages).
    - `response_delay <seconds>`: Delay in seconds before the bot responds (0-10 seconds).
    - `max_response_length <chars>`: Maximum length of the bot's response in characters (100-4000 characters).
    - `auto_prune <true/false>`: Enable or disable automatic conversation pruning (`true` or `false`).
    - `prune_interval <hours>`: How often (in hours) the automatic conversation pruning runs (1-48 hours).
    - `mentions <true/false>`: Enable or disable automatic responses to mentions (`true` or `false`).
    - `replies <true/false>`: Enable or disable automatic responses to replies (`true` or `false`).
- **Examples:**
    - `!chatbot_config`: Displays all available settings and their current values.
    - `!chatbot_config context_window 48`: Sets the context window to 48 hours.
    - `!chatbot_config auto_prune true`: Enables automatic conversation pruning.
- **Permissions:** `chatbot_config`

### `chatbot_clear_history`
Clears the entire conversation history for the current channel and sets an indexing checkpoint. This means the chatbot will start a fresh conversation, and messages sent before this command will not be re-indexed for future context.

- **Usage:** `!chatbot_clear_history`
- **Permissions:** `chatbot_clear_history`

### `chatbot_remove_checkpoint`
Removes the indexing checkpoint for the current channel. This allows the bot to re-index messages from before the last `!chatbot_clear_history` command, effectively extending the conversation history further back in time.

- **Usage:** `!chatbot_remove_checkpoint`
- **Permissions:** `chatbot_clear_history`

## Indexing and Debug Commands

### `indexing_stats`
Displays statistics about the user and channel indexes for the current server. This provides insight into how many users and channels the chatbot has indexed and the total number of user messages tracked for context.

- **Usage:** `!indexing_stats`
- **Permissions:** `has_command_permission`

### `cleanup_users`
Manually cleans up stale users from the chatbot's index. This command removes user data for users who have not been active in the specified number of hours, helping to manage storage and privacy.

- **Usage:** `!cleanup_users [hours]`
- **Arguments:**
    - `[hours]` (Optional): The number of hours of inactivity after which a user's data will be considered "stale" and removed. Must be between 24 (1 day) and 8760 (1 year). Defaults to 168 hours (1 week).
- **Permissions:** `has_command_permission`

### `debug_message_filter`
Tests a given message through the bot's internal content filter system. This command is primarily for development and debugging purposes to understand how messages are processed and filtered before being sent to the LLM.

- **Usage:** `!debug_message_filter <test_message>`
- **Arguments:**
    - `<test_message>` (Required): The message content to test through the filter.
- **Alias:** `dbg_filter`
- **Permissions:** `administrator`

### `debug_full_context`
Exports the complete LLM context for a user in a specific channel to a file. This command is for development and debugging, providing a comprehensive view of all information the LLM considers when generating a response, including channel configuration, system prompts, server context, pinned messages, and conversation history.

- **Usage:** `!debug_full_context [channel] [user_id]`
- **Arguments:**
    - `[channel]` (Optional): The channel to export the context from. Defaults to the current channel.
    - `[user_id]` (Optional): The ID of the user whose context should be exported. Defaults to the command author's ID.
- **Alias:** `dbg_full`
- **Permissions:** `administrator`