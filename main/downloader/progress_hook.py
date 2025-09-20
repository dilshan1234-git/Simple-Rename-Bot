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
        self.start_time = time.time()

    def hook(self, d):
        """yt-dlp progress hook using progress_message style"""
        try:
            if d["status"] == "downloading":
                now = time.time()
                if (self.chat_id not in last_update_time) or (now - last_update_time[self.chat_id] > 3):
                    last_update_time[self.chat_id] = now
                    
                    # Safely handle None values
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    
                    # Convert to numbers safely
                    try:
                        total_bytes = float(total_bytes) if total_bytes else 0
                        downloaded = float(downloaded) if downloaded else 0
                    except (ValueError, TypeError):
                        total_bytes = downloaded = 0
                    
                    # Use progress_message function for consistent styling
                    if total_bytes > 0:
                        asyncio.create_task(
                            progress_message(
                                current=int(downloaded),
                                total=int(total_bytes),
                                ud_type=self.prefix_text,
                                message=self.msg,
                                start=self.start_time
                            )
                        )
                    
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
                
                # Update message to show completion
                if self.msg:
                    text = (
                        f"✅ **Download Completed!**\n\n"
                        f"**📂 File:** {filename}\n"
                        f"**💾 Total Size:** {humanbytes(int(total_bytes)) if total_bytes > 0 else 'Unknown'}"
                    )
                    asyncio.create_task(self._update_msg(text))
                
        except Exception as e:
            if self.msg:
                asyncio.create_task(self._update_msg(f"❌ Error in progress hook: `{str(e)}`"))

    async def _update_msg(self, text: str):
        """Update message with new text"""
        try:
            if hasattr(self.msg, 'caption') and self.msg.caption is not None:
                # Edit caption if it's a photo message
                await self.msg.edit_caption(
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Edit text if it's a text message
                await self.msg.edit_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception:
            pass
