# main/downloader/progress_hook.py
import time
import asyncio
from main.utils import progress_message

last_update_time = {}

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="", edit_msg=None):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = edit_msg   # The Pyrogram message object
        self.start_time = time.time()

    async def hook(self, d):
        try:
            if d["status"] == "downloading":
                now = time.time()
                current = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 2):
                    last_update_time[self.chat_id] = now

                    await progress_message(
                        current=current,
                        total=total,
                        ud_type=self.prefix_text or "Downloading",
                        message=self.msg,
                        start=self.start_time
                    )

            elif d["status"] == "finished":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

                await progress_message(
                    current=total,
                    total=total,
                    ud_type=self.prefix_text or "Downloading",
                    message=self.msg,
                    start=self.start_time
                )

        except Exception as e:
            print(f"❌ Error in progress hook: {e}")
