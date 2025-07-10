import discord
from typing import Union, AsyncGenerator, List
import time
import json
import asyncio

from utils.logging_setup import get_logger
from utils.inline_response import split_message
from utils.chatbot.manager import chatbot_manager

logger = get_logger()

async def reply_or_send(
    target: Union[discord.Message, discord.ext.commands.Context],
    content: str = None,
    **kwargs,
) -> discord.Message: # Add return type hint
    """
    Safely replies to a message or context, falling back to sending a message
    in the same channel if the original message is deleted.
    Returns the message that was sent.

    Args:
        target: The discord.Message or commands.Context object to reply to.
        content: The text content of the message.
        **kwargs: Other arguments to pass to send/reply (e.g., embed, view).
    
    Returns:
        The discord.Message object that was sent.
    """
    sent_message = None
    try:
        sent_message = await target.reply(content, **kwargs)
    except discord.errors.HTTPException as e:
        # Error code 10008 is "Unknown Message"
        if e.code == 10008:
            logger.warning(
                f"Failed to reply to message {target.message.id if isinstance(target, discord.ext.commands.Context) else target.id}. It was likely deleted. Sending to channel instead."
            )
            channel = target.channel
            sent_message = await channel.send(content, **kwargs)
        else:
            # Re-raise other HTTP exceptions
            raise
    return sent_message

def truncate_to_last_sentence(text: str, max_length: int = 2000) -> str:
    """Truncates text to the last full sentence within the max_length."""
    if len(text) <= max_length:
        return text
    
    # Truncate to max_length to work with a smaller string
    truncated_text = text[:max_length]
    
    # Find the last sentence-ending punctuation
    last_sentence_end = -1
    for p in ['.', '!', '?']:
        last_sentence_end = max(last_sentence_end, truncated_text.rfind(p))
    
    # If we found a sentence end, truncate there and add ellipsis
    if last_sentence_end != -1:
        return truncated_text[:last_sentence_end+1] + "..."
    
    # Fallback: find the last space to avoid cutting a word
    last_space = truncated_text.rfind(' ')
    if last_space != -1:
        return truncated_text[:last_space] + "..."
        
    # Final fallback: hard truncate
    return text[:max_length-3] + "..."

