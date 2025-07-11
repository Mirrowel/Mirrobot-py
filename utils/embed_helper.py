"""
Embed helper module for Mirrobot.

This module provides utilities for creating and managing Discord embed messages,
making it easier to create consistent, well-formatted responses.
"""

import discord
import asyncio
from typing import List, Dict, Any, Optional, Union

from utils.constants import AUTHOR_ICON_URL, BOT_NAME, BOT_VERSION


def split_content_intelligently(content: str, max_length: int) -> List[str]:
    """
    Split content intelligently based on its structure.
    - For list-like content (single newlines), it splits by line.
    - For paragraph-based content, it splits by paragraph and then sentence.
    """
    if len(content) <= max_length:
        return [content]

    # Heuristic: Check if the content is more like a list or prose.
    # Lists typically use single newlines, while prose uses double newlines for paragraphs.
    is_list_like = '\n' in content and '\n\n' not in content

    # --- Strategy 1: Split by lines for lists ---
    if is_list_like:
        parts = []
        current_part = ""
        lines = content.split('\n')

        for line in lines:
            if len(line) > max_length:  # Handle single lines that are too long
                if current_part:
                    parts.append(current_part.strip())
                parts.append(line[:max_length - 4] + "...")
                current_part = ""
                continue

            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + '\n'
            else:
                current_part += line + '\n'

        if current_part.strip():
            parts.append(current_part.strip())
        return parts

    # --- Strategy 2: Split by paragraphs and sentences for prose ---
    parts = []
    current_part = ""
    paragraphs = content.split('\n\n')
    
    for paragraph in paragraphs:
        if len(current_part) + len(paragraph) + 2 > max_length:
            if current_part:
                parts.append(current_part.strip())
                current_part = ""
            
            if len(paragraph) > max_length:
                sentences = paragraph.split('. ')
                for i, sentence in enumerate(sentences):
                    sentence_with_period = sentence + ('.' if i < len(sentences) - 1 else '')
                    
                    if len(current_part) + len(sentence_with_period) + 1 > max_length:
                        if current_part:
                            parts.append(current_part.strip())
                            current_part = ""
                        
                        if len(sentence_with_period) > max_length:
                            while len(sentence_with_period) > max_length:
                                split_point = max_length - 10
                                parts.append(sentence_with_period[:split_point] + "...")
                                sentence_with_period = "..." + sentence_with_period[split_point:]
                            current_part = sentence_with_period
                        else:
                            current_part = sentence_with_period + ' '
                    else:
                        current_part += sentence_with_period + ' '
            else:
                current_part = paragraph + '\n\n'
        else:
            current_part += paragraph + '\n\n'
    
    if current_part.strip():
        parts.append(current_part.strip())
    
    return parts


def split_content_for_spoilers(content: str, max_length: int) -> List[str]:
    """
    Split content for spoiler tags, accounting for || overhead.
    
    Args:
        content (str): The content to split
        max_length (int): Maximum length per part
        
    Returns:
        List[str]: List of content parts
    """
    if len(content) <= max_length:
        return [content]
    
    # Account for spoiler tag overhead (4 characters: ||...||)
    effective_max = max_length - 4
    return split_content_intelligently(content, effective_max)


