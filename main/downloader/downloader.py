import os
import time
import asyncio
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from moviepy.editor import VideoFileClip
from PIL import Image
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT
from main.downloader.progress_hook import YTDLProgress
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
                size_str = humanbytes(filesize)
                available_resolutions.append((resolution, size_str, f['format_id']))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':
            filesize = f.get('filesize') or f.get('filesize_approx')
            if filesize:
                size_str = humanbytes(filesize)
                available_audio.append((filesize, size_str, f['format_id']))

    # Send thumbnail with info caption first
    caption = (
        f"**🎞 {title}**\n\n"
        f"**👀 Views:** {views}\n"
        f"**👍 Likes:** {likes}\n"
        f"**⏰ {duration}**\n"
        f"**🎥 {uploader}**\n\n"
        f"📥 **Select a resolution or audio format from buttons below.**"
    )

    # Build buttons
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    row = []
    for resolution, size, format_id in available_resolutions:
        row.append(InlineKeyboardButton(f"🎬 {resolution} - {size}", callback_data=f"yt_{format_id}_{resolution}_{url}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if available_audio:
        highest_audio = max(available_audio, key=lambda x: x[0])
        _, size, format_id = highest_audio
        buttons.append([InlineKeyboardButton(f"🎧 Audio - {size}", callback_data=f"audio_{format_id}_{url}")])
    buttons.append([
        InlineKeyboardButton("📝 Description", callback_data=f"desc_{url}"),
        InlineKeyboardButton("🖼️ Thumbnail", callback_data=f"thumb_{url}")
    ])
    markup = InlineKeyboardMarkup(buttons)

    # Send thumbnail with buttons
    if thumb_url:
        resp = requests.get(thumb_url)
        if resp.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
            await bot.send_photo(msg.chat.id, photo=thumb_path, caption=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
            os.remove(thumb_path)
        else:
            await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await bot.send_message(msg.chat.id, text=caption, reply_markup=markup, parse_mode=enums.ParseMode.MARKDOWN)

    await msg.delete()
    await processing_message.delete()


# Callback handler for download
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

    # Remove buttons and update caption to show downloading started
    await query.message.edit_reply_markup(reply_markup=None)
    await query.message.edit_caption(
        caption=f"📥 **Downloading Started...**\n\n🎞 {title}\n📹 {resolution}",
        parse_mode=enums.ParseMode.MARKDOWN
    )

    # Initialize progress with YTDLProgress using the same message
    progress = YTDLProgress(
        bot=bot, 
        chat_id=query.message.chat.id, 
        prefix_text=f"📥 **Downloading...**\n\n🎞 **{title}**\n\n📹 **{resolution}**", 
        edit_msg=query.message
    )

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
        await query.message.edit_caption(
            caption=f"❌ **Error during download:** {str(e)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    # Delete the download progress message
    await query.message.delete()

    # Process video info
    try:
        final_size = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        video_width, video_height = video.size
        filesize = humanbytes(final_size)
        video.close()
    except Exception as e:
        await bot.send_message(query.message.chat.id, f"❌ **Error processing video:** {str(e)}")
        return

    # Prepare and resize/crop thumbnail properly
    thumb_path = None
    thumb_url = info_dict.get('thumbnail', None)
    if thumb_url:
        resp = requests.get(thumb_url)
        if resp.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'upload_thumb.jpg')
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
            try:
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
                    img.save(thumb_path, "JPEG")
            except Exception as e:
                thumb_path = None

    # Send new message for upload with thumbnail
    upload_caption = f"🚀 **Uploading Started...**\n\n🎞 **{info_dict['title']}**\n\n📹 **{resolution}**"
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

    # Upload video with progress
    try:
        await bot.send_video(
            query.message.chat.id,
            video=downloaded_path,
            thumb=thumb_path,
            caption=f"**🎞 {info_dict['title']} | [🔗 URL]({url})**\n\n🎥 **{resolution}** | 🗂 **{filesize}**",
            duration=duration,
            progress=progress_message,
            progress_args=(f"**📤 Uploading...**\n\n🎞 **{info_dict['title']}**\n\n📹 **{resolution}**", upload_msg, time.time()),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        await upload_msg.delete()
    except Exception as e:
        await upload_msg.edit_caption(
            caption=f"❌ **Error during upload:** {str(e)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    # Cleanup files
    if os.path.exists(downloaded_path):
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
    await bot.send_message(query.message.chat.id, f"**📝 Description:**\n\n{desc}")


# Thumbnail handler
@Client.on_callback_query(filters.regex(r'^thumb_https?://'))
async def thumb_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        thumb_url = info.get('thumbnail', None)
    if not thumb_url:
        await query.message.edit_text("❌ **No thumbnail found.**")
        return
    resp = requests.get(thumb_url)
    if resp.status_code == 200:
        thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
        with open(thumb_path, 'wb') as f:
            f.write(resp.content)
        await bot.send_photo(query.message.chat.id, photo=thumb_path)
        os.remove(thumb_path)
    else:
        await query.message.edit_text("❌ **Failed to download thumbnail.**")
