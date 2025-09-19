# main/downloader/progress_hook.py

import asyncio
import logging
from queue import Queue

logger = logging.getLogger(__name__)

class YTDLProgress:
    def __init__(self, update_msg, prefix_text="Downloading: "):
        """
        :param update_msg: async function to update Telegram message
        :param prefix_text: prefix shown in progress messages
        """
        self.update_msg = update_msg
        self.prefix_text = prefix_text
        self.progress_queue = Queue()
        self.active = True
        self.task = None

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
            if not self.progress_queue.empty():
                text = self.progress_queue.get()
                try:
                    await self.update_msg(text)
                except Exception as e:
                    logger.error(f"Error updating message: {e}")
            await asyncio.sleep(2)  # ✅ faster updates (was 4)

    async def cleanup(self):
        """Flush remaining messages before shutdown"""
        while not self.progress_queue.empty():
            text = self.progress_queue.get()
            try:
                await self.update_msg(text)
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
