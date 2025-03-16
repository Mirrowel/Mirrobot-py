# Pattern Management Commands

This document describes the commands for managing pattern matching and responses in Mirrobot.

## Pattern Matching Overview

Mirrobot uses regular expression patterns to match text from OCR-processed images and provide automated responses. The pattern system has two main components:

1. **Responses**: The text that gets sent when a pattern is matched
2. **Patterns**: Regular expressions that trigger a specific response

## Command Reference

### list_patterns
List all pattern responses for this server.

- **Usage**: `!list_patterns [verbosity]`
- **Arguments**: 
  - `verbosity` (optional): Detail level (1-3, default: 1)
- **Examples**: 
  - `!list_patterns` - Basic listing
  - `!list_patterns 3` - Detailed listing with all pattern information
- **Permissions**: Requires bot manager or specific command permission

### add_response
Add a new response with optional name and note.

- **Usage**: `!add_response <response> [name] [note]`
- **Arguments**: 
  - `response` (required): The response text
  - `name` (optional): Friendly name for the response
  - `note` (optional): Description or explanation
- **Example**: `!add_response "Please update your driver" "driver_update" "Standard response for outdated drivers"`
- **Permissions**: Requires bot manager or specific command permission

### remove_response
Remove a response and all its patterns.

- **Usage**: `!remove_response <response_id_or_name>`
- **Arguments**: 
  - `response_id_or_name` (required): ID number or name of the response
- **Examples**: 
  - `!remove_response 5`
  - `!remove_response driver_update`
- **Permissions**: Requires bot manager or specific command permission

### add_pattern_to_response
Add a pattern to an existing response.

- **Usage**: `!add_pattern_to_response <response_id_or_name> <pattern> [flags] [name] [url]`
- **Arguments**: 
  - `response_id_or_name` (required): ID number or name of the response
  - `pattern` (required): Regex pattern to match
  - `flags` (optional): Regex flags (e.g., "DOTALL|IGNORECASE")
  - `name` (optional): Friendly name for the pattern
  - `url` (optional): Screenshot URL
- **Examples**: 
  - `!add_pattern_to_response driver_update "driver version [0-9]+" "IGNORECASE" "old_driver_pattern"`
  - `!add_pattern_to_response 5 "error code 1234"`
- **Permissions**: Requires bot manager or specific command permission

### remove_pattern_from_response
Remove a pattern from a response.

- **Usage**: `!remove_pattern_from_response <response_id_or_name> <pattern_id>`
- **Arguments**: 
  - `response_id_or_name` (required): ID number or name of the response
  - `pattern_id` (required): ID number of the pattern to remove
- **Examples**: 
  - `!remove_pattern_from_response driver_update 2`
  - `!remove_pattern_from_response 5 3`
- **Permissions**: Requires bot manager or specific command permission

### view_response
View details of a specific response.

- **Usage**: `!view_response <response_id_or_name>`
- **Arguments**: 
  - `response_id_or_name` (required): ID number or name of the response
- **Examples**: 
  - `!view_response driver_update`
  - `!view_response 5`
- **Permissions**: Requires bot manager or specific command permission

### extract_text
Extract text from an image without matching patterns.

- **Usage**: `!extract_text [url_or_lang] [language]`
- **Arguments**: 
  - `url_or_lang` (optional): URL to an image or language code
  - `language` (optional): Language code for OCR (default: eng, options: eng, rus)
- **Examples**: 
  - `!extract_text https://example.com/image.jpg` - Extract text from URL using default language
  - `!extract_text https://example.com/image.jpg rus` - Extract text with Russian language
  - `!extract_text rus` - Extract text from attached image with Russian language
- **Note**: You can either attach an image or provide a URL
- **Permissions**: Requires bot manager or specific command permission

## Pattern Examples

Here are some examples of regex patterns that can be useful:

### Basic Text Matching
```
error code 1234
```
Matches text containing exactly "error code 1234"

### Case-Insensitive Matching (using IGNORECASE flag)
```
driver version [0-9]+\.[0-9]+
```
Matches text like "Driver Version 10.2" or "driver version 9.0"

### Multi-line Matching (using DOTALL flag)
```
error.*not found
```
Matches "error" and "not found" even if they're on different lines

### Complex Example
```
(exception|error|failed).*\b(0x[A-Fa-f0-9]+)\b
```
Matches error messages containing hexadecimal codes like "Exception occurred at 0x1A2B3C4D"
