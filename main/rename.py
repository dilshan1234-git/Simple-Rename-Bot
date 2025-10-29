import time
import os
from pyrogram import Client, filters, enums
from config import DOWNLOAD_LOCATION, CAPTION, ADMIN
from main.utils import progress_message, humanbytes
from moviepy.editor import VideoFileClip


@Client.on_message(filters.private & filters.command("rename")
                   & filters.user(ADMIN))
async def rename_file(bot, msg):
    reply = msg.reply_to_message
    if len(msg.command) < 2 or not reply:
        return await msg.reply_text("Please Reply To A File or video or audio with filename + .extension e.g., (.mkv or .mp4 or .zip)")
    media = reply.document or reply.audio or reply.video
    if not media:
        return await msg.reply_text("Please Reply To A File or video or audio with filename + .extension e.g., (.mkv or .mp4 or .zip)")
    og_media = getattr(reply, reply.media.value)
    new_name = msg.text.split(" ", 1)[1]
    sts = await msg.reply_text("🔄 Trying to Download.....📥")
    c_time = time.time()
    downloaded = await reply.download(file_name=new_name, progress=progress_message, progress_args=("Download Started..... **Thanks To All Who Supported ❤**", sts, c_time))
    filesize = humanbytes(og_media.file_size)

    # Get video duration
    video_clip = VideoFileClip(downloaded)
    duration = int(video_clip.duration)
    video_clip.close()

    if CAPTION:
        try:
            cap = CAPTION.format(
                file_name=new_name,
                file_size=filesize,
                duration=duration)
        except Exception as e:
            return await sts.edit(text=f"Your caption Error: unexpected keyword ●> ({e})")
    else:
        cap = f"{new_name}\n\n💽 size: {filesize}\n🕒 duration: {duration} seconds"

    dir = os.listdir(DOWNLOAD_LOCATION)
    if len(dir) == 0:
        file_thumb = await bot.download_media(og_media.thumbs[0].file_id)
        og_thumbnail = file_thumb
    else:
        try:
            og_thumbnail = f"{DOWNLOAD_LOCATION}/thumbnail.jpg"
        except Exception as e:
            print(e)
            og_thumbnail = None

    await sts.edit("🚀 Uploading started..... 📤**Thanks To All Who Supported ❤**")
    c_time = time.time()
    try:
        await bot.send_video(msg.chat.id, video=downloaded, thumb=og_thumbnail, caption=cap, duration=duration, progress=progress_message, progress_args=("Upload Started..... **Thanks To All Who Supported ❤**", sts, c_time))
    except Exception as e:
        return await sts.edit(f"Error: {e}")
