# cogs/rag_commands.py
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands
from typing import Optional

from utils.rag_manager import RAGManager
from utils.constants import PKB_COLLECTION_NAME
from utils import permissions

logger = logging.getLogger('discord_bot.rag_commands')

class RAGCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rag_manager: RAGManager = None # This will be set in a setup hook
        logger.info("RAGCommands Cog loaded.")

    @commands.group(name="doc", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def doc(self, ctx):
        """Command group for managing the Permanent Knowledge Base."""
        await ctx.send_help(ctx.command)

    @doc.command(name="index")
    @commands.has_permissions(administrator=True)
    async def index(self, ctx, url: Optional[str] = None):
        """
        Indexes a document from a URL or a file attachment into the PKB.

        Usage:
        !doc index [url]
        !doc index (with file attachment)
        """
        if url is None and not ctx.message.attachments:
            await ctx.send("Please provide a URL or attach a file to index.")
            return

        content = ""
        source_name = ""

        async with ctx.typing():
            try:
                if url:
                    source_name = url.split('/')[-1] or "web_document"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                content = await response.text()
                            else:
                                await ctx.send(f"Error fetching URL: Status code {response.status}")
                                return
                elif ctx.message.attachments:
                    attachment = ctx.message.attachments[0]
                    source_name = attachment.filename
                    content = (await attachment.read()).decode('utf-8')

                if not content:
                    await ctx.send("Could not retrieve any content to index.")
                    return

                success = await self.rag_manager.index_document(
                    text_content=content,
                    source_name=source_name,
                    collection_name=PKB_COLLECTION_NAME
                )

                if success:
                    await ctx.send(f"✅ Successfully indexed document from `{source_name}`.")
                else:
                    await ctx.send(f"❌ Failed to index document from `{source_name}`. Check logs for details.")

            except Exception as e:
                logger.error(f"Error during document indexing command: {e}", exc_info=True)
                await ctx.send("An unexpected error occurred while indexing the document.")

    @doc.command(name="list")
    @commands.has_permissions(administrator=True)
    async def list_documents(self, ctx):
        """Lists all indexed documents in the Permanent Knowledge Base."""
        async with ctx.typing():
            try:
                doc_names = await self.rag_manager.list_documents(PKB_COLLECTION_NAME)
                if not doc_names:
                    await ctx.send("The Permanent Knowledge Base is currently empty.")
                    return

                formatted_list = "\n".join(f"- `{name}`" for name in doc_names)
                response_message = f"**Indexed Documents in PKB:**\n{formatted_list}"
                
                await ctx.send(response_message)

            except Exception as e:
                logger.error(f"Error listing documents: {e}", exc_info=True)
                await ctx.send("An error occurred while trying to list the documents.")

    @doc.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def delete_document(self, ctx, *, source_name: str):
        """
        Deletes an indexed document from the Permanent Knowledge Base.

        You must provide the exact source name to delete. Use !doc list to see the names.
        """
        async with ctx.typing():
            try:
                success = await self.rag_manager.delete_document(source_name, PKB_COLLECTION_NAME)
                if success:
                    await ctx.send(f"✅ Attempted to delete document `{source_name}`. Check logs for confirmation.")
                else:
                    await ctx.send(f"❌ Failed to delete document `{source_name}`. An error occurred.")
            except Exception as e:
                logger.error(f"Error during document deletion command for source '{source_name}': {e}", exc_info=True)
                await ctx.send("An unexpected error occurred while deleting the document.")

    @commands.command(name="rag_debug")
    @commands.has_permissions(administrator=True)
    async def rag_debug(self, ctx, mode: Optional[str] = "last"):
        """
        Displays debug information for the RAG pipeline.
        Usage: !rag_debug [last]
        """
        if mode != "last":
            await ctx.send("Invalid mode. Currently, only `last` is supported.")
            return

        try:
            latest_log = self.rag_manager.debug_logs[-1]
        except IndexError:
            await ctx.send("No debug logs available.")
            return

        embed = discord.Embed(title="RAG Debug Log", description=f"Session ID: `{latest_log.session_id}`", color=discord.Color.orange())

        # Function to format and add fields, handling character limits
        def add_field_smart(name, value, inline=False):
            if not value:
                value = "N/A"
            if len(value) > 1024:
                value = value[:1020] + "..."
            embed.add_field(name=name, value=value, inline=inline)

        add_field_smart("1. Refined Query", f"```\n{latest_log.refined_query}\n```")
        add_field_smart("2. Retrieved Context", f"```\n{latest_log.retrieved_context}\n```")
        add_field_smart("3. Final Prompt", f"```\n{latest_log.final_prompt}\n```")
        add_field_smart("4. Final Answer", f"```\n{latest_log.final_answer}\n```")
        
        # Full context is often very long, so it goes last and might be truncated.
        add_field_smart("Full Initial Context", f"```\n{latest_log.full_context}\n```")

        await ctx.send(embed=embed)


async def setup(bot):
    cog = RAGCommands(bot)
    # This is a crucial step to ensure the cog has access to the manager
    if hasattr(bot, 'rag_manager'):
        cog.rag_manager = bot.rag_manager
        await bot.add_cog(cog)
    else:
        logger.error("RAGManager not found on bot object. RAGCommands will not be loaded.")