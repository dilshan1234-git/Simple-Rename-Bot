# main/downloader/progress_hook.py
import asyncio
import time
from pyrogram.enums import ParseMode
from main.utils import humanbytes, progress_message

# Reduce global update interval for faster updates
last_update_time = {}


class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="", edit_msg=None):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = edit_msg
        self.start_time = time.time()
        self.current_data = {}
        self.update_task = None
        self.running = True
        self.last_telegram_update = 0
        self.update_interval = 0.5  # Update every 500ms for faster response
        self.telegram_limit = 1.5   # Telegram API limit every 1.5 seconds

    async def start_updater(self):
        """Start the background updater task"""
        self.update_task = asyncio.create_task(self._progress_updater())

    async def stop_updater(self):
        """Stop the background updater task"""
        self.running = False
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass

    async def _progress_updater(self):
        """Background task to update progress messages - optimized for speed"""
        consecutive_errors = 0
        max_errors = 3

        while self.running and consecutive_errors < max_errors:
            try:
                current_time = time.time()

                # Check if we have data and enough time has passed for Telegram
                # API
                if (self.current_data and self.msg and (current_time -
                        self.last_telegram_update) >= self.telegram_limit):

                    data = self.current_data.copy()

                    if data.get("status") == "downloading":
                        total_bytes = data.get("total_bytes", 0)
                        downloaded = data.get("downloaded_bytes", 0)

                        if total_bytes > 0:
                            await progress_message(
                                current=int(downloaded),
                                total=int(total_bytes),
                                ud_type=self.prefix_text,
                                message=self.msg,
                                start=self.start_time
                            )
                            self.last_telegram_update = current_time

                    elif data.get("status") == "finished":
                        filename = data.get('filename', 'Unknown')
                        if filename and len(filename) > 50:
                            filename = "..." + filename[-47:]

                        total_bytes = data.get('total_bytes', 0)
                        text = (
                            f"✅ **Download Completed!**\n\n"
                            f"**📂 File:** {filename}\n\n"
                            f"**💾 Total Size:** {humanbytes(int(total_bytes)) if total_bytes > 0 else 'Unknown'}")
                        await self._update_msg(text)
                        self.last_telegram_update = current_time
                        break

                    elif data.get("status") == "error":
                        await self._update_msg(f"❌ Error: `{data.get('error', 'Unknown error')}`")
                        break

                consecutive_errors = 0  # Reset error count on success
                await asyncio.sleep(self.update_interval)  # Fast polling

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    await self._update_msg(f"❌ Progress updater failed: `{str(e)}`")
                    break
                await asyncio.sleep(0.5)  # Short delay on error

    def hook(self, d):
        """yt-dlp progress hook - optimized for frequent updates"""
        try:
            if d["status"] == "downloading":
                # More frequent updates - every 200ms instead of 2-3 seconds
                now = time.time()
                if (self.chat_id not in last_update_time) or (
                        now - last_update_time[self.chat_id] > 0.2):
                    last_update_time[self.chat_id] = now

                    # Safely handle None values
                    total_bytes = d.get("total_bytes") or d.get(
                        "total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0

                    # Convert to numbers safely
                    try:
                        total_bytes = float(total_bytes) if total_bytes else 0
                        downloaded = float(downloaded) if downloaded else 0
                    except (ValueError, TypeError):
                        total_bytes = downloaded = 0

                    # Store data for async updater - update immediately
                    if total_bytes > 0:  # Only store valid progress
                        self.current_data = {
                            "status": "downloading",
                            "total_bytes": total_bytes,
                            "downloaded_bytes": downloaded,
                            "timestamp": now
                        }

            elif d["status"] == "finished":
                # Store finished status data immediately
                total_bytes = d.get('total_bytes', 0)
                try:
                    total_bytes = float(total_bytes) if total_bytes else 0
                except (ValueError, TypeError):
                    total_bytes = 0

                self.current_data = {
                    "status": "finished",
                    "filename": d.get('filename', 'Unknown'),
                    "total_bytes": total_bytes,
                    "timestamp": time.time()
                }

        except Exception as e:
            self.current_data = {
                "status": "error",
                "error": str(e),
                "timestamp": time.time()
            }

    async def _update_msg(self, text: str):
        """Update message with new text - optimized with retry logic"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if hasattr(
                        self.msg,
                        'caption') and self.msg.caption is not None:
                    # Edit caption if it's a photo message
                    await self.msg.edit_caption(
                        caption=text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # Edit text if it's a text message
                    await self.msg.edit_text(
                        text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                break  # Success, exit retry loop

            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    pass  # Silently fail on final attempt
                else:
                    await asyncio.sleep(0.5)  # Brief delay before retry
