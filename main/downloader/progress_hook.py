# main/downloader/progress_hook.py

import asyncio
import time
from main.utils import progress_message

class ProgressHook:
    def __init__(self, message, start_time):
        self.message = message
        self.start_time = start_time
        self.last_update = time.time()

    async def hook(self, d):
        """yt-dlp progress hook"""
        if d["status"] == "downloading":
            current = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

            # throttle updates (avoid spamming every millisecond)
            if time.time() - self.last_update >= 2 or current == total:
                self.last_update = time.time()
                try:
                    await progress_message(
                        current=current,
                        total=total,
                        ud_type="Downloading",  # same style as uploading
                        message=self.message,
                        start=self.start_time
                    )
                except Exception as e:
                    print(f"progress update error: {e}")

        elif d["status"] == "finished":
            # Final update to 100%
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            try:
                await progress_message(
                    current=total,
                    total=total,
                    ud_type="Downloading",
                    message=self.message,
                    start=self.start_time
                )
            except:
                pass
