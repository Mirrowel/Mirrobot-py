import requests
from core.ocr import msg_reply
import discord
from discord.ext import commands
from utils.logging_setup import get_logger
from utils.permissions import has_command_permission, command_category
from core.pattern_manager import (
    load_patterns, save_patterns, find_response, 
    get_server_patterns, get_next_response_id, get_next_pattern_id,
    REGEX_FLAGS, server_patterns
)
import re
import datetime
import time
import io
import aiohttp
from PIL import Image
import pytesseract
from utils.constants import BOT_NAME, BOT_VERSION

logger = get_logger()

class PaginationView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=180)  # 3 minute timeout
        self.embeds = embeds
        self.current_page = 0
        self.message = None
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])
        else:
            await interaction.response.defer()
    
    async def on_timeout(self):
        if self.message:
            # Remove buttons after timeout
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                # Message already deleted, suppress the error
                pass

class PatternCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Make sure patterns are loaded when the cog is initialized
        load_patterns()
    
    @commands.command(name='list_patterns', help='List all pattern responses for this server.\nArguments: [verbosity] - Optional verbosity level (1-3, default: 1)\nExample: !list_patterns or !list_patterns 2')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def list_patterns(self, ctx, verbosity: int = 1):
        """List all patterns for this server with configurable verbosity"""
        # Validate verbosity level
        if verbosity not in [1, 2, 3]:
            await ctx.reply("Invalid verbosity level. Please use 1, 2, or 3.")
            return
            
        server_id = str(ctx.guild.id)
        
        server_specific = []
        default = []
        
        # Get server-specific patterns
        if server_id in server_patterns:
            server_specific = server_patterns[server_id]
        
        # Get default patterns
        if "default" in server_patterns:
            default = server_patterns["default"]
        
        if not server_specific and not default:
            await ctx.reply("No patterns found.")
            return
        
        embeds = []
        
        # Create embeds for server-specific patterns
        if server_specific:
            server_embeds = self._create_pattern_embeds(
                server_specific, 
                "Server-specific Patterns", 
                discord.Color.blue(), 
                "🔹",
                verbosity
            )
            embeds.extend(server_embeds)
        
        # Create embeds for default patterns
        if default:
            default_embeds = self._create_pattern_embeds(
                default, 
                "Default Patterns", 
                discord.Color.green(), 
                "🔸",
                verbosity
            )
            embeds.extend(default_embeds)
        
        if not embeds:
            await ctx.reply("No patterns could be displayed.")
            return
        
        # Set bot avatar as thumbnail if available
        if ctx.guild and ctx.guild.me and ctx.guild.me.avatar:
            for embed in embeds:
                embed.set_thumbnail(url=ctx.guild.me.avatar.url)
        
        # Add warning for high verbosity
        if verbosity == 3:
            note = ("⚠️ **Note**: Level 3 verbosity shows full response text which can make embeds harder to read. "
                    "Consider using `!view_response <id>` for detailed information about specific responses.")
            for embed in embeds:
                if embed.description:
                    embed.description = f"{embed.description}\n\n{note}"
                else:
                    embed.description = note
        
        # Send the first embed and create pagination if needed
        if len(embeds) == 1:
            await ctx.reply(embed=embeds[0])
        else:
            # Add page numbers to embeds
            for i, embed in enumerate(embeds):
                embed.set_footer(text=f"{BOT_NAME} v{BOT_VERSION} | Page {i+1}/{len(embeds)}")
            
            # Create pagination with buttons
            view = PaginationView(embeds)
            message = await ctx.reply(embed=embeds[0], view=view)
            view.message = message

    def _create_pattern_embeds(self, patterns, title_prefix, color, icon, verbosity=1):
        """Create nicely formatted embeds for patterns with pagination and configurable verbosity"""
        if not patterns:
            return []
            
        embeds = []
        max_fields_per_embed = 24 if verbosity == 1 else 12  # More fields for lower verbosity
        current_embed = None
        current_fields = 0
        
        # Define verbosity descriptions
        verbosity_desc = {
            1: "Basic information (pattern counts only)",
            2: "Intermediate information (includes pattern details)",
            3: "Full information (includes response text)"
        }
        
        for response in patterns:
            # Prepare the response field for this response
            field_name = f"{icon} Response ID {response['response_id']}"
            if response.get("name"):
                field_name += f" [{response['name']}]"
            
            # Field value depends on verbosity
            if verbosity == 1:
                # Level 1: Just show pattern count
                field_value = f"**Patterns:** {len(response['patterns'])}\n"
                if response.get("note"):
                    field_value += f"**Note:** {response['note']}\n"
            
            else:
                # Level 2 or 3: Include more details
                if verbosity == 3:
                    # Level 3: Include response text
                    field_value = f"**Response:** `{response['response']}`\n"
                else:
                    # Level 2: No response text
                    field_value = ""
                    
                if response.get("note"):
                    field_value += f"**Note:** {response['note']}\n"
                
                field_value += f"**Patterns ({len(response['patterns'])}):**\n"
                
                # Add each pattern to the field
                for pattern in response['patterns']:
                    # Extract pattern string and determine flags
                    pattern_str = pattern['pattern'].pattern
                    flags = []
                    if pattern['pattern'].flags & re.IGNORECASE:
                        flags.append("IC")
                    if pattern['pattern'].flags & re.DOTALL:
                        flags.append("DA")
                    if pattern['pattern'].flags & re.MULTILINE:
                        flags.append("ML")
                    
                    flags_str = f" [{','.join(flags)}]" if flags else ""
                    
                    # Format the pattern name/id
                    pattern_name = f"ID {pattern['id']}"
                    if pattern.get("name"):
                        pattern_name += f" [{pattern['name']}]"
                    
                    # Truncate pattern if too long
                    if len(pattern_str) > 60:
                        pattern_str = pattern_str[:57] + "..."
                    
                    pattern_line = f"▫️ {pattern_name}: `{pattern_str}`{flags_str}"
                    if pattern.get("url"):
                        pattern_line += f" [Screenshot]({pattern['url']})"
                    pattern_line += "\n"
                    
                    field_value += pattern_line
            
            # Check if we need to create a new embed
            if current_embed is None or current_fields >= max_fields_per_embed:
                current_embed = discord.Embed(
                    title=f"{title_prefix} ({len(patterns)} responses)",
                    description=f"Verbosity Level: {verbosity} - {verbosity_desc[verbosity]}",
                    color=color,
                    timestamp=datetime.datetime.now()
                )
                current_embed.set_footer(text=f"{BOT_NAME} v{BOT_VERSION}")
                embeds.append(current_embed)
                current_fields = 0
            
            # Add the field to the current embed
            current_embed.add_field(name=field_name, value=field_value, inline=False)
            current_fields += 1
        
        return embeds

    @commands.command(name='add_response', help='Add a new response with optional name and note.\nArguments: response (str) - The response text\n           [name] (str) - Optional friendly name for the response\n           [note] (str) - Optional description or explanation\nExample: !add_response "!v6fix" "v6fix_command" "Common v6 connection issues"')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_response(self, ctx, response: str, name: str = "", *, note: str = ""):
        """Add a new response to the server configuration with optional name and note"""
        server_id = str(ctx.guild.id)
        
        # Initialize server responses list if needed
        if server_id not in server_patterns:
            server_patterns[server_id] = []
        
        # Check if name already exists if a name is provided
        if name:
            for existing_response in server_patterns[server_id]:
                if existing_response.get("name", "").lower() == name.lower():
                    await ctx.reply(f"A response with name '{name}' already exists. Please choose a different name.")
                    return
        
        # Get the next available response ID
        response_id = get_next_response_id(server_id)
        
        # Create the new response object
        new_response = {
            "response_id": response_id,
            "response": response,
            "name": name,
            "note": note,
            "patterns": []
        }
        
        # Add the new response
        server_patterns[server_id].append(new_response)
        
        # Save patterns to file
        if save_patterns():
            name_info = f" (Named: '{name}')" if name else ""
            await ctx.reply(f"Successfully added response ID {response_id}{name_info}: `{response}`\nUse `!add_pattern_to_response {response_id if not name else name} \"your_pattern_here\"` to add patterns to this response.")
        else:
            await ctx.reply("Response added to memory but could not be saved to file. Check logs for details.")

    @commands.command(name='remove_response', help='Remove a response and all its patterns.\nArguments: response_id_or_name - ID number or name of the response\nExample: !remove_response 5 or !remove_response v6fix_command')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_response(self, ctx, response_id_or_name: str):
        """Remove a response from the server configuration"""
        server_id = str(ctx.guild.id)
        
        if server_id not in server_patterns:
            await ctx.reply("This server has no custom responses.")
            return
        
        # Find the response to remove
        for i, response in enumerate(server_patterns[server_id]):
            if (str(response["response_id"]) == response_id_or_name or 
                response.get("name", "").lower() == response_id_or_name.lower()):
                removed_response = server_patterns[server_id].pop(i)
                
                # Save patterns to file
                if save_patterns():
                    name_info = f" [{removed_response.get('name')}]" if removed_response.get("name") else ""
                    await ctx.reply(f"Successfully removed response ID {removed_response['response_id']}{name_info}: `{removed_response['response']}` and all {len(removed_response['patterns'])} patterns.")
                else:
                    await ctx.reply("Response removed from memory but could not update the file. Check logs for details.")
                return
        
        await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")

    @commands.command(name='add_pattern_to_response', help='Add a pattern to an existing response.\nArguments: response_id_or_name - ID number or name of the response\n           pattern (str) - Regex pattern to match\n           [flags] (str) - Optional regex flags (e.g., "DOTALL|IGNORECASE")\n           [name] (str) - Optional friendly name for the pattern\n           [url] (str) - Optional screenshot URL\nExample: !add_pattern_to_response 5 ".*error.*message" "DOTALL" "error_pattern"\nExample: !add_pattern_to_response v6fix_command ".*error.*" "DOTALL"')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def add_pattern_to_response(self, ctx, response_id_or_name: str, pattern: str, flags: str = "", name: str = "", url: str = ""):
        """Add a pattern to an existing response"""
        server_id = str(ctx.guild.id)
        
        if server_id not in server_patterns:
            await ctx.reply("This server has no custom responses.")
            return
        
        # Find the response
        response = find_response(server_id, response_id_or_name)
                
        if not response:
            await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")
            return
        
        try:
            # Parse and combine regex flags
            flag_value = 0
            if flags:
                for flag in flags.split('|'):
                    if flag in REGEX_FLAGS:
                        flag_value |= REGEX_FLAGS[flag]
                    else:
                        await ctx.reply(f"Invalid flag: {flag}. Valid flags are: {', '.join(REGEX_FLAGS.keys())}")
                        return
            
            # Compile the pattern
            compiled_pattern = re.compile(pattern, flag_value)
            
            # Get the next pattern ID
            pattern_id = get_next_pattern_id(response)
            
            # Use a default name if none provided
            if not name:
                name = f"pattern_{pattern_id}"
            
            # Add the new pattern
            response["patterns"].append({
                "id": pattern_id,
                "name": name,
                "pattern": compiled_pattern,
                "url": url
            })
            
            # Save patterns to file
            if save_patterns():
                response_identifier = f"response ID {response['response_id']}"
                if response.get("name"):
                    response_identifier += f" [{response['name']}]"
                await ctx.reply(f"Successfully added pattern {pattern_id} to {response_identifier}.")
            else:
                await ctx.reply("Pattern added to memory but could not be saved to file. Check logs for details.")
        
        except re.error as e:
            await ctx.reply(f"Error compiling regex pattern: {e}")
        except Exception as e:
            logger.error(f"Error adding pattern: {e}")
            await ctx.reply(f"Error adding pattern: {e}")

    @commands.command(name='remove_pattern_from_response', help='Remove a pattern from a response.\nArguments: response_id_or_name - ID number or name of the response\n           pattern_id (int) - ID number of the pattern to remove\nExample: !remove_pattern_from_response 5 2\nExample: !remove_pattern_from_response v6fix_command 2')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def remove_pattern_from_response(self, ctx, response_id_or_name: str, pattern_id: int):
        """Remove a pattern from a response"""
        server_id = str(ctx.guild.id)
        
        if server_id not in server_patterns:
            await ctx.reply("This server has no custom responses.")
            return
        
        # Find the response
        response = find_response(server_id, response_id_or_name)
                
        if not response:
            await ctx.reply(f"No response found with ID or name '{response_id_or_name}' in this server's configuration.")
            return
        
        # Find and remove the pattern
        pattern_found = False
        for i, pattern in enumerate(response["patterns"]):
            if pattern["id"] == pattern_id:
                del response["patterns"][i]
                pattern_found = True
                break
        
        if not pattern_found:
            await ctx.reply(f"No pattern found with ID {pattern_id} in response {response_id_or_name}.")
            return
            
        # Remove the response if no patterns left
        if not response["patterns"]:
            for i, r in enumerate(server_patterns[server_id]):
                if r["response_id"] == response["response_id"]:
                    del server_patterns[server_id][i]
                    response_identifier = f"response {response['response_id']}"
                    if response.get("name"):
                        response_identifier += f" [{response['name']}]"
                    await ctx.reply(f"Removed pattern {pattern_id} and also removed {response_identifier} as it no longer has any patterns.")
                    break
        else:
            response_identifier = f"response {response['response_id']}"
            if response.get("name"):
                response_identifier += f" [{response.get('name')}]"
            await ctx.reply(f"Successfully removed pattern {pattern_id} from {response_identifier}.")
        
        # Save patterns to file
        if not save_patterns():
            await ctx.reply("Warning: Changes made in memory but could not be saved to file. Check logs for details.")

    @commands.command(name='view_response', help='View details of a specific response.\nArguments: response_id_or_name - ID number or name of the response\nExample: !view_response 5\nExample: !view_response v6fix_command')
    @has_command_permission()
    @command_category("OCR Configuration")
    async def view_response(self, ctx, response_id_or_name: str):
        """View details of a specific response"""
        server_id = str(ctx.guild.id)
        
        # Try server-specific patterns first
        response = None
        source = None
        
        # Check server-specific patterns
        if server_id in server_patterns:
            response = find_response(server_id, response_id_or_name)
            if response:
                source = "server"
                    
        # If not found, check default patterns
        if not response and "default" in server_patterns:
            # Try to interpret as an integer (ID)
            try:
                response_id = int(response_id_or_name)
                # Search by ID
                for r in server_patterns["default"]:
                    if r["response_id"] == response_id:
                        response = r
                        source = "default"
                        break
            except ValueError:
                # Search by name
                for r in server_patterns["default"]:
                    if r.get("name", "").lower() == response_id_or_name.lower():
                        response = r
                        source = "default"
                        break
        
        if not response:
            await ctx.reply(f"No response found with ID or name '{response_id_or_name}'.")
            return
        
        # Build detailed response info
        response_text = f"**Response ID {response['response_id']}** ({source})"
        if response.get("name"):
            response_text += f" [{response['name']}]"
        response_text += f"\nText: `{response['response']}`\n"
        
        if response.get("note"):
            response_text += f"Note: {response['note']}\n"
        
        response_text += f"\n**Patterns ({len(response['patterns'])}):**\n"
        
        for pattern in response["patterns"]:
            response_text += f"- ID {pattern['id']}: "
            if pattern.get("name"):
                response_text += f"`{pattern['name']}` "
            
            # Get pattern string and flags
            pattern_str = pattern['pattern'].pattern
            flags = []
            if pattern['pattern'].flags & re.IGNORECASE:
                flags.append("IGNORECASE")
            if pattern['pattern'].flags & re.DOTALL:
                flags.append("DOTALL")
            if pattern['pattern'].flags & re.MULTILINE:
                flags.append("MULTILINE")
            
            # Truncate pattern if needed
            if len(pattern_str) > 50:
                pattern_str = pattern_str[:47] + "..."
            
            response_text += f"`{pattern_str}`"
            
            if flags:
                response_text += f" Flags: {', '.join(flags)}"
                
            if pattern.get("url"):
                response_text += f" [Screenshot]({pattern['url']})"
                
            response_text += "\n"
        
        # Split into chunks if needed
        if len(response_text) > 2000:
            chunks = [response_text[i:i+1990] for i in range(0, len(response_text), 1990)]
            for i, chunk in enumerate(chunks):
                await ctx.reply(f"{chunk}\n*Part {i+1}/{len(chunks)}*")
        else:
            await ctx.reply(response_text)

    @commands.command(name='extract_text', help='Extract text from an image without matching patterns.\nArguments: [url] (optional) - URL to an image\nExample: !extract_text https://example.com/image.jpg')
    @has_command_permission()
    @command_category("OCR Utilities")
    async def extract_text(self, ctx, url: str = None):
        """Extract text from an image attachment or URL without applying patterns"""
        start_time = time.time()
        await ctx.channel.trigger_typing()
        
        if url:
            # Process URL provided as an argument
            try:
                logger.info(f'Grabbing the URL: {url}')
                response = requests.head(url)
                content_type = response.headers.get('content-type')
                if content_type is not None and content_type.startswith('image/'):
                    image_response = requests.get(url)
                    width, height = check_image_dimensions(io.BytesIO(image_response.content))
                    if width > 300 and height > 200:
                        logger.info("Content type is image")
                        # Create a simulated attachment object with the URL
                        attachment = type('FakeAttachment', (object,), {
                            'url': url,
                            'size': 999999,
                            'content_type': content_type
                        })
                        await self._extract_and_respond(ctx, attachment, start_time)
            except Exception as e:
                logger.error(f"Error processing URL: {e}")
                await ctx.reply(f"Error processing the URL: {e}")
        
        elif ctx.message.attachments:
            # Process attachment from the message
            attachment = ctx.message.attachments[0]
            logger.debug(f"Received image extraction request from {ctx.author}\nServer: {ctx.guild.name}:{ctx.guild.id}, Channel: {ctx.channel.name}:{ctx.channel.id}," + (f" Parent:{ctx.channel.parent}" if ctx.channel.type == 'public_thread' or ctx.channel.type == 'private_thread' else ""))
            logger.info(f'Received an attachment of size: {attachment.size}')
            if attachment.size < 500000 and attachment.content_type.startswith('image/'):
                if (attachment.width > 300 and attachment.height > 200):
                    await self._extract_and_respond(ctx, attachment, start_time)
                else:
                    await ctx.reply('Images must be at least 300x200 pixels.')
            else:
                await ctx.reply('Please attach an image (no GIFs) with a size less than 500KB.')
        
        else:
            await ctx.reply("Please provide either a URL or attach an image to extract text from.")

    async def _extract_and_respond(self, ctx, attachment, start_time):
        """Extract text from attachment and respond directly to the command"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(attachment.url) as resp:
                    if resp.status == 200:
                        data = io.BytesIO(await resp.read())
                        image = Image.open(data)
                        text = pytesseract.image_to_string(image, 'eng')
                        
                        logger.info(f"Text extraction took {time.time() - start_time:.2f} seconds.")
                        
                        if text.strip():
                            # Split into chunks if needed
                            await msg_reply(ctx, text)
                        else:
                            await ctx.reply("No text could be extracted from the image.")
                    else:
                        await ctx.reply(f"Failed to fetch the image. Status code: {resp.status}")
            except Exception as e:
                logger.error(f"Error in OCR processing: {e}")
                await ctx.reply(f"Error processing the image: {e}")
