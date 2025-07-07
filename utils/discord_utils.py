import discord
from typing import Union

from utils.logging_setup import get_logger

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