# Role Sharing Commands

Role sharing lets configured roles give configured target roles to other users. Assignments are recorded in `data/role_sharing.json`, logged to the bot log, and optionally sent to a configured Discord log channel.

The `Role Sharing` category can be disabled per server with `!command_lock category add "Role Sharing"` or `/command_lock category add`.

### `role_share give`
Shares a configured role with another member.

- **Usage:** `!role_share give <member> <role> [reason]`
- **Slash:** `/role_share give`
- **Rules:** Public command. The caller must have one of the applier roles configured for the target role.

### `role_share revoke`
Revokes a role that was assigned through `role_share give`.

- **Usage:** `!role_share revoke <member> <role> [reason]`
- **Slash:** `/role_share revoke`
- **Rules:** Public command. The original giver can revoke their own share. Server owner, server admins/manage-server users, and bot owner can revoke any bot-recorded active share.

### `role_share rules`
Lists configured role sharing rules for the current server.

- **Usage:** `!role_share rules`
- **Slash:** `/role_share rules`
- **Rules:** Public command.

### `role_share lookup`
Shows role shares recorded by this bot.

- **Usage:** `!role_share lookup <member>` or `!role_share lookup <role>`
- **Slash:** `/role_share lookup member:<member>` or `/role_share lookup role:<role>`
- **Permissions:** `has_command_permission`
- **Member View:** Shows roles the member received and roles the member gave out.
- **Role View:** Shows recipient/giver pairs for active shares of that role.

### `role_share allow`
Allows members with one role to share another role.

- **Usage:** `!role_share allow <applier_role> <target_role>`
- **Slash:** `/role_share allow`
- **Permissions:** `has_command_permission`

### `role_share disallow`
Removes one applier role from a target role's sharing rules.

- **Usage:** `!role_share disallow <applier_role> <target_role>`
- **Slash:** `/role_share disallow`
- **Permissions:** `has_command_permission`

### `role_share log_channel`
Sets the channel that receives role sharing audit logs.

- **Usage:** `!role_share log_channel <channel>`
- **Slash:** `/role_share log_channel`
- **Permissions:** `has_command_permission`
