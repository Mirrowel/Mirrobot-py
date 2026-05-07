import discord
from typing import Union, AsyncGenerator, List
import time
import json
import re
import asyncio

from utils.logging_setup import get_logger
from utils.inline_response import split_message
from utils.chatbot.manager import chatbot_manager

logger = get_logger()


def normalize_reasoning_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "thinking":
                parts.append(item.get("thinking", ""))
        return "".join(parts)
    return ""


async def reply_or_send(
    target: Union[discord.Message, discord.ext.commands.Context],
    content: str = None,
    **kwargs,
) -> discord.Message:  # Add return type hint
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
    for p in [".", "!", "?"]:
        last_sentence_end = max(last_sentence_end, truncated_text.rfind(p))

    # If we found a sentence end, truncate there and add ellipsis
    if last_sentence_end != -1:
        return truncated_text[: last_sentence_end + 1] + "..."

    # Fallback: find the last space to avoid cutting a word
    last_space = truncated_text.rfind(" ")
    if last_space != -1:
        return truncated_text[:last_space] + "..."

    # Final fallback: hard truncate
    return text[: max_length - 3] + "..."


_SUMMARY_REGEX = re.compile(r"^\s*\*\*(.*?)\*\*\s*$", re.MULTILINE)


def _extract_last_summary(reasoning_text: str) -> str:
    matches = _SUMMARY_REGEX.findall(reasoning_text)
    return matches[-1].strip() if matches else ""


def _should_show_summaries(model_name: str) -> bool:
    return any(m in model_name for m in ("gemini-2.5", "gemini-3"))


async def _update_discord_messages(
    message_to_reply_to: discord.Message,
    sent_messages: List[discord.Message],
    content: str,
    max_messages: int,
) -> List[discord.Message]:
    message_chunks = split_message(content)

    if len(message_chunks) > max_messages:
        message_chunks = message_chunks[:max_messages]
        message_chunks[-1] = truncate_to_last_sentence(message_chunks[-1])

    for i, chunk_content in enumerate(message_chunks):
        if i < len(sent_messages):
            if sent_messages[i].content != chunk_content:
                try:
                    await sent_messages[i].edit(content=chunk_content)
                    sent_messages[i].content = chunk_content
                except discord.errors.NotFound:
                    logger.warning(
                        f"Message {sent_messages[i].id} to edit was deleted."
                    )
                    try:
                        new_msg = await reply_or_send(
                            message_to_reply_to, chunk_content
                        )
                        sent_messages[i] = new_msg
                    except Exception as e:
                        logger.error(f"Failed to resend deleted message: {e}")
                        return []
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        logger.warning("Hit rate limit, slowing down updates.")
                        return []
                    logger.error(f"Failed to edit message: {e}")
                    return []
        else:
            try:
                new_message = await reply_or_send(
                    message_to_reply_to, chunk_content
                )
                sent_messages.append(new_message)
            except Exception as e:
                logger.error(f"Failed to send new message part: {e}")
                return []

    return sent_messages


