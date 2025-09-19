import os
import time
import asyncio
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
from PIL import Image
import logging
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT
from main.downloader.progress_hook import YTDLProgress
import nest_asyncio

nest_asyncio.apply()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# /ytdl command
@Client.on_message(filters.private & filters.command("ytdl") & filters.user(ADMIN))
async def ytdl(bot, msg):
    caption_text = YTDL_WELCOME_TEXT.replace("TELEGRAPH_IMAGE_URL", TELEGRAPH_IMAGE_URL)
    await bot.send_photo(
        chat_id=msg.chat.id,
        photo=TELEGRAPH_IMAGE_URL,
        caption=caption_text,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# Handle YouTube links
@Client.on_message(filters.private & filters.user(ADMIN) & filters.regex(r'https?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)'))
async def youtube_link_handler(bot, msg):
    url = msg.text.strip()
    logger.info(f"Processing YouTube URL: {url}")

    processing_message = await msg.reply_text("🔄 **Processing your request...**", parse_mode=enums.ParseMode.MARKDOWN)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'format_sort': ['+res', '+size'],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'cookiefile': os.path.join(DOWNLOAD_LOCATION, 'cookies.txt') if os.path.exists(os.path.join(DOWNLOAD_LOCATION, 'cookies.txt')) else None,
        'retries': 10,
        'fragment_retries': 10,
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get('title', 'Unknown Title')
            views = info_dict.get('view_count', 'N/A')
            likes = info_dict.get('like_count', 'N/A')
            thumb_url = info_dict.get('thumbnail', None)
            duration_seconds = info_dict.get('duration', 0)
            uploader = info_dict.get('uploader', 'Unknown Channel')
            formats = info_dict.get('formats', [])
    except Exception as e:
        await processing_message.edit_text(f"❌ **Error extracting video info:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    # Collect resolutions and audio
    available_resolutions = {}
    available_audio = []
    for f in formats:
        if f['ext'] == 'mp4' and f.get('vcodec') != 'none':
            height = int(f.get('height', 0))
            fps = int(f.get('fps', 0)) if f.get('fps') else None
            resolution = f"{height}p"
            if fps and fps != 30:
                resolution_fps = f"{height}p{fps}fps"
                available_resolutions[resolution_fps] = (f.get('format_id'), f.get('filesize') or f.get('filesize_approx'))
            available_resolutions[resolution] = (f.get('format_id'), f.get('filesize') or f.get('filesize_approx'))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':
            filesize = f.get('filesize') or f.get('filesize_approx')
            format_id = f.get('format_id')
            if format_id:
                filesize_str = humanbytes(filesize) if filesize else 'Unknown'
                available_audio.append((filesize or 0, filesize_str, format_id))

    # Sort resolutions
    sorted_resolutions = sorted(available_resolutions.items(), key=lambda x: int(''.join(filter(str.isdigit, x[0]))))

    # Build 2-column buttons
    buttons = []
    row = []
    for res_name, (format_id, filesize) in sorted_resolutions:
        size_str = humanbytes(filesize) if filesize else 'Unknown'
        row.append(InlineKeyboardButton(f"📹 {res_name} - {size_str}", callback_data=f"yt_{format_id}_{res_name}_{url}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Audio button
    if available_audio:
        highest_quality_audio = max(available_audio, key=lambda x: x[0])
        _, size, format_id = highest_quality_audio
        buttons.append([InlineKeyboardButton(f"🎧 Audio - {size}", callback_data=f"audio_{format_id}_{url}")])

    # Thumbnail & Description
    buttons.append([
        InlineKeyboardButton("🖼️ Thumbnail", callback_data=f"thumb_{url}"),
        InlineKeyboardButton("📝 Description", callback_data=f"desc_{url}")
    ])

    markup = InlineKeyboardMarkup(buttons)
    caption = (
        f"**🎞 {title}**\n\n"
        f"**👀 Views:** {views}\n"
        f"**👍 Likes:** {likes}\n"
        f"**⏰ {duration}**\n"
        f"**🎥 {uploader}**\n\n"
        f"📥 **Select your resolution or audio format:**"
    )

    try:
        if thumb_url:
            resp = requests.get(thumb_url)
            if resp.status_code == 200:
                thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
                with open(thumb_path, 'wb') as f:
                    f.write(resp.content)
                download_message = await bot.send_photo(
                    chat_id=msg.chat.id,
                    photo=thumb_path,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                os.remove(thumb_path)
            else:
                download_message = await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
        else:
            download_message = await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        await processing_message.edit_text(f"❌ **Error sending video options:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    await msg.delete()
    await processing_message.delete()


# Handle resolution/audio selection
@Client.on_callback_query(filters.regex(r'^yt_\d+_'))
async def yt_callback_handler(bot, query):
    data = query.data.split('_')
    format_id = data[1]
    resolution = data[2]
    url = query.data.split('_', 3)[3]

    try:
        title = query.message.caption.split('🎞 ')[1].split('\n')[0]
    except Exception:
        title = "Unknown Title"

    # Initialize progress
    progress = YTDLProgress(bot, query.message.chat.id)
    progress.update_task = asyncio.create_task(progress.process_queue())

    await progress.update_msg(f"📥 **Downloading Started...**\n\n🎞 {title}\n📹 {resolution}")

    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]/best",
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'progress_hooks': [progress.hook],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
    }

    def download_video():
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info, ydl.prepare_filename(info)

    loop = asyncio.get_event_loop()
    try:
        info_dict, downloaded_path = await loop.run_in_executor(None, download_video)
    except Exception as e:
        await progress.cleanup()
        await query.message.edit_text(f"❌ **Error during download:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    # Auto-delete initial download message
    await progress.cleanup()
    await query.message.delete()

    # Process video for upload
    try:
        final_filesize = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        video_width, video_height = video.size
        filesize = humanbytes(final_filesize)
    except Exception as e:
        await bot.send_message(query.message.chat.id, f"❌ **Error processing video:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    thumb_url = info_dict.get('thumbnail', None)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    if thumb_url:
        resp = requests.get(thumb_url)
        if resp.status_code == 200:
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
        else:
            thumb_path = None
    else:
        thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎥 **{resolution}**   |   🗂 **{filesize}**\n"
    )

    uploading_message = await bot.send_message(
        query.message.chat.id,
        text="🚀 **Uploading started...** 📤",
        parse_mode=enums.ParseMode.MARKDOWN
    )

    c_time = time.time()
    try:
        await bot.send_video(
            chat_id=query.message.chat.id,
            video=downloaded_path,
            thumb=thumb_path,
            caption=caption,
            duration=duration,
            progress=progress_message,
            progress_args=(f"**📤 Uploading Started... ❤\n\n🎞 {info_dict['title']}**", uploading_message, c_time)
        )
    except Exception as e:
        await uploading_message.edit_text(f"❌ **Error during upload:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    await uploading_message.delete()

    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)


# Thumbnail handler
@Client.on_callback_query(filters.regex(r'^thumb_https?://'))
async def thumb_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        thumb_url = info.get('thumbnail', None)

    if not thumb_url:
        await query.message.edit_text("❌ **No thumbnail found.**", parse_mode=enums.ParseMode.MARKDOWN)
        return

    resp = requests.get(thumb_url)
    if resp.status_code == 200:
        thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
        with open(thumb_path, 'wb') as f:
            f.write(resp.content)
        await bot.send_photo(query.message.chat.id, photo=thumb_path)
        os.remove(thumb_path)
    else:
        await query.message.edit_text("❌ **Failed to download thumbnail.**", parse_mode=enums.ParseMode.MARKDOWN)


# Description handler
@Client.on_callback_query(filters.regex(r'^desc_https?://'))
async def description_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        desc = info.get('description', 'No description available.')

    if len(desc) > 4096:
        desc = desc[:4093] + "..."
    await bot.send_message(query.message.chat.id, f"**📝 Description:**\n\n{desc}", parse_mode=enums.ParseMode.MARKDOWN)
