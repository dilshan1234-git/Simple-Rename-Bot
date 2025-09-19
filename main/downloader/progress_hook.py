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
        self.is_finished = False  # Track if download is finished
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    async def update_msg(self, text, retries=3, delay=1):
        # Don't update if we're finished and cleaned up
        if self.is_finished:
            return
            
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
                    logger.debug(f"Successfully updated message: {text[:50]}...")
                    return
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to update message: {str(e)}")
                if "MESSAGE_ID_INVALID" in str(e) or "MESSAGE_NOT_MODIFIED" in str(e):
                    # Message was deleted or content is the same, send a new one
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
                if attempt < retries:
                    await asyncio.sleep(delay)  # Wait before retrying
        logger.error(f"All {retries} attempts failed to update or send message")

    def hook(self, d):
        """
        Hook for youtube_dl progress updates.
        """
        if self.is_finished:
            return
            
        status = d.get('status', None)
        now = time.time()
        
        # Update more frequently for better user experience (every 3 seconds instead of 10)
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
                
                # Extract just the filename without path
                if filename:
                    filename = filename.split('/')[-1] if '/' in filename else filename
                    filename = filename.split('\\')[-1] if '\\' in filename else filename

                if total_bytes and downloaded_bytes and isinstance(total_bytes, (int, float)) and isinstance(downloaded_bytes, (int, float)) and total_bytes > 0:
                    percent = min((downloaded_bytes / total_bytes) * 100, 100)  # Cap at 100%
                    progress_bar = self.progress_bar(percent)
                    
                    text = (
                        f"{self.prefix_text}\n"
                        f"📥 **Downloading:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n"
                        f"{progress_bar}\n"
                        f"**{percent:.1f}%** | {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes)}\n"
                        f"🚀 **Speed:** {humanbytes(speed) if speed and isinstance(speed, (int, float)) and speed > 0 else 'Calculating...'}/s | ⏳ ETA: {self.format_eta(eta)}"
                    )
                else:
                    # Fallback for when total_bytes is unknown
                    text = (
                        f"{self.prefix_text}\n"
                        f"📥 **Downloading:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n"
                        f"Downloaded: {humanbytes(downloaded_bytes) if downloaded_bytes and isinstance(downloaded_bytes, (int, float)) else 'Calculating...'}\n"
                        f"🚀 **Speed:** {humanbytes(speed) if speed and isinstance(speed, (int, float)) and speed > 0 else 'Calculating...'}/s"
                    )

                # Use asyncio.run_coroutine_threadsafe to safely call async function from thread
                future = asyncio.run_coroutine_threadsafe(self.update_msg(text), self.loop)
                # Don't wait for the result to avoid blocking youtube-dl

            elif status == 'finished':
                filename = d.get('filename', 'Video')
                if filename:
                    filename = filename.split('/')[-1] if '/' in filename else filename
                    filename = filename.split('\\')[-1] if '\\' in filename else filename
                
                text = f"{self.prefix_text}\n✅ **Download finished:** {filename[:50]}{'...' if len(filename) > 50 else ''}\n🔄 **Processing and merging...**"
                future = asyncio.run_coroutine_threadsafe(self.update_msg(text), self.loop)
                # Give it a moment to update
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error in progress hook: {str(e)}")

    async def cleanup(self):
        """Clean up the progress message after download completes."""
        self.is_finished = True
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
        
        # Cap extremely large ETAs
        if seconds > 86400:  # More than 24 hours
            return "Long time"
            
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"{m:02d}:{s:02d}"