def create_structured_fields(
    sections: List[Dict[str, Any]], 
    field_char_limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Create structured fields from content sections with intelligent splitting.
    
    Args:
        sections (List[Dict]): List of sections with keys:
            - name: Section name (str)
            - content: Section content (str) 
            - inline: Whether field should be inline (bool, optional)
            - spoiler: Whether to wrap in spoiler tags (bool, optional)
            - emoji: Emoji prefix for the name (str, optional)
        field_char_limit (int): Character limit per field
        
    Returns:
        List[Dict]: List of field dictionaries ready for embed
    """
    fields = []
    
    for section in sections:
        name = section.get('name', '')
        content = section.get('content', '')
        inline = section.get('inline', False)
        spoiler = section.get('spoiler', False)
        emoji = section.get('emoji', '')
        
        if not content:
            continue
            
        # Add emoji prefix if provided
        if emoji:
            name = f"{emoji} {name}" if name else emoji
        
        # Handle spoiler wrapping
        if spoiler:
            content_parts = split_content_for_spoilers(content, field_char_limit)
            for i, part in enumerate(content_parts):
                field_name = name if i == 0 else ""
                fields.append({
                    "name": field_name,
                    "value": f"||{part}||",
                    "inline": inline
                })
        else:
            # Regular content splitting
            if len(content) <= field_char_limit:
                fields.append({
                    "name": name,
                    "value": content,
                    "inline": inline
                })
            else:
                content_parts = split_content_intelligently(content, field_char_limit)
                for i, part in enumerate(content_parts):
                    field_name = name if i == 0 else ""
                    fields.append({
                        "name": field_name,
                        "value": part,
                        "inline": inline
                    })
    
    return fields

async def create_embed_response(
    ctx, 
    description="", 
    fields=None, 
    title=BOT_NAME, 
    footer_text=f"{BOT_NAME} v{BOT_VERSION}", 
    thumbnail_url=None, 
    footer_icon_url=AUTHOR_ICON_URL, 
    url=None, 
    author_name=None, 
    author_icon_url=None, 
    author_url=None, 
    field_unbroken=False, 
    color=discord.Color.blue(),
    smart_split=True,
    max_description_length=4000,
    # New unified parameters
    sections=None,
    content="",
    auto_strategy=True,
    description_limit=3800,
    max_fields_per_embed=20,
    max_embed_chars=5800
):
    """
    Universal Discord embed creator with intelligent content handling.
    
    This function creates a Discord embed with automatic content optimization,
    intelligent field splitting, and multi-embed support when needed.
    
    Args:
        ctx (commands.Context): The Discord context to send the embed to
        description (str): The main description text of the embed
        fields (list): A list of field dictionaries with keys:
                      - name: Field title (str)
                      - value: Field content (str)
                      - inline: Whether to display field inline (bool, optional)
        title (str): The title of the embed
        footer_text (str, optional): Text to display in the footer
        thumbnail_url (str, optional): URL of thumbnail image to display
        footer_icon_url (str, optional): URL of icon to display in the footer
        url (str, optional): URL to make the title clickable
        author_name (str, optional): Name to display in the author field
        author_icon_url (str, optional): URL of icon to display in the author field
        author_url (str, optional): URL to make the author name clickable
        field_unbroken (bool, optional): Whether to use seamless field continuation
        color (discord.Color): Embed color
        smart_split (bool): Whether to use intelligent content splitting
        max_description_length (int): Maximum description length before converting to fields
        sections (list, optional): List of structured content sections for advanced field creation
        content (str, optional): Simple content alternative to description
        auto_strategy (bool): Whether to automatically choose description vs fields strategy
        description_limit (int): Maximum chars for description strategy when auto_strategy is True
        max_fields_per_embed (int): Maximum fields per embed for multi-embed handling
        max_embed_chars (int): Maximum characters per embed for multi-embed handling
        
    Returns:
        Union[discord.Message, List[discord.Message]]: Single message or list of messages
    
    Example:
        ```python
        # Simple usage
        await create_embed_response(ctx, "Simple content", title="Example")
        
        # Advanced usage with fields
        fields = [
            {"name": "🤖 Model", "value": "GPT-4", "inline": True},
            {"name": "🧠 Thinking", "value": "Long thinking content...", "spoiler": True},
            {"name": "💡 Answer", "value": "The answer is..."}
        ]
        await create_embed_response(ctx, "", fields=fields, title="LLM Response")
        
        # Advanced usage with sections
        sections = [
            {"name": "Model", "content": "GPT-4", "inline": True, "emoji": "🤖"},
            {"name": "Thinking", "content": "Long thinking...", "spoiler": True, "emoji": "🧠"},
            {"name": "Answer", "content": "The response...", "emoji": "💡"}
        ]
        await create_embed_response(ctx, sections=sections, title="LLM Response")
        ```
    """
    # UNIFIED SMART CONTENT HANDLING
    # Handle simple content parameter
    if content and not description and not sections:
        if auto_strategy and len(content) <= description_limit:
            # Use description strategy for short content
            description = content
        else:
            # Convert to sections for field strategy
            sections = [{"name": "📄 Content", "content": content}]
    
    # Handle structured sections
    if sections:
        if not fields:
            fields = []
        # Convert sections to fields using structured field creation
        section_fields = create_structured_fields(sections)
        fields.extend(section_fields)
    
    # Handle overly long description by converting to fields
    if description and len(description) > max_description_length and smart_split:
        # Convert description to a field and clear description
        if not fields:
            fields = []
        fields.insert(0, {"name": "📄 Content", "value": description})
        description = ""
    
    # UNIFIED MULTI-EMBED HANDLING
    if fields:
        # Calculate total embed size for multi-embed detection
        def calculate_embed_size(embed_title, embed_description, embed_footer, field_list, author_name_param=""):
            total = 0
            total += len(embed_title) if embed_title else 0
            total += len(embed_description) if embed_description else 0
            total += len(embed_footer) if embed_footer else 0
            total += len(author_name_param) if author_name_param else 0
            
            for field in field_list:
                total += len(field.get('name', ''))
                total += len(field.get('value', ''))
            
            return total
        
        # Check if we need multiple embeds
        total_chars = calculate_embed_size(title, description, footer_text, fields, author_name or "")
        
        if len(fields) > max_fields_per_embed or total_chars > max_embed_chars:
            # Use multi-embed strategy
            
            # Split into multiple embeds with size-aware chunking
            messages = []
            current_chunk = []
            embed_chunks = []
            
            for field in fields:
                # Test if adding this field would exceed limits
                test_chunk = current_chunk + [field]
                
                # Calculate size for this chunk
                test_title = f"{title} (Part X/Y)"
                test_footer = f"Continued... (Part X/Y)"
                test_size = calculate_embed_size(test_title, "", test_footer, test_chunk)
                
                # Check if we need to start a new chunk
                if (len(test_chunk) > max_fields_per_embed or 
                    test_size > max_embed_chars) and current_chunk:
                    
                    embed_chunks.append(current_chunk)
                    current_chunk = [field]
                else:
                    current_chunk = test_chunk
            
            # Add the last chunk if it has content
            if current_chunk:
                embed_chunks.append(current_chunk)
            
            # Create and send embeds
            for i, chunk in enumerate(embed_chunks):
                embed_title = f"{title} (Part {i+1}/{len(embed_chunks)})" if len(embed_chunks) > 1 else title
                embed_description = description if i == 0 else ""
                embed_footer = footer_text if i == 0 else f"Continued... (Part {i+1}/{len(embed_chunks)})"

                # Create a new embed for the chunk
                chunk_embed = discord.Embed(
                    title=embed_title,
                    description=embed_description,
                    color=color
                )
                if url and i == 0:
                    chunk_embed.url = url

                for field in chunk:
                    chunk_embed.add_field(name=field.get('name', ''), value=field.get('value', ''), inline=field.get('inline', False))

                if embed_footer:
                    chunk_embed.set_footer(text=embed_footer, icon_url=footer_icon_url)

                if thumbnail_url and i == 0:
                    chunk_embed.set_thumbnail(url=thumbnail_url)

                if author_name and i == 0:
                    chunk_embed.set_author(name=author_name, icon_url=author_icon_url, url=author_url)

                message = await ctx.send(embed=chunk_embed)
                messages.append(message)

                # Small delay between messages to avoid rate limits
                if i < len(embed_chunks) - 1:
                    await asyncio.sleep(0.5)
            
            return messages
    
    # SINGLE EMBED CREATION (Original logic preserved)
    # Create the embed with specified color
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    
    # Add URL if provided
    if url:
        embed.url = url
        
    # Add all fields with intelligent splitting
    if fields:
        for field in fields:
            name = field.get('name', '')
            value = field.get('value', '')
            inline = field.get('inline', False)
            
            # Skip empty fields
            if not value:
                continue
                
            # Handle fields that are too long
            if len(value) > 1024:
                if smart_split:
                    # Use intelligent splitting
                    parts = split_content_intelligently(value, 1024)
                else:
                    # Use simple line-based splitting (legacy behavior)
                    parts = []
                    current_part = ""
                    lines = value.split('\n')
                    for line in lines:
                        if len(current_part + line + '\n') > 1024:
                            parts.append(current_part)
                            current_part = line + '\n'
                        else:
                            current_part += line + '\n'
                    if current_part:
                        parts.append(current_part)
                    
                # Add the parts as separate fields
                for i, part in enumerate(parts):
                    if not field_unbroken:
                        embed.add_field(name=f"{name} ({i+1}/{len(parts)})", value=part, inline=inline)
                    elif i == 0:
                        embed.add_field(name=name, value=part, inline=inline)
                    else:
                        # Use an empty field name for continuation to make it appear connected
                        embed.add_field(name='', value=part, inline=inline)
            else:
                embed.add_field(name=name, value=value, inline=inline)
    
    # Add footer if provided
    if footer_text:
        if footer_icon_url:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)
        else:
            embed.set_footer(text=footer_text)
            
    # Add thumbnail if provided
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    elif ctx.guild and ctx.guild.me.avatar:
        embed.set_thumbnail(url=ctx.guild.me.avatar.url)
    elif ctx.bot.user.avatar:
        embed.set_thumbnail(url=ctx.bot.user.avatar.url)
        
    # Add author if provided
    if author_name:
        if author_icon_url and author_url:
            embed.set_author(name=author_name, icon_url=author_icon_url, url=author_url)
        elif author_icon_url:
            embed.set_author(name=author_name, icon_url=author_icon_url)
        elif author_url:
            embed.set_author(name=author_name, url=author_url)
        else:
            embed.set_author(name=author_name)
            
    # Send the embed
    return await ctx.send(embed=embed)


async def create_llm_response(
    ctx,
    response_text: str,
    question: str,
    model_name: str,
    thinking_content: str = "",
    show_thinking: bool = False,
    title: str = "LLM Response",
    color: discord.Color = discord.Color.blue(),
    performance_metrics: Optional[Dict[str, Any]] = None
) -> Union[discord.Message, List[discord.Message]]:
    """
    Create a specialized LLM response embed with intelligent formatting.
    
    Args:
        ctx: Discord context
        response_text: The main LLM response content
        question: The original question asked
        model_name: Name of the LLM model used
        thinking_content: Optional thinking process content
        show_thinking: Whether to display thinking content
        title: Embed title
        color: Embed color
        performance_metrics: Optional performance metrics dict with elapsed_time, chars_per_sec, etc.
        
    Returns:
        Union[discord.Message, List[discord.Message]]: Single message or list of messages
    """
    # Calculate total content size for strategy decision
    total_content_size = len(response_text) + (len(thinking_content) if show_thinking else 0)
    
    # Strategy 1: Small responses (< 2800 chars) - use description
    if total_content_size <= 2800:  # Leave room for other embed elements
        if show_thinking and thinking_content:
            formatted_content = f"**🤖 Model:** `{model_name}`\n\n"
            formatted_content += f"||🧠 **Thinking Process:**\n\n{thinking_content}||\n\n"
            formatted_content += f"**💡 Answer:**\n{response_text}"
        else:
            formatted_content = f"**🤖 Model:** `{model_name}`\n\n{response_text}"
        
        # Add performance metrics to formatted content if available
        if performance_metrics:
            if performance_metrics.get('has_token_data', False):
                perf_text = (
                    f"\n\n**📈 Performance:**\n"
                    f"🚀 {performance_metrics['tokens_per_sec']:.0f} tokens/s\n"
                    f"📊 {performance_metrics['completion_tokens']} tokens generated in ⏱️ {performance_metrics['elapsed_time']:.2f}s\n"
                    f"🔢 {performance_metrics['total_tokens']} total tokens ({performance_metrics['prompt_tokens']} prompt + {performance_metrics['completion_tokens']} completion)"
                )
            else:
                perf_text = (
                    f"\n\n**📈 Performance:**\n"
                    f"🚀 {performance_metrics['chars_per_sec']:.0f} chars/s (~{performance_metrics['tokens_per_sec']:.0f} tokens/s)\n"
                    f"📊 {performance_metrics['char_count']} chars (~{performance_metrics['char_count']//4} tokens) in ⏱️ {performance_metrics['elapsed_time']:.2f}s"
                )
            formatted_content += perf_text
        
        return await create_embed_response(
            ctx,
            formatted_content,
            title=title,
            footer_text=f"Question: {question[:100]}{'...' if len(question) > 100 else ''}",
            color=color,
            author_name=f"Response from {model_name}",
            author_icon_url=ctx.bot.user.avatar.url if ctx.bot.user.avatar else None
        )
    
    # Strategy 2: Large responses - use structured fields
    sections = []
    
    # Model info section
    sections.append({
        "name": "Model",
        "content": model_name,
        "inline": True,
        "emoji": "🤖"
    })
    
    # Add spacer
    sections.append({
        "name": "\u200b",
        "content": "\u200b",
        "inline": True
    })
    
    # Thinking section if needed
    if show_thinking and thinking_content:
        sections.append({
            "name": "Thinking Process",
            "content": thinking_content,
            "spoiler": True,
            "emoji": "🧠"
        })
    
    # Answer section
    sections.append({
        "name": "Answer",
        "content": response_text,
        "emoji": "💡"
    })      
    # Performance metrics section if available
    if performance_metrics:
        if performance_metrics.get('has_token_data', False):
            perf_text = (
                f"🚀 {performance_metrics['tokens_per_sec']:.0f} tokens/s\n"
                f"📊 {performance_metrics['completion_tokens']} tokens generated in ⏱️ {performance_metrics['elapsed_time']:.2f}s\n"
                f"🔢 {performance_metrics['total_tokens']} total tokens ({performance_metrics['prompt_tokens']} prompt + {performance_metrics['completion_tokens']} completion)"
            )
        else:
            perf_text = (
                f"🚀 {performance_metrics['chars_per_sec']:.0f} chars/s (~{performance_metrics['tokens_per_sec']:.0f} tokens/s)\n"
                f"📊 {performance_metrics['char_count']} chars (~{performance_metrics['char_count']//4} tokens) in ⏱️ {performance_metrics['elapsed_time']:.2f}s"
            )
        sections.append({
            "name": "Performance",
            "content": perf_text,
            "emoji": "📈"
        })

    return await create_embed_response(
        ctx,
        sections=sections,
        title=title,
        footer_text=f"Question: {question[:80]}{'...' if len(question) > 80 else ''}",
        color=color,
        author_name=f"Response from {model_name}",
        author_icon_url=ctx.bot.user.avatar.url if ctx.bot.user.avatar else None,
        field_unbroken=True
    )
