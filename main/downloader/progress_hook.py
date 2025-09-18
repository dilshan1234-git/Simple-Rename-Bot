# main/downloader/progress_hook.py
import time
import math
import asyncio
from main.utils import humanbytes

class YTDLProgress:
    def __init__(self, bot, message, prefix_text=""):
        self.bot = bot
        self.message = message
        self.prefix_text = prefix_text
        self.last_update_time = 0
        self.loop = asyncio.get_event_loop()

    async def update_msg(self, text):
        try:
            await self.message.edit_text(text)
        except Exception:
            pass

    def hook(self, d):
        """
        Hook for youtube_dl progress updates.
        """
        status = d.get('status', None)
        now = time.time()
        if now - self.last_update_time < 1:
            return
        self.last_update_time = now

        if status == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)

            if total_bytes:
                percent = downloaded_bytes / total_bytes * 100
                progress_bar = self.progress_bar(percent)
                text = (
                    f"{self.prefix_text}\n"
                    f"📥 **Downloading:** {d.get('filename', 'Video')}\n"
                    f"{progress_bar}\n"
                    f"**{percent:.1f}%** | {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes)}\n"
                    f"🚀 **Speed:** {humanbytes(speed)}/s | ⏳ ETA: {self.format_eta(eta)}"
                )
            else:
                text = f"{self.prefix_text}\n📥 Downloading: {d.get('filename', 'Video')}\n" \
                       f"Downloaded: {humanbytes(downloaded_bytes)}"

            asyncio.ensure_future(self.update_msg(text), loop=self.loop)

        elif status == 'finished':
            text = f"{self.prefix_text}\n✅ Download finished: {d.get('filename', 'Video')}\n🔄 Merging/processing..."
            asyncio.ensure_future(self.update_msg(text), loop=self.loop)

    @staticmethod
    def progress_bar(percent, length=20):
        filled = math.floor(percent / 100 * length)
        empty = length - filled
        return '█' * filled + '░' * empty

    @staticmethod
    def format_eta(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
