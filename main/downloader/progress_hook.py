# main/downloader/progress_hook.py
import asyncio
import time
from pyrogram.enums import ParseMode
from main.utils import progress_message, humanbytes

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

    async def process_queue(self):
        """Process queue asynchronously using progress_message style"""
        while True:
            try:
                current, total = await self.queue.get()
                await progress_message(
                    current=current,
                    total=total,
                    ud_type=self.prefix_text,
                    message=self.msg,
                    start=self.start_time
                )
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def enqueue(self, current, total):
        """Enqueue numeric data for progress_message style"""
        if not self.queue.full():
            self.queue.put_nowait((current, total))

    def hook(self, d):
        """yt-dlp progress hook"""
        try:
            status = d.get("status", None)

            if status == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 1):
                    last_update_time[self.chat_id] = now

                    downloaded = d.get("downloaded_bytes") or 0
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

                    # Ensure numeric values
                    try:
                        downloaded = float(downloaded)
                        total_bytes = float(total_bytes)
                    except (ValueError, TypeError):
                        downloaded = total_bytes = 0

                    if total_bytes > 0:
                        self.enqueue(downloaded, total_bytes)

            elif status == "finished":
                filename = d.get('filename', 'Unknown')
                total_bytes = d.get('total_bytes') or 0
                try:
                    total_bytes = float(total_bytes)
                except (ValueError, TypeError):
                    total_bytes = 0

                # Final progress as 100%
                self.enqueue(total_bytes, total_bytes)

        except Exception as e:
            # If hook crashes, enqueue a minimal message
            print(f"❌ Progress hook error: {str(e)}")

    async def cleanup(self):
        """Cleanup background task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
