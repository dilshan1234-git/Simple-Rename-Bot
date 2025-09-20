# main/downloader/progress_hook.py
import asyncio
import time
from main.utils import progress_message, humanbytes

last_update_time = {}

class YTDLProgress:
    def __init__(self, bot, chat_id, ud_type="", message_obj=None):
        """
        bot: pyrogram Client
        chat_id: chat where progress should be displayed
        ud_type: Upload/Download type text (like "📥 Downloading...")
        message_obj: message object to edit
        """
        self.bot = bot
        self.chat_id = chat_id
        self.ud_type = ud_type
        self.msg = message_obj
        self.queue = asyncio.Queue()
        self.update_task = None
        self.start_time = time.time()

    async def process_queue(self):
        """Continuously process the queue and update the message"""
        while True:
            try:
                item = await self.queue.get()
                current, total = item[:2]
                await progress_message(current, total, self.ud_type, self.msg, self.start_time)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def enqueue(self, current, total):
        """Add numbers for progress_message"""
        if not self.queue.full():
            self.queue.put_nowait((current, total))

    def hook(self, d):
        """yt-dlp progress hook"""
        try:
            status = d.get("status")
            if status == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 2):
                    last_update_time[self.chat_id] = now

                    downloaded = d.get("downloaded_bytes") or 0
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

                    downloaded = float(downloaded)
                    total_bytes = float(total_bytes)

                    if total_bytes > 0:
                        self.enqueue(downloaded, total_bytes)

            elif status == "finished":
                filename = d.get("filename", "Unknown")
                total_bytes = d.get("total_bytes") or 0
                total_bytes = float(total_bytes)

                # Send final progress as full
                self.enqueue(total_bytes, total_bytes)

        except Exception as e:
            pass  # optional: handle errors

    async def cleanup(self):
        """Cancel the queue processing task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