async def handle_streaming_text_response(
    bot,
    message_to_reply_to: discord.Message,
    stream_generator: AsyncGenerator,
    model_name: str,
    llm_cog,
    initial_message: discord.Message = None,
    max_messages: int = 1,
) -> List[discord.Message]:
    """
    Processes a streaming LLM response and updates a series of plain-text Discord messages.
    Reasoning and answer buffers are kept strictly separate - reasoning is never formatted
    or sent as content. Only the answer buffer is formatted and displayed.
    Returns the list of messages that were sent or edited.
    """
    sent_messages: List[discord.Message] = []
    if initial_message:
        sent_messages.append(initial_message)
    else:
        initial_message = await reply_or_send(
            message_to_reply_to, f"Thinking with `{model_name}`..."
        )
        sent_messages.append(initial_message)

    answer_buffer = ""
    reasoning_buffer = ""
    last_update_time = time.time()
    last_summary = ""
    stream_chunks = []
    stream_error = False

    show_summaries = _should_show_summaries(model_name)
    guild = message_to_reply_to.guild if message_to_reply_to.guild else None

    try:
        async for chunk in stream_generator:
            try:
                if isinstance(chunk, bytes):
                    chunk_str = chunk.decode("utf-8")
                else:
                    chunk_str = str(chunk)

                if chunk_str.startswith("data: "):
                    chunk_str = chunk_str[6:]

                if not chunk_str.strip() or chunk_str.strip() == "[DONE]":
                    continue

                data = json.loads(chunk_str)
                stream_chunks.append(data)

                if "error" in data:
                    error_message = data.get("error", "Unknown error from proxy")
                    if isinstance(error_message, dict):
                        error_message = error_message.get("message", str(error_message))
                    logger.error(f"Stream error from provider: {error_message}")
                    await sent_messages[0].edit(
                        content=f"An error occurred: {error_message}"
                    )
                    stream_error = True
                    return []

                delta = data.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    answer_buffer += delta["content"]
                if delta.get("reasoning_content"):
                    reasoning_buffer += normalize_reasoning_content(
                        delta["reasoning_content"]
                    )

            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON chunk, skipping: {chunk_str[:100]}")
                continue
            except Exception as e:
                logger.error(f"Error processing stream chunk: {e}", exc_info=True)
                await sent_messages[0].edit(
                    content=f"An unexpected error occurred: {e}"
                )
                stream_error = True
                return []

            current_time = time.time()
            if current_time - last_update_time < 1.0:
                continue
            last_update_time = current_time

            if not answer_buffer.strip():
                if reasoning_buffer.strip():
                    if show_summaries:
                        summary = _extract_last_summary(reasoning_buffer)
                        status = f"Thinking... ({summary})" if summary else "Thinking..."
                    else:
                        status = "Thinking..."
                    try:
                        if sent_messages[0].content != status:
                            await sent_messages[0].edit(content=status)
                    except discord.errors.HTTPException as e:
                        logger.warning(f"Failed to update thinking status: {e}")
            else:
                formatted = await chatbot_manager.formatter.format_llm_output_for_discord(
                    answer_buffer, guild,
                )
                if not formatted.strip():
                    continue

                result = await _update_discord_messages(
                    message_to_reply_to, sent_messages, formatted, max_messages,
                )
                if not result:
                    stream_error = True
                    return []

    finally:
        if "stream_generator" in locals() and hasattr(stream_generator, "aclose"):
            await stream_generator.aclose()

        llm_cog._save_debug_stream_response_raw(stream_chunks, model_name.split("/")[0])
        llm_cog._save_debug_stream_response_assembled(
            stream_chunks, model_name.split("/")[0]
        )

        if stream_error:
            return []

        if not answer_buffer.strip():
            cleaned_content = "No response generated."
        else:
            cleaned_content = await chatbot_manager.formatter.format_llm_output_for_discord(
                answer_buffer, guild,
            )

        message_chunks = split_message(cleaned_content)

        if len(message_chunks) > max_messages:
            message_chunks = message_chunks[:max_messages]
            message_chunks[-1] = truncate_to_last_sentence(message_chunks[-1])

        for i, chunk_content in enumerate(message_chunks):
            if i < len(sent_messages):
                if sent_messages[i].content != chunk_content:
                    try:
                        await sent_messages[i].edit(content=chunk_content)
                        sent_messages[i].content = chunk_content
                    except discord.errors.NotFound:
                        logger.warning(
                            f"Message {sent_messages[i].id} for final update was deleted."
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send final update for message {i}: {e}"
                        )
            else:
                try:
                    new_message = await reply_or_send(
                        message_to_reply_to, chunk_content
                    )
                    sent_messages.append(new_message)
                except Exception as e:
                    logger.error(
                        f"Failed to send new message part in final update: {e}"
                    )

        if len(sent_messages) > len(message_chunks):
            for i in range(len(message_chunks), len(sent_messages)):
                try:
                    await sent_messages[i].delete()
                except discord.errors.NotFound:
                    pass
                except Exception as e:
                    logger.error(
                        f"Failed to delete extra message {sent_messages[i].id}: {e}"
                    )
            sent_messages = sent_messages[: len(message_chunks)]

        return sent_messages
