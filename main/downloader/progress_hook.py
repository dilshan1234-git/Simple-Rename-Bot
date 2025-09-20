# main/downloader/progress_hook.py
import asyncio
import time
from pyrogram.enums import ParseMode
from main.utils import humanbytes, progress_message

last_update_time = {}

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="", edit_msg=None):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = edit_msg  # If provided, edit this message instead of creating new one
        self.queue = asyncio.Queue()
        self.update_task = None
        self.start_time = time.time()

    async def update_msg(self, coro):
        """Send or edit progress message"""
        if self.msg is None:
            self.msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"{self.prefix_text}\n\n⏳ Starting download...",
                parse_mode=ParseMode.MARKDOWN
            )
        try:
            # run the progress_message coroutine (it edits self.msg)
            await coro
        except Exception:
            pass

    async def process_queue(self):
        """Process queue updates asynchronously"""
        while True:
            try:
                coro = await self.queue.get()
                await self.update_msg(coro)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def enqueue(self, coro):
        """Enqueue coroutine for later processing"""
        if not self.queue.full():
            self.queue.put_nowait(coro)

    def hook(self, d):
        """yt-dlp progress hook"""
        try:
            if d["status"] == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 3):
                    last_update_time[self.chat_id] = now
                    
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0

                    # enqueue the coroutine for consistent upload-style progress
                    self.enqueue(
                        progress_message(
                            current=downloaded,
                            total=total_bytes,
                            ud_type="📥 Downloading...",
                            message=self.msg,
                            start=self.start_time
                        )
                    )
                    
            elif d["status"] == "finished":
                # Safely handle finished status
                filename = d.get('filename', 'Unknown')
                if filename and len(filename) > 50:
                    filename = "..." + filename[-47:]  # Truncate long filenames
                
                total_bytes = d.get('total_bytes') or 0
                try:
                    total_bytes = float(total_bytes) if total_bytes else 0
                except (ValueError, TypeError):
                    total_bytes = 0
                
                completed_text = (
                    f"✅ **Download Completed!**\n\n"
                    f"**📂 File:** {filename}\n"
                    f"**💾 Total Size:** {humanbytes(int(total_bytes)) if total_bytes > 0 else 'Unknown'}"
                )
                self.enqueue(self.msg.edit_text(completed_text, parse_mode=ParseMode.MARKDOWN))
                
        except Exception as e:
            # show error as plain text edit
            self.enqueue(self.msg.edit_text(f"❌ Error in progress hook: `{str(e)}`"))

    async def cleanup(self):
        """Cleanup background task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
