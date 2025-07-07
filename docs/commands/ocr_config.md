# OCR Configuration Commands

These commands are for setting up and managing OCR (Optical Character Recognition) functionality.
(TO BE DEPRECATED IN FAVOR OF LLM-BASED OCR)

### `add_ocr_read_channel`
Adds a specified channel to the list of channels where the bot will automatically scan images for OCR (Optical Character Recognition) processing. When an image is posted in a read channel, the bot will attempt to extract text from it.

- **Usage:** `!add_ocr_read_channel <channel> [language]`
- **Arguments:**
    - `<channel>` (Required): The channel to add (mention, ID, or name).
    - `[language]` (Optional): The language code for OCR processing in this channel. Supported options are `eng` (English) and `rus` (Russian). Defaults to `eng`.
- **Example:** `!add_ocr_read_channel #screenshots rus`
- **Permissions:** `has_command_permission`

### `remove_ocr_read_channel`
Removes a specified channel from the list of channels where the bot performs OCR processing on images. The bot will no longer scan images posted in this channel.

- **Usage:** `!remove_ocr_read_channel <channel>`
- **Arguments:**
    - `<channel>` (Required): The channel to remove (mention, ID, or name).
- **Example:** `!remove_ocr_read_channel #screenshots`
- **Permissions:** `has_command_permission`

### `set_ocr_language`
Sets the OCR language for a specific channel that is configured for OCR reading. This allows the bot to accurately extract text from images in different languages.

- **Usage:** `!set_ocr_language <channel> <language>`
- **Arguments:**
    - `<channel>` (Required): The channel to configure (mention, ID, or name).
    - `<language>` (Required): The language code for OCR processing. Supported options are `eng` (English) and `rus` (Russian).
- **Example:** `!set_ocr_language #russian-support rus`
- **Permissions:** `has_command_permission`

### `add_ocr_response_channel`
Adds a specified channel to the list of channels where the bot will post the results of its OCR analysis. When text is successfully extracted from an image in an OCR read channel, the bot will send the extracted text to a configured response channel.

- **Usage:** `!add_ocr_response_channel <channel> [language]`
- **Arguments:**
    - `<channel>` (Required): The channel to add (mention, ID, or name).
    - `[language]` (Optional): The language associated with this response channel. This is useful if you have different response channels for different OCR languages. Supported options are `eng` (English) and `rus` (Russian). Defaults to `eng`.
- **Example:** `!add_ocr_response_channel #ocr-results rus`
- **Permissions:** `has_command_permission`

### `remove_ocr_response_channel`
Removes a specified channel from the list of channels where the bot posts OCR analysis results. The bot will no longer send OCR output to this channel.

- **Usage:** `!remove_ocr_response_channel <channel>`
- **Arguments:**
    - `<channel>` (Required): The channel to remove (mention, ID, or name).
- **Example:** `!remove_ocr_response_channel #ocr-results`
- **Permissions:** `has_command_permission`

### `add_ocr_response_fallback`
Adds a specified channel as a fallback for OCR responses. If the bot cannot post OCR analysis results to the designated `ocr_response_channel` (e.g., due to permissions or channel deletion), it will attempt to send the results to this fallback channel instead.

- **Usage:** `!add_ocr_response_fallback <channel>`
- **Arguments:**
    - `<channel>` (Required): The channel to set as the fallback (mention, ID, or name).
- **Example:** `!add_ocr_response_fallback #bot-logs`
- **Permissions:** `has_command_permission`

### `remove_ocr_response_fallback`
Removes a specified channel from the OCR response fallback list. The bot will no longer attempt to send OCR analysis results to this channel if the primary response channel is unavailable.

- **Usage:** `!remove_ocr_response_fallback <channel>`
- **Arguments:**
    - `<channel>` (Required): The channel to remove (mention, ID, or name).
- **Example:** `!remove_ocr_response_fallback #bot-logs`
- **Permissions:** `has_command_permission`
