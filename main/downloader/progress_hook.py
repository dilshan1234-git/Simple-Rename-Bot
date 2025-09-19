import time
import math
import asyncio
import logging
from pyrogram import enums
from main.utils import humanbytes

# Set up logging to debug issues with message updates
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text=""):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.last_update_time = 0
        self.message = None  # Will be set after sending the first message
        self.loop = asyncio.get_event_loop()

    async def update_msg(self, text, retries=3, delay=1):
        attempt = 0
        while attempt < retries:
            try:
                if self.message is None:
                    # Send initial message
                    self.message = await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                    logger.info(f"Sent initial progress message: {text[:50]}...")
                    return
                else:
                    # Try editing the existing message
                    await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                    logger.info(f"Successfully updated message: {text[:50]}...")
                    return
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to update message: {str(e)}")
                if "MESSAGE_ID_INVALID" in str(e):
                    # Reset message to None to force sending a new message
                    self.message = None
                    try:
                        self.message = await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=text,
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                        logger.info("Sent new message due to invalid message ID")
                        return
                    except Exception as e:
                        logger.error(f"Failed to send new message: {str(e)}")
                attempt += 1
                if attempt < retries:
                    await asyncio.sleep(delay)  # Wait before retrying
        logger.error(f"All {retries} attempts failed to update or send message")

    def hook(self, d):
        """
        Hook for youtube_dl progress updates.
        """
        status = d.get('status', None)
        now = time.time()
        if now - self.last_update_time < 5:  # Increased to 5 seconds to avoid rate limits
            return
        self.last_update_time = now

        if status == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)

            if total_bytes and downloaded_bytes and isinstance(total_bytes, (int, float)) and isinstance(downloaded_bytes, (int, float)):
                percent = (downloaded_bytes / total_bytes) * 100
                progress_bar = self.progress_bar(percent)
                text = (
                    f"{self.prefix_text}\n"
                    f"📥 **Downloading:** {d.get('filename', 'Video')}\n"
                    f"{progress_bar}\n"
                    f"**{percent:.1f}%** | {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes)}\n"
                    f"🚀 **Speed:** {humanbytes(speed) if speed and isinstance(speed, (int, float)) else 'N/A'}/s | ⏳ ETA: {self.format_eta(eta)}"
                )
            else:
                text = f"{self.prefix_text}\n📥 Downloading: {d.get('filename', 'Video')}\n" \
                       f"Downloaded: {humanbytes(downloaded_bytes) if downloaded_bytes and isinstance(downloaded_bytes, (int, float)) else 'N/A'}"

            asyncio.create_task(self.update_msg(text))

        elif status == 'finished':
            text = f"{self.prefix_text}\n✅ Download finished: {d.get('filename', 'Video')}\n🔄 Merging/processing..."
            asyncio.create_task(self.update_msg(text))

    async def cleanup(self):
        """Clean up the progress message after download completes."""
        if self.message:
            try:
                await self.message.delete()
                logger.info("Progress message deleted")
            except Exception as e:
                logger.error(f"Failed to delete progress message: {str(e)}")

    @staticmethod
    def progress_bar(percent, length=20):
        filled = math.floor(percent / 100 * length) if percent and isinstance(percent, (int, float)) else 0
        empty = length - filled
        return '█' * filled + '░' * empty

    @staticmethod
    def format_eta(seconds):
        if not seconds or not isinstance(seconds, (int, float)):
            return "N/A"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
