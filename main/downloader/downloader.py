import os
import time
import requests
import asyncio
from queue import Queue, Empty
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
from PIL import Image
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT

# ---------------- Progress Hook ---------------- #
async def ytdl_progress_hook(d, message, c_time):
    """Custom yt-dlp progress hook for Telegram live updates"""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '').strip()
        speed = d.get('_speed_str', '').strip()
        eta = d.get('_eta_str', '').strip()
        total = d.get('_total_bytes_str', '') or d.get('_total_bytes_estimate_str', '')
        downloaded = d.get('_downloaded_bytes_str', '')

        text = (
            f"📥 **Downloading...**\n\n"
            f"✅ Progress: {percent}\n"
            f"📦 Size: {total}\n"
            f"⬇️ Downloaded: {downloaded}\n"
            f"⚡ Speed: {speed}\n"
            f"⏳ ETA: {eta}"
        )

        if (time.time() - c_time[0]) > 3:
            try:
                await message.edit_text(text)
                c_time[0] = time.time()
            except Exception:
                pass

    elif d['status'] == 'finished':
        try:
            await message.edit_text("✅ **Download complete!**\n🔄 Preparing file...")
        except Exception:
            pass

# ---------------- /ytdl Command ---------------- #
@Client.on_message(filters.private & filters.command("ytdl") & filters.user(ADMIN))
async def ytdl(bot, msg):
    caption_text = YTDL_WELCOME_TEXT.replace("TELEGRAPH_IMAGE_URL", TELEGRAPH_IMAGE_URL)
    await bot.send_photo(
        chat_id=msg.chat.id,
        photo=TELEGRAPH_IMAGE_URL,
        caption=caption_text,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ---------------- YouTube Link Handler ---------------- #
@Client.on_message(filters.private & filters.user(ADMIN) & filters.regex(r'https?://(www\.)?youtube\.com/(watch\?v=|shorts/)'))
async def youtube_link_handler(bot, msg):
    url = msg.text.strip()
    processing_message = await msg.reply_text("🔄 **Processing your request...**")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'noplaylist': True,
        'quiet': True
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        title = info_dict.get('title', 'Unknown Title')
        views = info_dict.get('view_count', 'N/A')
        likes = info_dict.get('like_count', 'N/A')
        thumb_url = info_dict.get('thumbnail', None)
        formats = info_dict.get('formats', [])      
        duration_seconds = info_dict.get('duration', 0)
        uploader = info_dict.get('uploader', 'Unknown Channel')

    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    available_resolutions, available_audio = [], []
    for f in formats:
        if f['ext'] == 'mp4' and f.get('vcodec') != 'none':
            resolution = f"{f['height']}p"
            fps = f.get('fps', None)
            if fps in [50, 60]:
                resolution += f"{fps}fps"
            filesize = f.get('filesize')
            if filesize:
                filesize_str = humanbytes(filesize)
                format_id = f['format_id']
                available_resolutions.append((resolution, filesize_str, format_id))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':
            filesize = f.get('filesize')
            if filesize:
                filesize_str = humanbytes(filesize)
                format_id = f['format_id']
                available_audio.append((filesize, filesize_str, format_id))

    buttons, row = [], []
    for resolution, size, format_id in available_resolutions:
        button_text = f"🎬 {resolution} - {size}"
        callback_data = f"yt_{format_id}_{resolution}_{url}"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if available_audio:
        highest_quality_audio = max(available_audio, key=lambda x: x[0])
        _, size, format_id = highest_quality_audio
        buttons.append([InlineKeyboardButton(f"🎧 Audio - {size}", callback_data=f"audio_{format_id}_{url}")])
    
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

    thumb_response = requests.get(thumb_url)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    with open(thumb_path, 'wb') as thumb_file:
        thumb_file.write(thumb_response.content)
    await bot.send_photo(chat_id=msg.chat.id, photo=thumb_path, caption=caption, reply_markup=markup)
    os.remove(thumb_path)

    await msg.delete()
    await processing_message.delete()

# ---------------- Download Callback Handler ---------------- #
@Client.on_callback_query(filters.regex(r'^yt_\d+_\d+p(?:\d+fps)?_https?://(www\.)?youtube\.com/watch\?v='))
async def yt_callback_handler(bot, query):
    data = query.data.split('_')
    format_id, resolution = data[1], data[2]
    url = query.data.split('_', 3)[3]

    title = query.message.caption.split('🎞 ')[1].split('\n')[0]
    download_message = await query.message.edit_text(
        f"📥 **Download started...**\n\n**🎞 {title}**\n\n**📹 {resolution}**"
    )

    # Thread-safe queue for progress updates
    progress_queue = Queue()
    FINISHED_MARKER = "__YTDL_FINISHED__"

    # Progress hook for yt-dlp (runs in worker thread)
    def progress_hook(d):
        status = d.get('status')
        if status == 'downloading':
            percent = d.get('_percent_str', '').strip()
            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            total = d.get('_total_bytes_str', '') or d.get('_total_bytes_estimate_str', '')
            downloaded = d.get('_downloaded_bytes_str', '')

            text = (
                f"📥 **Downloading...**\n\n"
                f"✅ Progress: {percent}\n"
                f"📦 Size: {total}\n"
                f"⬇️ Downloaded: {downloaded}\n"
                f"⚡ Speed: {speed}\n"
                f"⏳ ETA: {eta}"
            )
            try:
                progress_queue.put_nowait(text)
            except Exception:
                pass

        elif status == 'finished':
            try:
                progress_queue.put_nowait("✅ **Download complete!**\n🔄 Preparing file...")
                progress_queue.put_nowait(FINISHED_MARKER)
            except Exception:
                pass

    # Async updater task
    async def progress_updater():
        last_text = None
        while True:
            try:
                while True:
                    item = progress_queue.get_nowait()
                    last_text = item
            except Empty:
                pass

            if last_text and last_text != FINISHED_MARKER:
                try:
                    await download_message.edit_text(last_text)
                except Exception:
                    pass

            if last_text == FINISHED_MARKER:
                break

            await asyncio.sleep(2)

    # yt-dlp options
    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]",
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'progress_hooks': [progress_hook],
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]
    }

    progress_task = asyncio.create_task(progress_updater())

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info_dict)
    except Exception as e:
        try: progress_queue.put_nowait(FINISHED_MARKER)
        except: pass
        await progress_task
        await download_message.edit_text(f"❌ **Error during download:** {e}")
        return

    try:
        progress_queue.put_nowait(FINISHED_MARKER)
    except: pass
    await progress_task

    final_filesize = os.path.getsize(downloaded_path)
    video = VideoFileClip(downloaded_path)
    duration = int(video.duration)
    video_width, video_height = video.size
    filesize = humanbytes(final_filesize)

    thumb_url = info_dict.get('thumbnail', None)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    response = requests.get(thumb_url)
    if response.status_code == 200:
        with open(thumb_path, 'wb') as thumb_file:
            thumb_file.write(response.content)
        with Image.open(thumb_path) as img:
            img_width, img_height = img.size
            scale_factor = max(video_width / img_width, video_height / img_height)
            new_size = (int(img_width * scale_factor), int(img_height * scale_factor))
            img = img.resize(new_size, Image.LANCZOS)
            left = (img.width - video_width) / 2
            top = (img.height - video_height) / 2
            right = (img.width + video_width) / 2
            bottom = (img.height + video_height) / 2
            img = img.crop((left, top, right, bottom))
            img.save(thumb_path)
    else:
        thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎥 **{resolution}**   |   🗂 **{filesize}**\n"                     
    )

    await download_message.delete()
    uploading_message = await bot.send_photo(
        chat_id=query.message.chat.id,
        photo=thumb_path,
        caption="🚀 **Uploading started...** 📤"
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
            progress_args=(f"**📤 Uploading Started...Thanks To All Who Supported ❤\n\n🎞 {info_dict['title']}**", uploading_message, c_time)
        )
    except Exception as e:
        await uploading_message.edit_text(f"❌ **Error during upload:** {e}")
        return

    await uploading_message.delete()
    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

# ---------------- Thumbnail Callback ---------------- #
@Client.on_callback_query(filters.regex(r'^thumb_https?://(www\.)?youtube\.com/watch\?v='))
async def thumb_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    ydl_opts = {'quiet': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        thumb_url = info_dict.get('thumbnail', None)
    if not thumb_url:
        await query.message.edit_text("❌ **No thumbnail found for this video.**")
        return
    thumb_response = requests.get(thumb_url)
    if thumb_response.status_code == 200:
        thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
        with open(thumb_path, 'wb') as thumb_file:
            thumb_file.write(thumb_response.content)
        await bot.send_photo(chat_id=query.message.chat.id, photo=thumb_path)
        os.remove(thumb_path)
    else:
        await query.message.edit_text("❌ **Failed to download thumbnail.**")

# ---------------- Description Callback ---------------- #
@Client.on_callback_query(filters.regex(r'^desc_https?://(www\.)?youtube\.com/watch\?v='))
async def description_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    ydl_opts = {'quiet': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        description = info_dict.get('description', 'No description available.')
    if len(description) > 4096:
        description = description[:4093] + "..."
    await bot.send_message(chat_id=query.message.chat.id, text=f"**📝 Description:**\n\n{description}")
