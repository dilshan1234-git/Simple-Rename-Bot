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
    Splits video into parts if it exceeds Telegram's ~2GB limit.
    Returns list of split file paths.
    """
    MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
    video_size = os.path.getsize(video_path)

    if video_size <= MAX_SIZE:
        return [video_path]

    # Open video
    try:
        video = VideoFileClip(video_path)
        duration = video.duration  # in seconds
    except Exception as e:
        await bot.send_message(
            chat_id,
            f"❌ Error opening video for splitting: {str(e)}"
        )
        return []

    # Calculate approx split duration per part
    num_parts = int(video_size // MAX_SIZE) + 1
    part_duration = duration / num_parts

    split_files = []
    for i in range(num_parts):
        start = i * part_duration
        end = min((i + 1) * part_duration, duration)
        part_file = f"{os.path.splitext(video_path)[0]}_Part {str(i+1).zfill(2)}.mp4"
        try:
            clip = video.subclip(start, end)
            clip.write_videofile(
                part_file,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile="temp-audio.m4a",
                remove_temp=True,
                verbose=False,
                logger=None
            )
            clip.close()
            split_files.append(part_file)
        except Exception as e:
            await bot.send_message(
                chat_id,
                f"❌ Error creating part {i+1}: {str(e)}"
            )

    video.close()
    return split_files
