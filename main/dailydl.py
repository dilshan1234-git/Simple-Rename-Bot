import time, os, yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes
from moviepy.editor import VideoFileClip

# yt-dlp options
ydl_opts = {
    'format': 'best',
    'outtmpl': f'{DOWNLOAD_LOCATION}/%(title)s.%(ext)s',
    'noplaylist': True,
}

# Block YouTube URLs
BLOCKED_DOMAINS = ["youtube.com", "youtu.be"]

@Client.on_message(filters.private & filters.command("daily") & filters.user(ADMIN))
async def download_yt_dlp(bot, msg):
    if len(msg.command) < 2:
        return await msg.reply_text("🔗 **Please provide a valid URL.**")
    
    url = msg.text.split(" ", 1)[1]

    # Check for blocked domains (YouTube)
    if any(domain in url for domain in BLOCKED_DOMAINS):
        return await msg.reply_text("❌ **YouTube URLs are not supported in this command.**")

    # Start message with inline keyboard for interaction
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Status", callback_data="show_status")],
        [InlineKeyboardButton("🗑️ Cancel", callback_data="cancel")]
    ])
    sts = await msg.reply_text(f"🔄 **Processing:** `{url}`\n\n🌐 *Checking the link and starting download...*", reply_markup=keyboard)

    # Downloading with yt-dlp
    try:
        await sts.edit("🔄 **Downloading... Please wait...**")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get('title', None)
            ext = info_dict.get('ext', None)
            downloaded = ydl.download([url])
            file_path = f"{DOWNLOAD_LOCATION}/{title}.{ext}"
            file_size = os.path.getsize(file_path)

        # Inform about download completion
        await sts.edit(f"✅ **Downloaded successfully!**\n\n📤 **Uploading to Telegram...**", reply_markup=None)

    except Exception as e:
        print(f"Error during download: {str(e)}")  # Debug print for logging
        return await sts.edit(f"❌ **Download failed:** `{str(e)}`")

    # Get video duration and thumbnail
    try:
        video_clip = VideoFileClip(file_path)
        duration = int(video_clip.duration)
        video_clip.close()
    except Exception as e:
        print(f"Error during video processing: {str(e)}")
        return await sts.edit(f"❌ **Error processing video:** `{str(e)}`")

    # Custom Caption
    filesize = humanbytes(file_size)
    cap = f"**{title}**\n\n💽 **Size:** `{filesize}`\n🕒 **Duration:** `{duration} seconds`"

    # Fetch thumbnail if available
    thumbnail = None
    if info_dict.get('thumbnail'):
        thumbnail = f"{DOWNLOAD_LOCATION}/thumbnail.jpg"
        os.system(f"wget {info_dict['thumbnail']} -O {thumbnail}")

    c_time = time.time()

    # Upload to Telegram
    try:
        await bot.send_video(
            msg.chat.id,
            video=file_path,
            thumb=thumbnail,
            caption=cap,
            duration=duration,
            progress=progress_message,
            progress_args=("Upload Started... 📤", sts, c_time)
        )
    except Exception as e:
        print(f"Error during upload: {str(e)}")
        return await sts.edit(f"❌ **Upload failed:** `{str(e)}`")

    # Cleanup after upload
    try:
        if thumbnail:
            os.remove(thumbnail)
        os.remove(file_path)
    except Exception as e:
        print(f"Error during cleanup: {e}")

    await sts.delete()

# Inline keyboard button handler
@Client.on_callback_query(filters.regex("show_status"))
async def show_status_callback(bot, callback_query):
    await callback_query.answer("📊 Current Status: Download/Upload in progress...")

@Client.on_callback_query(filters.regex("cancel"))
async def cancel_callback(bot, callback_query):
    await callback_query.message.edit("🛑 **Download/Upload canceled.**")
