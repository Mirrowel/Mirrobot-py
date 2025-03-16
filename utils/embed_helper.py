"""
Embed helper module for Mirrobot.

This module provides utilities for creating and managing Discord embed messages,
making it easier to create consistent, well-formatted responses.
"""

import discord

async def create_embed_response(ctx, title, description, fields, footer_text=None, thumbnail_url=None, footer_icon_url=None, url=None, author_name=None, author_icon_url=None, author_url=None):
    """
    Create and send a formatted Discord embed response.
    
    This function creates a consistent Discord embed with various optional parameters
    and sends it to the specified context.
    
    Args:
        ctx (commands.Context): The Discord context to send the embed to
        title (str): The title of the embed
        description (str): The main description text of the embed
        fields (list): A list of field dictionaries with keys:
                      - name: Field title (str)
                      - value: Field content (str)
                      - inline: Whether to display field inline (bool, optional)
        footer_text (str, optional): Text to display in the footer
        thumbnail_url (str, optional): URL of thumbnail image to display
        footer_icon_url (str, optional): URL of icon to display in the footer
        url (str, optional): URL to make the title clickable
        author_name (str, optional): Name to display in the author field
        author_icon_url (str, optional): URL of icon to display in the author field
        author_url (str, optional): URL to make the author name clickable
        
    Returns:
        discord.Message: The sent message object containing the embed
    
    Example:
        ```python
        fields = [
            {"name": "Field 1", "value": "Value 1", "inline": True},
            {"name": "Field 2", "value": "Value 2", "inline": False}
        ]
        
        await create_embed_response(
            ctx=ctx,
            title="Example Embed",
            description="This is a sample embed message",
            fields=fields,
            footer_text="Footer text here"
        )
        ```
    """
    # Create the embed with specified color
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    
    # Add URL if provided
    if url:
        embed.url = url
        
    # Add all fields
    for field in fields:
        name = field.get('name', '')
        value = field.get('value', '')
        inline = field.get('inline', False)
        
        # Skip empty fields
        if not value:
            continue
            
        # Handle fields that are too long
        if len(value) > 1024:
            # Split into multiple fields
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
                if i == 0:
                    embed.add_field(name=name, value=part, inline=inline)
                else:
                    embed.add_field(name=f"{name} (continued)", value=part, inline=inline)
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
