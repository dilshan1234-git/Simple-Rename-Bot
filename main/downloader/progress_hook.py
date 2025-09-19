# main/downloader/progress_hook.py

import os
import math
import time
from pyrogram.enums import ParseMode
from main.utils import progress_message, humanbytes

# Dictionary to track last update time for each message
last_update_time = {}

async def progress_hook(d, message, start_time):
    """
    Hook for yt_dlp progress reporting.
    Updates the Telegram message with download progress.
    """
    try:
        if d["status"] == "downloading":
            now = time.time()
            # Avoid too frequent updates (every 3 seconds)
            if (message.id not in last_update_time) or (now - last_update_time[message.id] > 3):
                last_update_time[message.id] = now

                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)

                percent = 0
                if total_bytes and total_bytes > 0:
                    percent = downloaded_bytes * 100 / total_bytes

                text = f"""
<b>📥 Downloading...</b>

<b>File:</b> {d.get('filename', 'Unknown')}
<b>Progress:</b> {percent:.2f}%
<b>Downloaded:</b> {humanbytes(downloaded_bytes)} / {humanbytes(total_bytes) if total_bytes else "?"}
<b>Speed:</b> {humanbytes(speed)}/s
<b>ETA:</b> {time.strftime('%H:%M:%S', time.gmtime(eta))}
"""

                try:
                    await message.edit_text(
                        text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass

        elif d["status"] == "finished":
            text = f"""
<b>✅ Download Completed!</b>

<b>File:</b> {d.get('filename', 'Unknown')}
<b>Total Size:</b> {humanbytes(d.get("total_bytes", 0))}
"""
            try:
                await message.edit_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except Exception:
                pass

    except Exception as e:
        try:
            await message.edit_text(
                f"❌ Error in progress hook: <code>{e}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
