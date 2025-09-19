# main/downloader/progress_hook.py

import asyncio
import logging
from queue import Queue

logger = logging.getLogger(__name__)

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="Downloading: "):
        """
        :param bot: Pyrogram Client (for sending edits)
        :param chat_id: Chat where progress will be sent
        :param prefix_text: Prefix shown in progress messages
        """
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.progress_queue = Queue()
        self.active = True
        self.task = None

        # Message object to update later
        self.msg = None

    async def bind(self, msg):
        """Bind to a Telegram message to edit progress"""
        self.msg = msg

    async def start(self):
        """Start processing the queue asynchronously"""
        self.task = asyncio.create_task(self.process_queue())

    async def stop(self):
        """Stop queue processing and cleanup"""
        self.active = False
        if self.task:
            await self.task
        await self.cleanup()

    async def process_queue(self):
        """Process the queue and update message in Telegram"""
        while self.active:
            if not self.progress_queue.empty() and self.msg:
                text = self.progress_queue.get()
                try:
                    await self.msg.edit_text(text)
                except Exception as e:
                    logger.error(f"Error updating message: {e}")
            await asyncio.sleep(2)  # smoother updates

    async def cleanup(self):
        """Flush remaining messages before shutdown"""
        while not self.progress_queue.empty() and self.msg:
            text = self.progress_queue.get()
            try:
                await self.msg.edit_text(text)
            except Exception as e:
                logger.error(f"Error in cleanup: {e}")

    def hook(self, d):
        """yt_dlp progress hook"""
        if d["status"] == "downloading":
            try:
                percent = d.get("_percent_str", "").strip()
                speed = d.get("_speed_str", "").strip()
                eta = d.get("_eta_str", "").strip()

                text = (
                    f"{self.prefix_text}\n"
                    f"📥 Progress: {percent}\n"
                    f"⚡ Speed: {speed}\n"
                    f"⏳ ETA: {eta}"
                )

                # ✅ Queue update for Telegram
                self.progress_queue.put(text)

                # ✅ Also log to Colab in real time
                logger.info(f"[YTDL] {text.replace(self.prefix_text, '').strip()[:80]}...")
                print(f"[YTDL] {text.replace(self.prefix_text, '').strip()[:80]}...", flush=True)

            except Exception as e:
                logger.error(f"Error in hook: {e}")
