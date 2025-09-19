# main/downloader/progress_hook.py

import time
from pyrogram.enums import ParseMode
from main.utils import humanbytes

last_update_time = {}

class YTDLProgress:
    def __init__(self, message, start_time):
        self.message = message
        self.start_time = start_time

    async def hook(self, d):
        try:
            if d["status"] == "downloading":
                now = time.time()
                if (self.message.id not in last_update_time) or (now - last_update_time[self.message.id] > 3):
                    last_update_time[self.message.id] = now

                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                    downloaded = d.get("downloaded_bytes", 0)
                    speed = d.get("speed", 0)
                    eta = d.get("eta", 0)

                    percent = (downloaded * 100 / total_bytes) if total_bytes else 0

                    text = f"""
<b>📥 Downloading...</b>

<b>File:</b> {d.get('filename', 'Unknown')}
<b>Progress:</b> {percent:.2f}%
<b>Downloaded:</b> {humanbytes(downloaded)} / {humanbytes(total_bytes) if total_bytes else "?"}
<b>Speed:</b> {humanbytes(speed)}/s
<b>ETA:</b> {time.strftime('%H:%M:%S', time.gmtime(eta))}
"""

                    try:
                        await self.message.edit_text(text, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass

            elif d["status"] == "finished":
                text = f"""
<b>✅ Download Completed!</b>

<b>File:</b> {d.get('filename', 'Unknown')}
<b>Total Size:</b> {humanbytes(d.get("total_bytes", 0))}
"""
                try:
                    await self.message.edit_text(text, parse_mode=ParseMode.HTML)
                except Exception:
                    pass

        except Exception as e:
            try:
                await self.message.edit_text(
                    f"❌ Error in progress hook: <code>{e}</code>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
