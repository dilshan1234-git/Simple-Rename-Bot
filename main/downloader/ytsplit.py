import os
import math
import subprocess
from main.utils import humanbytes

# Safe margin (Telegram limit ~2GB → keep ~1.95GB)
MAX_SIZE = int(1.95 * 1024 * 1024 * 1024)


async def split_video(bot, chat_id, file_path, title, resolution, thumb_path):
    total_size = os.path.getsize(file_path)

    # No split needed
    if total_size <= MAX_SIZE:
        return [file_path]

    total_size_hr = humanbytes(total_size)

    # Get duration using ffprobe
    duration_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    duration = float(subprocess.check_output(duration_cmd).decode().strip())

    # Calculate size per second (VERY IMPORTANT)
    size_per_sec = total_size / duration

    # Calculate safe duration per part
    part_duration = MAX_SIZE / size_per_sec

    # Calculate number of parts
    parts = math.ceil(duration / part_duration)

    # 🔥 Stylish message
    await bot.send_message(
        chat_id,
        f"⚠️ **SIZE LIMIT EXCEEDED**\n\n"
        f"📦 **Total Size:** `{total_size_hr}`\n"
        f"🧠 **Smart Splitting Enabled**\n"
        f"✂️ **Estimated Parts:** `{parts}`\n\n"
        f"⚡ **Splitting without re-encoding (Ultra Fast)**",
        parse_mode="markdown"
    )

    output_files = []

    for i in range(parts):
        start_time = i * part_duration

        output_file = file_path.replace(".mp4", f"_part{i+1}.mp4")

        split_cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_time),   # FAST SEEK
            "-i", file_path,
            "-t", str(part_duration),
            "-c", "copy",             # NO RE-ENCODE (VERY FAST)
            "-avoid_negative_ts", "1",
            output_file
        ]

        subprocess.run(split_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 🔥 Extra safety check (rare case)
        if os.path.getsize(output_file) > MAX_SIZE:
            # fallback: reduce duration slightly
            reduced_duration = part_duration * 0.95

            split_cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(start_time),
                "-i", file_path,
                "-t", str(reduced_duration),
                "-c", "copy",
                "-avoid_negative_ts", "1",
                output_file
            ]
            subprocess.run(split_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        output_files.append(output_file)

    return output_files
