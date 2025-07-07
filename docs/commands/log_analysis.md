# Log Analysis Commands

These commands are used to analyze game log files for errors and manage log-related patterns.

### `analyze_logs`
Manually triggers the log analysis process on one or more attached log files. The bot will scan the files for known error patterns and provide relevant responses.

- **Usage:** `!analyze_logs` (with one or more log files attached to the message)
- **Permissions:** `has_command_permission`

### `log_analysis_stats`
Displays statistics related to the bot's log analysis performance, including the number of files analyzed, patterns matched, and any errors encountered during the process.

- **Usage:** `!log_analysis_stats`
- **Permissions:** `has_command_permission`

### `create_log_pattern`
Creates a new log pattern and associates it with a response. You provide an example log file, the desired response text, and a name for the pattern. The bot will extract a pattern from the attached log file.

- **Usage:** `!create_log_pattern "response text" "pattern_name"` (with a log file attached to the message)
- **Arguments:**
    - `"response text"` (Required): The text the bot should respond with when this pattern is detected in a log file. Enclose in quotes.
    - `"pattern_name"` (Required): A unique name for this log pattern. Enclose in quotes.
- **Permissions:** `has_command_permission`