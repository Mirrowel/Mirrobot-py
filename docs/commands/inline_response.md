# Inline Response Commands

The `inline` command group manages the Inline Response feature, which allows the bot to automatically reply to mentions in configured channels or threads. This feature provides a lightweight, conversational AI experience without needing to enable the full chatbot mode.

## Configuration Hierarchy

The inline response feature uses a hierarchical configuration system that allows for granular control over its behavior. Settings can be applied server-wide and then overridden for specific channels or threads.

-   **Server Settings (Base):** These are the default settings for the entire server. If a channel or thread does not have its own specific setting for an option, it will inherit the server's setting.
-   **Channel/Thread Settings (Override):** You can set specific configurations for individual channels or threads. These settings take precedence over the server settings.

**Key Behavior:**

-   For simple settings (like `toggle`, `trigger`, `model`, `context`), a channel-specific setting **overrides** the server setting.
-   For permission lists (`whitelist`, `blacklist`), a channel's list is **combined** with the server's list. For example, if the server whitelists `@RoleA` and a channel whitelists `@RoleB`, both roles will be able to use the feature in that specific channel.

---

## `!inline`

This is the base command for managing the Inline Response feature. Using it without a subcommand will display a comprehensive help embed listing all available subcommands and their functions.

-   **Usage:** `!inline`
-   **Permissions:** `manage_guild`

---

## `!inline status [target]`

Displays the current configuration for the Inline Response feature for a specific target. This command is crucial for understanding the effective settings in any given context.

The output shows the final, effective settings for the target and indicates the source of each setting:
-   `(Channel Specific)`: The setting is explicitly defined for this channel/thread.
-   `(Server Default)`: The setting is inherited from the server-wide configuration.
-   `(Bot Default)`: The setting is using the bot's hardcoded default because it hasn't been set at the server or channel level.
-   `(Channel & Server Combined)`: For permissions, this indicates that both server and channel lists are merged.

-   **Usage:** `!inline status [target]`
-   **Arguments:**
    -   `[target]` (Optional): The scope to view status for. Can be `server`, a `#channel` mention, or a channel/thread ID. Defaults to the current channel.
-   **Examples:**
    -   `!inline status`: Shows status for the current channel.
    -   `!inline status server`: Shows server-wide inline response settings.
    -   `!inline status #general`: Shows status for the `#general` channel.
-   **Permissions:** `manage_guild`

---

## `!inline toggle <on|off> [target]`

Enables or disables the Inline Response feature for a specific target.

-   **Usage:** `!inline toggle <on|off> [target]`
-   **Arguments:**
    -   `<on|off>` (Required): Specify `on` to enable or `off` to disable the feature.
    -   `[target]` (Optional): The scope to apply the toggle to. Defaults to the current channel.
-   **Examples:**
    -   `!inline toggle on`: Enables inline responses in the current channel.
    -   `!inline toggle off server`: Disables inline responses across the entire server.
-   **Permissions:** `manage_guild`

---

## `!inline trigger <start|anywhere> [target]`

Configures how the bot detects a mention to trigger an inline response.

-   **Usage:** `!inline trigger <start|anywhere> [target]`
-   **Arguments:**
    -   `<start|anywhere>` (Required):
        -   `start`: The bot will only respond if its mention is at the very beginning of the message.
        -   `anywhere`: The bot will respond if its mention appears anywhere in the message.
    -   `[target]` (Optional): The scope to apply the trigger setting to. Defaults to the current channel.
-   **Examples:**
    -   `!inline trigger start server`: Sets the server-wide trigger to only respond if the mention is at the start of a message.
    -   `!inline trigger anywhere #bots`: Overrides the server setting for the `#bots` channel to allow triggering anywhere in the message.
-   **Permissions:** `manage_guild`

---

## `!inline model <ask|think|chat> [target]`

Sets the LLM (Large Language Model) behavior type for inline responses.

-   **Usage:** `!inline model <ask|think|chat> [target]`
-   **Arguments:**
    -   `<ask|think|chat>` (Required): The LLM behavior type.
    -   `[target]` (Optional): The scope to apply the model setting to. Defaults to the current channel.
-   **Examples:**
    -   `!inline model ask`: Sets the model to `ask` mode in the current channel.
    -   `!inline model chat server`: Sets the server-wide default model to `chat` mode.
-   **Permissions:** `manage_guild`

---

## `!inline context <channel_msgs> <user_msgs> [target]`

Configures the number of recent messages the bot considers for context.

-   **Usage:** `!inline context <channel_messages> <user_messages> [target]`
-   **Arguments:**
    -   `<channel_messages>` (Required): Number of recent channel messages to include.
    -   `<user_messages>` (Required): Number of recent messages from the triggering user to include.
    -   `[target]` (Optional): The scope to apply the context settings to. Defaults to the current channel.
-   **Examples:**
    -   `!inline context 10 5`: Sets context to 10 channel messages and 5 user messages for the current channel.
    -   `!inline context 20 10 server`: Sets the server-wide default context.
-   **Permissions:** `manage_guild`

---

## Permissions Subcommands

### Permission Logic

The permission system uses a default-deny model with whitelists and blacklists. The rules are checked in this order:

1.  **Blacklist Check:** If a user or any of their roles are on the blacklist for the given context (channel or server), they are **always denied** access. This is the highest priority rule.
2.  **Whitelist Check:** If the user is not blacklisted, they must be on the whitelist to gain access.
    -   If the `@everyone` role is on the whitelist, all non-blacklisted users are granted access.
    -   Otherwise, the user must either be individually whitelisted or have a role that is on the whitelist.
3.  **Default Deny:** If a user is not blacklisted and not on the whitelist, access is **denied**.

### `!inline permissions whitelist <add|remove> <entity> [target]`

Manages the whitelist of users and roles allowed to trigger inline responses.

-   **Usage:** `!inline permissions whitelist <add|remove> <entity> [target]`
-   **Arguments:**
    -   `<add|remove>` (Required): The action to perform.
    -   `<entity>` (Required): The role or member to add/remove (name, ID, or mention). Use `everyone` for the `@everyone` role.
    -   `[target]` (Optional): The scope of the change. Defaults to the current channel.
-   **Examples:**
    -   `!inline permissions whitelist add everyone server`: Allows all non-blacklisted users to use the feature server-wide.
    -   `!inline permissions whitelist add "Cool People"`: Adds the 'Cool People' role to the whitelist for the current channel.
    -   `!inline permissions whitelist remove @SomeUser #general`: Removes a user from the whitelist specifically for the `#general` channel.
-   **Permissions:** `manage_guild`

### `!inline permissions blacklist <add|remove> <entity> [target]`

Manages the blacklist of users and roles explicitly denied from triggering inline responses.

-   **Usage:** `!inline permissions blacklist <add|remove> <entity> [target]`
-   **Arguments:**
    -   `<add|remove>` (Required): The action to perform.
    -   `<entity>` (Required): The role or member to add/remove (name, ID, or mention). You cannot blacklist `@everyone`.
    -   `[target]` (Optional): The scope of the change. Defaults to the current channel.
-   **Examples:**
    -   `!inline permissions blacklist add "Known Spammers" server`: Blacklists a role server-wide.
    -   `!inline permissions blacklist remove @AnnoyingUser`: Removes a user from the blacklist in the current channel.
-   **Permissions:** `manage_guild`