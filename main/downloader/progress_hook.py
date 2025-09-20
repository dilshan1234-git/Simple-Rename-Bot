# main/downloader/progress_hook.py
import asyncio
import time
from main.utils import progress_message, humanbytes

last_update_time = {}

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="", edit_msg=None):
        """
        bot: pyrogram Client
        chat_id: chat where progress should be displayed
        prefix_text: text to prepend to progress message
        edit_msg: optional message object to edit instead of sending new
        """
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = edit_msg
        self.queue = asyncio.Queue()
        self.update_task = None

    async def update_msg(self, text: str):
        """Send or edit a message with the current progress"""
        if self.msg is None:
            self.msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"{self.prefix_text}\n\n{text}"
            )
        else:
            try:
                if hasattr(self.msg, 'caption') and self.msg.caption is not None:
                    await self.msg.edit_caption(
                        caption=f"{self.prefix_text}\n\n{text}"
                    )
                else:
                    await self.msg.edit_text(
                        f"{self.prefix_text}\n\n{text}"
                    )
            except Exception:
                pass

    async def process_queue(self):
        """Continuously process the queue and update the message"""
        while True:
            try:
                text = await self.queue.get()
                await self.update_msg(text)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def enqueue(self, text: str):
        """Add a progress text to the queue"""
        if not self.queue.full():
            self.queue.put_nowait(text)

    def hook(self, d):
        """yt-dlp progress hook"""
        try:
            status = d.get("status")
            if status == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 2):
                    last_update_time[self.chat_id] = now

                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    speed = d.get("speed") or 0
                    eta = d.get("eta") or 0

                    total_bytes = float(total_bytes) if total_bytes else 0
                    downloaded = float(downloaded) if downloaded else 0
                    speed = float(speed) if speed else 0
                    eta = float(eta) if eta else 0

                    text = f"{downloaded}|{total_bytes}|{speed}|{eta}"
                    self.enqueue(text)

            elif status == "finished":
                filename = d.get("filename", "Unknown")
                total_bytes = d.get("total_bytes") or 0
                total_bytes = float(total_bytes) if total_bytes else 0

                text = (
                    f"✅ **Download Completed!**\n\n"
                    f"**📂 File:** {filename}\n"
                    f"**💾 Total Size:** {humanbytes(int(total_bytes)) if total_bytes > 0 else 'Unknown'}"
                )
                self.enqueue(text)
        except Exception as e:
            self.enqueue(f"❌ Error in progress hook: `{str(e)}`")

    async def cleanup(self):
        """Cancel the queue processing task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
