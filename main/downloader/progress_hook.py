import time
import math
import asyncio
import logging
from pyrogram import enums  # Import enums from pyrogram
from main.utils import humanbytes

# Set up logging to debug issues with message updates
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YTDLProgress:
    def __init__(self, bot, message, prefix_text=""):
        self.bot = bot
        self.message = message
        self.prefix_text = prefix_text
        self.last_update_time = 0
        self.loop = asyncio.get_event_loop()

    async def update_msg(self, text):
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
            logger.info(f"Successfully updated message: {text[:50]}...")
        except Exception as e:
            logger.error(f"Failed to update message: {str(e)}")
            # Fallback: Send a new message if edit fails
            try:
                self.message = await self.bot.send_message(
                    chat_id=self.message.chat.id,
                    text=text,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                logger.info("Sent new message as fallback")
            except Exception as e:
                logger.error(f"Failed to send fallback message: {str(e)}")

    def hook(self, d):
        """
        Hook for youtube_dl progress updates.
        """
        status = d.get('status', None)
        now = time.time()
        if now - self.last_update_time < 1:
            return
        self.last_update_time = now

        if status == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)

            # Ensure values are not None and are numeric before processing
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

            asyncio.run_coroutine_threadsafe(self.update_msg(text), self.loop)

        elif status == 'finished':
            text = f"{self.prefix_text}\n✅ Download finished: {d.get('filename', 'Video')}\n🔄 Merging/processing..."
            asyncio.run_coroutine_threadsafe(self.update_msg(text), self.loop)

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
