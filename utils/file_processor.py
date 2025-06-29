import discord
import aiohttp
import io
import pdfplumber
import chardet
from utils.logging_setup import get_logger

logger = get_logger()

async def download_file(url):
    """Download file from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
    return None

async def extract_text_from_attachment(attachment: discord.Attachment):
    """Extract text from a Discord attachment."""
    content = await attachment.read()
    filename = attachment.filename
    if "pdf" in attachment.content_type:
        return extract_text_from_pdf(content, filename)
    elif "text" in attachment.content_type:
        return extract_text_from_txt(content, filename)
    else:
        return None

async def extract_text_from_url(url):
    """Extract text from a URL."""
    content = await download_file(url)
    if content:
        filename = url.split('/')[-1]
        if url.endswith(".pdf"):
            return extract_text_from_pdf(content, filename)
        elif any(url.endswith(ext) for ext in [".txt", ".log", ".ini"]):
            return extract_text_from_txt(content, filename)
    return None

def extract_text_from_pdf(content, filename):
    """Extract text from PDF content."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "".join(page.extract_text() for page in pdf.pages)
            return f"--- Start of file: {filename} ---\n\n{text}\n\n--- End of file: {filename} ---"
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return None

def extract_text_from_txt(content, filename):
    """Extract text from a text-based file."""
    try:
        encoding = chardet.detect(content)['encoding']
        text = content.decode(encoding, errors='ignore')
        return f"--- Start of file: {filename} ---\n\n{text}\n\n--- End of file: {filename} ---"
    except Exception as e:
        logger.error(f"Error extracting text from text file: {e}")
        return None
