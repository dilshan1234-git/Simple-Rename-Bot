import os
import time
import asyncio
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT
import nest_asyncio

nest_asyncio.apply()


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
    processing_message = await msg.reply_text("🔄 **Processing your request...**", parse_mode=enums.ParseMode.MARKDOWN)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0',
        'cookiefile': os.path.join(DOWNLOAD_LOCATION, 'cookies.txt') if os.path.exists(os.path.join(DOWNLOAD_LOCATION, 'cookies.txt')) else None,
        'retries': 10,
        'fragment_retries': 10,
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
    except Exception as e:
        await processing_message.edit_text(f"❌ **Error extracting video info:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    title = info_dict.get('title', 'Unknown Title')
    views = info_dict.get('view_count', 'N/A')
    likes = info_dict.get('like_count', 'N/A')
    thumb_url = info_dict.get('thumbnail', None)
    duration_seconds = info_dict.get('duration', 0)
    uploader = info_dict.get('uploader', 'Unknown Channel')
    formats = info_dict.get('formats', [])
    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    # Extract resolutions & audio
    available_resolutions = []
    available_audio = []

    for f in formats:
        if f['ext'] == 'mp4' and f.get('vcodec') != 'none':
            height = f.get('height')
            fps = f.get('fps', None)
            resolution = f"{height}p"
            if fps in [50, 60] and height in [720, 1080]:
                resolution += f"{fps}fps"
            filesize = f.get('filesize') or f.get('filesize_approx')
            if filesize:
                available_resolutions.append((resolution, humanbytes(filesize), f['format_id']))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':
            filesize = f.get('filesize') or f.get('filesize_approx')
            if filesize:
                available_audio.append((filesize, humanbytes(filesize), f['format_id']))

    # Sort resolutions numerically
    available_resolutions.sort(key=lambda x: int(''.join(filter(str.isdigit, x[0]))))

    # Build buttons
    buttons = []
    row = []
    for resolution, size, format_id in available_resolutions:
        row.append(InlineKeyboardButton(f"📹 {resolution} - {size}", callback_data=f"yt_{format_id}_{resolution}_{url}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Audio button
    if available_audio:
        highest_audio = max(available_audio, key=lambda x: x[0])
        _, size, format_id = highest_audio
        buttons.append([InlineKeyboardButton(f"🎧 Audio - {size}", callback_data=f"audio_{format_id}_{url}")])

    # Description & thumbnail buttons
    buttons.append([
        InlineKeyboardButton("📝 Description", callback_data=f"desc_{url}"),
        InlineKeyboardButton("🖼️ Thumbnail", callback_data=f"thumb_{url}")
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

    if thumb_url:
        resp = requests.get(thumb_url)
        if resp.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
            download_message = await bot.send_photo(msg.chat.id, photo=thumb_path, caption=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
            os.remove(thumb_path)
        else:
            download_message = await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        download_message = await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)

    await msg.delete()
    await processing_message.delete()


# Callback for video/audio download
@Client.on_callback_query(filters.regex(r'^(yt|audio)_'))
async def yt_callback_handler(bot, query):
    data = query.data.split('_')
    format_id = data[1]
    resolution = data[2]
    url = query.data.split('_', 3)[3]

    try:
        title = query.message.caption.split('🎞 ')[1].split('\n')[0]
    except:
        title = "Unknown Title"

    # Live download progress message
    downloading_msg = await bot.send_message(query.message.chat.id, f"📥 **Downloading Started...**\n\n🎞 {title}\n📹 {resolution}", parse_mode=enums.ParseMode.MARKDOWN)
    start_time = time.time()

    def progress_hook(d):
        try:
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                percent = (downloaded * 100 / total) if total else 0
                asyncio.run_coroutine_threadsafe(
                    progress_message(f"📥 **Downloading...**\n\n🎞 {title}\n📹 {resolution}", downloading_msg, start_time, downloaded, total, speed, eta),
                    asyncio.get_event_loop()
                )
        except Exception:
            pass

    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]/best",
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'progress_hooks': [progress_hook],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
    }

    loop = asyncio.get_event_loop()

    def download_video():
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info, ydl.prepare_filename(info)

    try:
        info_dict, downloaded_path = await loop.run_in_executor(None, download_video)
    except Exception as e:
        await downloading_msg.edit_text(f"❌ **Error during download:** {e}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    await downloading_msg.edit_text("✅ **Download Completed!**\n\nPreparing for upload...", parse_mode=enums.ParseMode.MARKDOWN)

    # Upload video
    try:
        final_size = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        filesize = humanbytes(final_size)
    except Exception as e:
        await bot.send_message(query.message.chat.id, f"❌ **Error processing video:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    thumb_path = None
    thumb_url = info_dict.get('thumbnail', None)
    if thumb_url:
        resp = requests.get(thumb_url)
        if resp.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)

    caption = f"**🎞 {info_dict['title']} | [🔗 URL]({url})**\n\n🎥 **{resolution}** | 🗂 **{filesize}**"
    uploading_msg = await bot.send_message(query.message.chat.id, "🚀 **Uploading started...** 📤", parse_mode=enums.ParseMode.MARKDOWN)

    try:
        await bot.send_video(
            query.message.chat.id,
            video=downloaded_path,
            thumb=thumb_path,
            caption=caption,
            duration=duration,
            progress=progress_message,
            progress_args=(f"📤 **Uploading...**\n\n🎞 {info_dict['title']}", uploading_msg, time.time())
        )
    except Exception as e:
        await uploading_msg.edit_text(f"❌ **Error during upload:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    await uploading_msg.delete()
    os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)


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
