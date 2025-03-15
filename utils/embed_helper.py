import discord

async def create_embed_response(ctx, title, description, fields, footer_text=None, thumbnail_url=None, footer_icon_url=None, url=None, author_name=None, author_icon_url=None, author_url=None):
    """
    Create a standardized embed response with proper formatting.
    
    Args:
        ctx: The command context
        title: The title of the embed
        description: The description text
        fields: List of dictionaries with 'name', 'value', and 'inline' keys
        footer_text: Optional text for the footer
        thumbnail_url: Optional URL for the thumbnail
        footer_icon_url: Optional URL for the footer icon
        url: Optional URL for the embed title hyperlink
        author_name: Optional custom author name for the embed
        author_icon_url: Optional custom author icon URL for the embed
        author_url: Optional custom author URL for the embed
    """
    embed_color = discord.Color.blue()
    
    # Create the embed with title and description
    embed = discord.Embed(title=title, url=url, description=description, color=embed_color)
    
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url, url=author_url)

    # Add thumbnail if provided
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    elif ctx.guild and ctx.guild.me.avatar:
        embed.set_thumbnail(url=ctx.guild.me.avatar.url)
    elif ctx.bot.user.avatar:
        embed.set_thumbnail(url=ctx.bot.user.avatar.url)
        
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
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)
        
    await ctx.send(embed=embed)
