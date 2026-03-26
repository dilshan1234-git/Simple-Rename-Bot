import os
import asyncio
from moviepy.editor import VideoFileClip
from main.utils import humanbytes, progress_message

# Escape Markdown v2 special characters
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!:"  # Telegram Markdown V2
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

# Ensure download folder exists
os.makedirs("split_temp", exist_ok=True)

async def split_video(bot, chat_id, video_path, title, resolution, thumb_path=None):
    """
    Split large videos into multiple parts if needed (for Telegram upload limits),
    handle special characters in titles to avoid markdown issues,
    and prevent re-download/re-split if files already exist.
    """

    # Clean title for markdown
    safe_title = escape_markdown(title)

    # Max Telegram upload size per video in bytes (~2GB)
    MAX_SIZE = 2 * 1024 * 1024 * 1024

    video_size = os.path.getsize(video_path)
    if video_size <= MAX_SIZE:
        # No split needed
        return [video_path]

    # If already split, skip re-splitting
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    split_dir = os.path.join("split_temp", base_name)
    os.makedirs(split_dir, exist_ok=True)

    existing_files = sorted([os.path.join(split_dir, f) for f in os.listdir(split_dir) if f.endswith(".mp4")])
    if existing_files:
        return existing_files

    # Load video
    try:
        clip = VideoFileClip(video_path)
    except Exception as e:
        await bot.send_message(chat_id, f"❌ **Error loading video for splitting:** {str(e)}")
        return [video_path]

    duration = clip.duration
    total_size = os.path.getsize(video_path)
    num_parts = int(total_size // MAX_SIZE) + 1
    part_duration = duration / num_parts

    split_files = []
    for i in range(num_parts):
        start = i * part_duration
        end = min((i + 1) * part_duration, duration)
        part_clip = clip.subclip(start, end)
        part_file = os.path.join(split_dir, f"{base_name}_part{i+1}.mp4")
        try:
            part_clip.write_videofile(part_file, codec="libx264", audio_codec="aac", verbose=False, logger=None)
            split_files.append(part_file)
        except Exception as e:
            await bot.send_message(chat_id, f"❌ **Error creating split part {i+1}:** {str(e)}")
        finally:
            part_clip.close()

    clip.close()
    return split_files
