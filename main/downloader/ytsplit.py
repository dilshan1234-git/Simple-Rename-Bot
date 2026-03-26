import os
from moviepy.editor import VideoFileClip
from main.utils import humanbytes

# Escape Markdown v2 special characters
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!:"  # Telegram Markdown V2
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

async def split_video(bot, chat_id, video_path, title, resolution, thumb_path=None):
    """
    Handles splitting, but now checks Telegram upload size AFTER download.
    If video exceeds limit (~2GB), sends a message and skips upload.
    """
    # Max Telegram upload size per video in bytes (~2GB)
    MAX_SIZE = 2 * 1024 * 1024 * 1024
    video_size = os.path.getsize(video_path)

    if video_size <= MAX_SIZE:
        # No split needed, return the downloaded file itself
        return [video_path]
    else:
        # File too big
        safe_title = escape_markdown(title)
        await bot.send_message(
            chat_id,
            f"❌ **Download completed, but the video is too large for Telegram!**\n"
            f"**🎞 {safe_title}** | Size: **{humanbytes(video_size)}**\n\n"
            f"Try a lower resolution or split manually."
        )
        # Return empty list to skip upload
        return []
