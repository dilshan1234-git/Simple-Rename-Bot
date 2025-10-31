# main/downloader/audiodl.py

import os
import time
import asyncio
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import AudioFileClip
from PIL import Image
from config import DOWNLOAD_LOCATION
from main.utils import progress_message, humanbytes
from main.downloader.progress_hook import YTDLProgress


# 🎧 Callback for Audio Download Button
@Client.on_callback_query(filters.regex(r'^audio_'))
async def audio_callback_handler(bot, query):
    try:
        data = query.data.split('_')
        format_id = data[1]
        url = '_'.join(data[2:])  # full YouTube URL

        # Safely extract title from caption (handles 🎞 or 🎬)
        caption_text = query.message.caption or ""
        if '🎞 ' in caption_text:
            title = caption_text.split('🎞 ')[1].split('\n')[0]
        elif '🎬 ' in caption_text:
            title = caption_text.split('🎬 ')[1].split('\n')[0]
        else:
            title = "Unknown Title"

        # Remove buttons before updating message
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.edit_caption(
            caption=f"📥 **Downloading Audio...**\n\n🎧 **{title}**",
            parse_mode=enums.ParseMode.MARKDOWN
        )

        # Initialize YTDL progress updater
        progress = YTDLProgress(
            bot=bot,
            chat_id=query.message.chat.id,
            prefix_text=f"📥 **Downloading Audio...**\n\n🎧 **{title}**",
            edit_msg=query.message
        )
        await progress.start_updater()

        # yt_dlp options
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
            'progress_hooks': [progress.hook],
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'retries': 10,
            'fragment_retries': 10,
        }

        # Download audio
        def download_audio():
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl.prepare_filename(info)

        loop = asyncio.get_event_loop()
        try:
            info_dict, downloaded_path = await loop.run_in_executor(None, download_audio)
        except Exception as e:
            await progress.stop_updater()
            await query.message.edit_caption(
                caption=f"❌ **Error during audio download:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return

        await progress.stop_updater()
        await query.message.delete()

        # Get audio duration & size
        try:
            final_size = os.path.getsize(downloaded_path)
            audio = AudioFileClip(downloaded_path)
            duration = int(audio.duration)
            filesize = humanbytes(final_size)
            audio.close()
        except Exception:
            duration = 0
            filesize = humanbytes(os.path.getsize(downloaded_path))

        # Download thumbnail if available
        thumb_path = None
        thumb_url = info_dict.get('thumbnail', None)
        if thumb_url:
            try:
                resp = requests.get(thumb_url)
                if resp.status_code == 200:
                    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'audio_thumb.jpg')
                    with open(thumb_path, 'wb') as f:
                        f.write(resp.content)
                    # Resize for upload
                    with Image.open(thumb_path) as img:
                        img.thumbnail((320, 320))
                        img.save(thumb_path)
            except Exception:
                thumb_path = None

        # Send upload message
        upload_caption = f"🚀 **Uploading Audio...**\n\n🎧 **{info_dict['title']}**"
        if thumb_path and os.path.exists(thumb_path):
            upload_msg = await bot.send_photo(
                query.message.chat.id,
                photo=thumb_path,
                caption=upload_caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            upload_msg = await bot.send_message(
                query.message.chat.id,
                text=upload_caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )

        # Upload as audio
        try:
            await bot.send_audio(
                query.message.chat.id,
                audio=downloaded_path,
                thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
                caption=f"**🎧 {info_dict['title']} | [🔗 URL]({url})**\n\n🗂 **{filesize}**",
                duration=duration,
                progress=progress_message,
                progress_args=(f"**📤 Uploading...**\n\n🎧 **{info_dict['title']}**", upload_msg, time.time()),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await upload_msg.delete()
        except Exception as e:
            await upload_msg.edit_caption(
                caption=f"❌ **Error during audio upload:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return

        # Cleanup
        if os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        await query.message.reply_text(f"❌ **Unexpected error:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
