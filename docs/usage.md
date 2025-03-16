# Mirrobot Usage Guide

This document provides examples and guidance for using Mirrobot effectively in your server.

## Initial Setup

After adding Mirrobot to your server, follow these steps for basic setup:

1. **Set Up OCR Channels**:
   ```
   !add_ocr_read_channel #support-channel
   !add_ocr_response_channel #bot-responses
   ```

2. **Create Bot Manager Roles**:
   ```
   !add_bot_manager @Support-Team
   ```

3. **Add Responses for Common Issues**:
   ```
   !add_response "Please update your graphics driver to the latest version." "driver_update" "Standard response for outdated drivers"
   ```

4. **Add Patterns to Your Responses**:
   ```
   !add_pattern_to_response driver_update "driver version [0-9]+\.[0-9]+" "IGNORECASE" "old_driver_pattern"
   ```

## OCR Workflow

### How OCR Processing Works

1. A user posts an image in a monitored channel
2. Mirrobot processes the image and extracts text
3. The text is matched against patterns in your pattern database
4. If a match is found, the corresponding response is sent

### Example Usage Scenarios

#### Technical Support

In a technical support channel, users often post error messages. Configure Mirrobot to:

1. Monitor the #tech-support channel:
   ```
   !add_ocr_read_channel #tech-support
   ```

2. Create responses for common errors:
   ```
   !add_response "This error occurs when your game settings are too high for your hardware. Try lowering your graphics settings." "graphics_settings" "High settings error"
   ```

3. Add patterns to match those errors:
   ```
   !add_pattern_to_response graphics_settings ".*memory allocation failed.*" "DOTALL|IGNORECASE" "memory_error"
   ```

4. Test the pattern with an example image:
   ```
   !extract_text https://example.com/error_screenshot.jpg
   ```

#### Multiple Language Support

For servers serving multiple language communities:

1. Set up language-specific channels:
   ```
   !add_ocr_read_channel #english-support eng
   !add_ocr_read_channel #russian-support rus
   ```

2. Create language-specific response channels:
   ```
   !add_ocr_response_channel #english-bot-responses eng
   !add_ocr_response_channel #russian-bot-responses rus
   ```

## Advanced Configuration

### Regex Pattern Tips

- **Be Specific**: Make patterns as specific as possible to avoid false positives
- **Use Flags**: 
  - `IGNORECASE` for case-insensitive matching
  - `DOTALL` to match across line breaks
  - `MULTILINE` for working with multi-line text
- **Test Thoroughly**: Use `!extract_text` to verify OCR accuracy before creating patterns

### Response Organization

Use a systematic naming convention for your responses:
- Use prefixes like `err_`, `warn_`, `info_` for different types of responses
- Number related responses (e.g., `driver_01`, `driver_02`)
- Include brief but descriptive notes for each response

## Command Examples by Task

### Managing OCR Channels

```
# Add an English OCR channel
!add_ocr_read_channel #bug-reports eng

# Add a Russian OCR channel
!add_ocr_read_channel #russian-support rus

# Change language of an existing channel
!set_ocr_language #bug-reports rus

# Remove a channel from OCR processing
!remove_ocr_read_channel #bug-reports
```

### Managing Patterns

```
# List all patterns with basic details
!list_patterns 1

# List all patterns with full details
!list_patterns 3

# View a specific response
!view_response driver_update

# Remove a pattern from a response
!remove_pattern_from_response driver_update 2
```

### Managing Permissions

```
# Allow a role to add OCR channels
!add_command_role @Moderators add_ocr_read_channel

# Remove a permission
!remove_command_role @Moderators add_ocr_read_channel

# Make a role bot manager
!add_bot_manager @TechSupport

# View all permissions
!server_info
```

## Troubleshooting

### Common Issues

#### OCR Not Detecting Text

- **Possible causes**:
  - Image resolution too low
  - Text too blurry or small
  - Unusual font or stylized text
  - Language mismatch

- **Solutions**:
  - Ask users to provide clearer screenshots
  - Use the correct language setting for the channel
  - Try multiple patterns to account for OCR variations

#### Pattern Not Matching

- **Possible causes**:
  - OCR misreading characters
  - Pattern too specific
  - Unexpected formatting in the text

- **Solutions**:
  - Use `!extract_text` to see how Mirrobot perceives the image
  - Make patterns more general with wildcards
  - Add multiple patterns for the same response

#### Permission Issues

- **Possible causes**:
  - Incorrect role hierarchy
  - Missing permissions

- **Solutions**:
  - Check server_info for current permissions
  - Ensure roles are assigned correctly
  - Try using bot mention as prefix: `@Mirrobot command`
