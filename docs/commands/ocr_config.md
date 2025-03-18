# OCR Configuration Commands

This document describes the commands available for configuring the OCR functionality of Mirrobot.

## OCR Overview

Mirrobot uses Optical Character Recognition (OCR) to scan images posted in designated channels, extract text, and respond based on pattern matching. The following commands allow you to configure which channels are monitored and how responses are handled.

## Command Reference

### add_ocr_read_channel
Add a channel to the list of channels where the bot will scan images for OCR processing.

- **Usage**: `!add_ocr_read_channel <channel> [language]`
- **Arguments**: 
  - `channel` (required): The channel to add (can be a mention, ID, or name)
  - `language` (optional): Language code for OCR (default: eng, options: eng, rus)
- **Examples**: 
  - `!add_ocr_read_channel #support-channel`
  - `!add_ocr_read_channel 123456789012345678 rus`
  - `!add_ocr_read_channel support-channel eng`
- **Permissions**: Requires bot manager or specific command permission

### remove_ocr_read_channel
Remove a channel from the OCR reading list.

- **Usage**: `!remove_ocr_read_channel <channel>`
- **Arguments**: 
  - `channel` (required): The channel to remove (can be a mention, ID, or name)
- **Examples**: 
  - `!remove_ocr_read_channel #support-channel`
  - `!remove_ocr_read_channel support-channel`
- **Permissions**: Requires bot manager or specific command permission

### set_ocr_language
Set the OCR language for a channel.

- **Usage**: `!set_ocr_language <channel> <language>`
- **Arguments**: 
  - `channel` (required): The channel to configure (can be a mention, ID, or name)
  - `language` (required): Language code for OCR (options: eng, rus)
- **Examples**: 
  - `!set_ocr_language #russian-support rus`
  - `!set_ocr_language russian-support rus`
- **Permissions**: Requires bot manager or specific command permission

### add_ocr_response_channel
Add a channel where bot will post OCR analysis results.

- **Usage**: `!add_ocr_response_channel <channel> [language]`
- **Arguments**: 
  - `channel` (required): The channel to add (can be a mention, ID, or name)
  - `language` (optional): Language code for OCR (default: eng, options: eng, rus)
- **Examples**: 
  - `!add_ocr_response_channel #bot-responses rus`
  - `!add_ocr_response_channel bot-responses eng`
- **Permissions**: Requires bot manager or specific command permission

### remove_ocr_response_channel
Remove a channel from the OCR response list.

- **Usage**: `!remove_ocr_response_channel <channel>`
- **Arguments**: 
  - `channel` (required): The channel to remove (can be a mention, ID, or name)
- **Examples**: 
  - `!remove_ocr_response_channel #bot-responses`
  - `!remove_ocr_response_channel bot-responses`
- **Permissions**: Requires bot manager or specific command permission

### add_ocr_response_fallback
Add a fallback channel for OCR responses if no regular response channel is available.

- **Usage**: `!add_ocr_response_fallback <channel>`
- **Arguments**: 
  - `channel` (required): The channel to add (can be a mention, ID, or name)
- **Examples**: 
  - `!add_ocr_response_fallback #general-bot`
  - `!add_ocr_response_fallback general-bot`
- **Permissions**: Requires bot manager or specific command permission

### remove_ocr_response_fallback
Remove a channel from the OCR response fallback list.

- **Usage**: `!remove_ocr_response_fallback <channel>`
- **Arguments**: 
  - `channel` (required): The channel to remove (can be a mention, ID, or name)
- **Examples**: 
  - `!remove_ocr_response_fallback #general-bot`
  - `!remove_ocr_response_fallback general-bot`
- **Permissions**: Requires bot manager or specific command permission

## OCR Channel Flow

The OCR process follows this flow when determining where to send responses:

1. Images are scanned in channels added with `add_ocr_read_channel`
2. If a matching pattern is found, the response is sent to:
   - A language-matching channel from `add_ocr_response_channel` if available
   - The first available response channel if no language match
   - A fallback channel from `add_ocr_response_fallback` if no response channel
   - As a direct reply to the original message if no channels are configured
