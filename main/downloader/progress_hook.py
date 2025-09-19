import time
import math
import asyncio
import logging
from queue import Queue
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
        self.message = None
        self.is_finished = False
        self.progress_queue = Queue()  # Queue for buffering progress updates
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        self.update_task = None  # Track the update task

    async def update_msg(self, text):
        """Update or send the progress message with retry logic."""
        if self.is_finished:
            return

        retries = 3
        attempt = 0
        while attempt < retries:
            try:
                if self.message is None:
                    self.message = await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                    logger.info(f"Sent initial progress message: {text[:50]}...")
                    return
                else:
                    await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                    logger.debug(f"Successfully updated message: {text[:50]}...")
                    return
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to update message: {str(e)}")
                if "MESSAGE_ID_INVALID" in str(e) or "MESSAGE_NOT_MODIFIED" in str(e):
                    self.message = None
                    try:
                        self.message = await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=text,
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                        logger.info("Sent new message due to invalid/unmodified message")
                        return
                    except Exception as e:
                        logger.error(f"Failed to send new message: {str(e)}")
                attempt += 1
                await asyncio.sleep(1)
        logger.error(f"All {retries} attempts failed to update or send message")

    async def process_queue(self):
        """Process progress updates from the queue with rate limiting."""
        while not self.is_finished:
            if not self.progress_queue.empty():
                text = self.progress_queue.get()
                logger.info(f"Processing queue update: {text[:50]}...")  # Log to Colab
                await self.update_msg(text)
                await asyncio.sleep(3)  # Rate limit to avoid Telegram throttling
            else:
                await asyncio.sleep(0.5)  # Avoid busy-waiting

    def hook(self, d):
        """Hook for youtube_dl progress updates."""
        if self.is_finished:
            return

        status = d.get('status', None)
        now = time.time()

        # Update every 3 seconds for downloading, 1 second for other statuses
        if status == 'downloading' and now - self.last_update_time < 3:
            return
        elif status != 'downloading' and now - self.last_update_time < 1:
            return

        self.last_update_time = now

        try:
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                filename = d.get('filename', 'Video')

                if filename:
                    filename = filename.split('/')[-1] if '/' in filename else filename
                    filename = filename.split('\\')[-1] if '\\' in filename else filename

                if total_bytes and downloaded_bytes and isinstance(total_bytes, (int, float)) and isinstance(downloaded_bytes, (int, float)) and total_bytes > 0:
                    percent = min((downloaded_bytes / total_bytes) * 100, 100)
                    progress_bar = self.progress_bar(percent)
                    text = (
                        f"{self.prefix_text}\n"
                        f"📥 **Downloading:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n"
                        f"{progress_bar}\n"
                        f"**{percent:.1f}%** | {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes)}\n"
                        f"🚀 **Speed:** {humanbytes(speed) if speed and isinstance(speed, (int, float)) and speed > 0 else 'Calculating...'}/s | ⏳ ETA: {self.format_eta(eta)}"
                    )
                else:
                    text = (
                        f"{self.prefix_text}\n"
                        f"📥 **Downloading:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n"
                        f"Downloaded: {humanbytes(downloaded_bytes) if downloaded_bytes and isinstance(downloaded_bytes, (int, float)) else 'Calculating...'}\n"
                        f"🚀 **Speed:** {humanbytes(speed) if speed and isinstance(speed, (int, float)) and speed > 0 else 'Calculating...'}/s"
                    )
            elif status == 'finished':
                filename = d.get('filename', 'Video')
                if filename:
                    filename = filename.split('/')[-1] if '/' in filename else filename
                    filename = filename.split('\\')[-1] if '\\' in filename else filename
                text = f"{self.prefix_text}\n✅ **Download finished:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n🔄 **Processing and merging...**"
            else:
                return

            logger.info(f"Queueing update: {text[:50]}...")  # Log to Colab
            self.progress_queue.put(text)  # Queue the update

        except Exception as e:
            logger.error(f"Error in progress hook: {str(e)}")

    async def cleanup(self):
        """Clean up the progress message and stop the queue processor."""
        self.is_finished = True
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        if self.message:
            try:
                await self.message.delete()
                logger.info("Progress message deleted successfully")
                self.message = None
            except Exception as e:
                logger.error(f"Failed to delete progress message: {str(e)}")

    @staticmethod
    def progress_bar(percent, length=20):
        if not percent or not isinstance(percent, (int, float)):
            return '░' * length
        filled = max(0, min(math.floor(percent / 100 * length), length))
        empty = length - filled
        return '█' * filled + '░' * empty

    @staticmethod
    def format_eta(seconds):
        if not seconds or not isinstance(seconds, (int, float)) or seconds <= 0:
            return "Calculating..."
        if seconds > 86400:
            return "Long time"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
