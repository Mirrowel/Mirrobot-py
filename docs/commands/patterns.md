# Pattern Management Commands

These commands are for creating, managing, and testing response patterns for the OCR system.
(TO BE DEPRECATED IN FAVOR OF LLM-BASED OCR)

### `list_patterns`
Lists all configured response patterns for the current server. This command helps you review existing patterns and their associated responses.

- **Usage:** `!list_patterns [verbosity]`
- **Arguments:**
    - `[verbosity]` (Optional): Controls the level of detail in the output:
        - `1` (Default): Shows response IDs and names.
        - `2`: Includes response text and pattern names.
        - `3`: Shows full details, including response text, pattern regex, flags, and associated URLs.
- **Examples:**
    - `!list_patterns`: Lists all responses with their IDs and names.
    - `!list_patterns 2`: Lists responses with their text and pattern names.
    - `!list_patterns 3`: Provides a detailed list of all responses and their patterns.
- **Permissions:** `has_command_permission`

### `add_response`
Adds a new response template to the server's pattern configuration. This response can then be associated with one or more regex patterns.

- **Usage:** `!add_response "response text" [name] [note]`
- **Arguments:**
    - `"response text"` (Required): The text the bot will send as a response when a linked pattern is matched. Enclose in quotes.
    - `[name]` (Optional): A friendly, unique name for this response. If not provided, a name will be generated. Enclose in quotes if it contains spaces.
    - `[note]` (Optional): A descriptive note or explanation for this response. Enclose in quotes if it contains spaces.
- **Examples:**
    - `!add_response "Please check your internet connection." "Connection Issue"`
    - `!add_response "Contact support for further assistance."`
- **Permissions:** `has_command_permission`

### `remove_response`
Removes an existing response template and all regex patterns associated with it from the server's configuration.

- **Usage:** `!remove_response <response_id_or_name>`
- **Arguments:**
    - `<response_id_or_name>` (Required): The ID number or the friendly name of the response to remove.
- **Examples:**
    - `!remove_response 5`: Removes the response with ID 5.
    - `!remove_response "Connection Issue"`: Removes the response named "Connection Issue".
- **Permissions:** `has_command_permission`

### `add_pattern_to_response`
Adds a new regex pattern to an existing response template. When this pattern is matched in OCR-extracted text, the associated response will be triggered.

- **Usage:** `!add_pattern_to_response <response_id_or_name> "pattern" [flags] [name] [url]`
- **Arguments:**
    - `<response_id_or_name>` (Required): The ID number or the friendly name of the response to add the pattern to.
    - `"pattern"` (Required): The regular expression string to match. Enclose in quotes.
    - `[flags]` (Optional): Regex flags to modify pattern matching behavior (e.g., `DOTALL`, `IGNORECASE`, `MULTILINE`). Multiple flags can be combined with `|` (e.g., `"DOTALL|IGNORECASE"`).
    - `[name]` (Optional): A friendly, unique name for this pattern. Enclose in quotes if it contains spaces.
    - `[url]` (Optional): A URL to a screenshot or image that demonstrates this pattern.
- **Examples:**
    - `!add_pattern_to_response 5 ".*error.*" "DOTALL|IGNORECASE"`: Adds a case-insensitive pattern matching "error" anywhere, to response ID 5.
    - `!add_pattern_to_response "Connection Issue" "Failed to connect to server"`: Adds a literal pattern to the "Connection Issue" response.
- **Permissions:** `has_command_permission`

### `remove_pattern_from_response`
Removes a specific regex pattern from an existing response template. The response itself will remain, but it will no longer be triggered by this particular pattern.

- **Usage:** `!remove_pattern_from_response <response_id_or_name> <pattern_id>`
- **Arguments:**
    - `<response_id_or_name>` (Required): The ID number or the friendly name of the response from which to remove the pattern.
    - `<pattern_id>` (Required): The ID number of the pattern to remove. You can find this ID using `!view_response`.
- **Examples:**
    - `!remove_pattern_from_response 5 2`: Removes pattern with ID 2 from response ID 5.
    - `!remove_pattern_from_response "Connection Issue" 1`: Removes pattern with ID 1 from the "Connection Issue" response.
- **Permissions:** `has_command_permission`

### `view_response`
Views the full details of a specific response template, including its ID, name, response text, associated patterns (with their regex, flags, and names), and any linked URLs.

- **Usage:** `!view_response <response_id_or_name>`
- **Arguments:**
    - `<response_id_or_name>` (Required): The ID number or the friendly name of the response to view.
- **Examples:**
    - `!view_response 5`: Displays details for the response with ID 5.
    - `!view_response "Connection Issue"`: Displays details for the "Connection Issue" response.
- **Permissions:** `has_command_permission`

### `extract_text`
Extracts text from an image (either attached to the message or provided via URL) using OCR, and displays the extracted text. This command is useful for testing OCR capabilities and verifying text extraction without triggering any configured patterns.

- **Usage:** `!extract_text [url_or_language] [language]`
- **Arguments:**
    - `[url_or_language]` (Optional): Can be a URL to an image, or a language code if no URL is provided and an image is attached.
    - `[language]` (Optional): The language code for OCR processing. Supported options are `eng` (English) and `rus` (Russian). Defaults to `eng`.
- **Examples:**
    - `!extract_text` (with an image attached): Extracts text from the attached image using the default language.
    - `!extract_text https://example.com/image.jpg`: Extracts text from the image at the provided URL.
    - `!extract_text rus` (with an image attached): Extracts text from the attached image using Russian OCR.
    - `!extract_text https://example.com/image.jpg rus`: Extracts text from the image at the URL using Russian OCR.
- **Permissions:** `has_command_permission`
