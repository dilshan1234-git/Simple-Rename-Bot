# main/downloader/progress_hook.py

import asyncio
import time
from pyrogram.enums import ParseMode
from main.utils import humanbytes

last_update_time = {}


class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text=""):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = None
        self.queue = asyncio.Queue()
        self.update_task = None

    async def update_msg(self, text: str):
        """Send or edit progress message"""
        if self.msg is None:
            self.msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"{self.prefix_text}\n\n{text}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            try:
                await self.msg.edit_text(
                    f"{self.prefix_text}\n\n{text}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

    async def process_queue(self):
        """Process queue updates asynchronously"""
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
        """Enqueue message text for later processing"""
        if not self.queue.full():
            self.queue.put_nowait(text)

    def hook(self, d):
        """yt-dlp progress hook"""
        try:
            if d["status"] == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 3):
                    last_update_time[self.chat_id] = now

                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                    downloaded = d.get("downloaded_bytes", 0)
                    speed = d.get("speed", 0)
                    eta = d.get("eta", 0)

                    percent = (downloaded * 100 / total_bytes) if total_bytes else 0

                    text = (
                        f"📥 **Downloading...**\n\n"
                        f"**Progress:** {percent:.2f}%\n"
                        f"**Downloaded:** {humanbytes(downloaded)} / {humanbytes(total_bytes) if total_bytes else '?'}\n"
                        f"**Speed:** {humanbytes(speed)}/s\n"
                        f"**ETA:** {time.strftime('%H:%M:%S', time.gmtime(eta))}"
                    )

                    self.enqueue(text)

            elif d["status"] == "finished":
                text = (
                    f"✅ **Download Completed!**\n\n"
                    f"**File:** {d.get('filename', 'Unknown')}\n"
                    f"**Total Size:** {humanbytes(d.get('total_bytes', 0))}"
                )
                self.enqueue(text)

        except Exception as e:
            self.enqueue(f"❌ Error in progress hook: `{e}`")

    async def cleanup(self):
        """Cleanup background task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
