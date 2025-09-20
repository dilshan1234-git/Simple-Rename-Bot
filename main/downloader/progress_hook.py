# main/downloader/progress_hook.py
import asyncio
import time
from pyrogram.enums import ParseMode
from main.utils import humanbytes, progress_message

last_update_time = {}

class YTDLProgress:
    def __init__(self, bot, chat_id, prefix_text="", edit_msg=None):
        self.bot = bot
        self.chat_id = chat_id
        self.prefix_text = prefix_text
        self.msg = edit_msg  # If provided, edit this message instead of creating new one
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
                if hasattr(self.msg, 'caption') and self.msg.caption is not None:
                    # Edit caption if it's a photo message
                    await self.msg.edit_caption(
                        caption=f"{self.prefix_text}\n\n{text}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # Edit text if it's a text message
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
                    
                    # Safely handle None values
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    speed = d.get("speed") or 0
                    eta = d.get("eta") or 0
                    
                    # Convert to numbers safely
                    try:
                        total_bytes = float(total_bytes) if total_bytes else 0
                        downloaded = float(downloaded) if downloaded else 0
                        speed = float(speed) if speed else 0
                        eta = float(eta) if eta else 0
                    except (ValueError, TypeError):
                        total_bytes = downloaded = speed = eta = 0
                    
                    # Use same style as uploading progress
                    text = progress_message(
                        current=downloaded,
                        total=total_bytes,
                        speed=speed,
                        eta=eta,
                        prefix="Downloading"
                    )
                    self.enqueue(text)
                    
            elif d["status"] == "finished":
                # Safely handle finished status
                filename = d.get('filename', 'Unknown')
                if filename and len(filename) > 50:
                    filename = "..." + filename[-47:]  # Truncate long filenames
                
                total_bytes = d.get('total_bytes') or 0
                try:
                    total_bytes = float(total_bytes) if total_bytes else 0
                except (ValueError, TypeError):
                    total_bytes = 0
                
                text = (
                    f"✅ **Download Completed!**\n\n"
                    f"**📂 File:** {filename}\n"
                    f"**💾 Total Size:** {humanbytes(int(total_bytes)) if total_bytes > 0 else 'Unknown'}"
                )
                self.enqueue(text)
                
        except Exception as e:
            self.enqueue(f"❌ Error in progress hook: `{str(e)}`")

    async def cleanup(self):
        """Cleanup background task"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except Exception:
                pass
