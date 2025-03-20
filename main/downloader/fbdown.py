import os
import time
import yt_dlp
from pyrogram import Client, filters
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

@Client.on_message(filters.private & filters.command("fbdl") & filters.user(ADMIN) & filters.reply)
async def fb_download_images(bot, msg):
    # Check if the replied message contains a valid link
    reply = msg.reply_to_message
    if not reply or not reply.text or not reply.text.startswith("http"):
        return await msg.reply_text("❌ Please reply to a valid Facebook post link with the /fbdl command.")

    post_url = reply.text
    sts = await msg.reply_text("🔄 Processing... Please wait.")

    try:
        # Configure yt-dlp options
        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_LOCATION, "%(title)s.%(ext)s"),  # Save files with a proper name
            "quiet": True,  # Suppress yt-dlp output
            "extract_images": True,  # Extract images if available
            "format": "best",  # Download the best quality available
        }

        # Download media using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(post_url, download=False)  # Get info without downloading
            if not info_dict:
                return await sts.edit_text("❌ No media found in the post.")

            await sts.edit_text(f"📥 Downloading {info_dict.get('title', 'media')}...")
            ydl.download([post_url])  # Start downloading

        # Find the downloaded file(s)
        downloaded_files = []
        for file in os.listdir(DOWNLOAD_LOCATION):
            if file.endswith((".jpg", ".png", ".webp", ".mp4", ".mkv")):  # Supported formats
                downloaded_files.append(os.path.join(DOWNLOAD_LOCATION, file))

        if not downloaded_files:
            return await sts.edit_text("❌ No media files were downloaded.")

        # Upload files to Telegram
        await sts.edit_text("📤 Uploading media...")
        for file_path in downloaded_files:
            try:
                c_time = time.time()
                if file_path.endswith((".mp4", ".mkv")):  # Upload as video
                    await bot.send_video(
                        msg.chat.id,
                        video=file_path,
                        caption=f"📹 {os.path.basename(file_path)}",
                        progress=progress_message,
                        progress_args=(f"Uploading {os.path.basename(file_path)}...", sts, c_time)
                    )
                else:  # Upload as photo
                    await bot.send_photo(
                        msg.chat.id,
                        photo=file_path,
                        caption=f"🖼️ {os.path.basename(file_path)}",
                        progress=progress_message,
                        progress_args=(f"Uploading {os.path.basename(file_path)}...", sts, c_time)
                    )
                os.remove(file_path)  # Delete the file after uploading
            except Exception as e:
                print(f"Error uploading {file_path}: {e}")

        await sts.edit_text("✅ All media files have been uploaded successfully!")
    except Exception as e:
        await sts.edit_text(f"❌ An error occurred: {e}")
    finally:
        await sts.delete()