async def handle_streaming_text_response(bot, message_to_reply_to: discord.Message, stream_generator: AsyncGenerator, model_name: str, llm_cog, initial_message: discord.Message = None, max_messages: int = 1):
    """
    Processes a streaming LLM response and updates a series of plain-text Discord messages.
    Handles message splitting for long responses and enforces a message limit.
    """
    # 1. Initial Message
    sent_messages: List[discord.Message] = []
    if initial_message:
        sent_messages.append(initial_message)
    else:
        initial_message = await reply_or_send(message_to_reply_to, f"Thinking with `{model_name}`...")
        sent_messages.append(initial_message)

    # 2. Stream Processing Loop
    response_buffer = ""
    last_update_time = time.time()
    
    try:
        async for chunk in stream_generator:
            try:
                if isinstance(chunk, bytes):
                    chunk_str = chunk.decode('utf-8')
                else:
                    chunk_str = str(chunk)

                if chunk_str.startswith('data: '):
                    chunk_str = chunk_str[6:]
                
                if not chunk_str.strip() or chunk_str.strip() == '[DONE]':
                    continue
                
                data = json.loads(chunk_str)

                if "error" in data:
                    error_message = data.get("error", "Unknown error from proxy")
                    await sent_messages[0].edit(content=f"An error occurred: {error_message}")
                    return

                delta = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                if delta:
                    response_buffer += delta

            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON chunk, skipping: {chunk_str[:100]}")
                continue
            except Exception as e:
                logger.error(f"Error processing stream chunk: {e}", exc_info=True)
                await sent_messages[0].edit(content=f"An unexpected error occurred: {e}")
                return

            # 3. Rate-Limited Updates & Message Splitting
            current_time = time.time()
            if current_time - last_update_time > 2.0:
                last_update_time = current_time
                
                # Format and split the content
                formatted_content = await chatbot_manager.formatter.format_llm_output_for_discord(response_buffer, message_to_reply_to.guild.id if message_to_reply_to.guild else None)
                cleaned_content, _, is_thinking_only = llm_cog.strip_thinking_tokens(formatted_content)
                
                # If we only have thinking content and no final answer yet, wait for more chunks.
                if is_thinking_only:
                    continue

                if not cleaned_content.strip():
                    continue

                message_chunks = split_message(cleaned_content)

                # Enforce the message limit
                if len(message_chunks) > max_messages:
                    message_chunks = message_chunks[:max_messages]
                    # Truncate the last chunk to ensure it ends nicely
                    message_chunks[-1] = truncate_to_last_sentence(message_chunks[-1])


                # Update existing messages and send new ones if needed
                for i, chunk_content in enumerate(message_chunks):
                    if i < len(sent_messages):
                        # Edit existing message
                        if sent_messages[i].content != chunk_content:
                            try:
                                await sent_messages[i].edit(content=chunk_content)
                            except discord.errors.NotFound:
                                logger.warning(f"Message {sent_messages[i].id} to edit was deleted.")
                                # Attempt to resend
                                try:
                                    new_msg = await reply_or_send(message_to_reply_to, chunk_content)
                                    sent_messages[i] = new_msg
                                except Exception as e:
                                    logger.error(f"Failed to resend deleted message: {e}")
                                    return # Stop if we can't maintain the message chain
                            except discord.errors.HTTPException as e:
                                if e.status == 429:
                                    logger.warning("Hit rate limit, slowing down updates.")
                                    last_update_time = current_time + 5 # Back off more
                                else:
                                    logger.error(f"Failed to edit message: {e}")
                                    return
                    else:
                        # Send new message
                        try:
                            new_message = await reply_or_send(message_to_reply_to, chunk_content)
                            sent_messages.append(new_message)
                        except Exception as e:
                            logger.error(f"Failed to send new message part: {e}")
                            return # Stop if we can't send a part

    finally:
        # 4. Final Update
        await asyncio.sleep(1) # Short delay to ensure stream is fully closed
        formatted_content = await chatbot_manager.formatter.format_llm_output_for_discord(response_buffer, message_to_reply_to.guild.id if message_to_reply_to.guild else None)
        cleaned_content, _, _ = llm_cog.strip_thinking_tokens(formatted_content)
        
        if not cleaned_content.strip():
             cleaned_content = "No response generated."

        message_chunks = split_message(cleaned_content)

        # Enforce the message limit for the final update
        if len(message_chunks) > max_messages:
            message_chunks = message_chunks[:max_messages]
            # Truncate the last chunk to ensure it ends nicely
            message_chunks[-1] = truncate_to_last_sentence(message_chunks[-1])

        for i, chunk_content in enumerate(message_chunks):
            if i < len(sent_messages):
                if sent_messages[i].content != chunk_content:
                    try:
                        await sent_messages[i].edit(content=chunk_content)
                    except discord.errors.NotFound:
                        logger.warning(f"Message {sent_messages[i].id} for final update was deleted.")
                    except Exception as e:
                        logger.error(f"Failed to send final update for message {i}: {e}")
            else:
                try:
                    new_message = await reply_or_send(message_to_reply_to, chunk_content)
                    sent_messages.append(new_message)
                except Exception as e:
                    logger.error(f"Failed to send new message part in final update: {e}")

        # Clean up any extra messages if the final response is shorter
        if len(sent_messages) > len(message_chunks):
            for i in range(len(message_chunks), len(sent_messages)):
                try:
                    await sent_messages[i].delete()
                except discord.errors.NotFound:
                    pass # Already deleted, which is fine
                except Exception as e:
                    logger.error(f"Failed to delete extra message {sent_messages[i].id}: {e}")
            sent_messages = sent_messages[:len(message_chunks)]