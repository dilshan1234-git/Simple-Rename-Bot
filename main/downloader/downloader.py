import os
import time
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
from PIL import Image
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT

# Command to display welcome text with the YouTube link handler
@Client.on_message(filters.private & filters.command("ytdl") & filters.user(ADMIN))
async def ytdl(bot, msg):
    # Replace the placeholder with the actual URL from config.py
    caption_text = YTDL_WELCOME_TEXT.replace("TELEGRAPH_IMAGE_URL", TELEGRAPH_IMAGE_URL)
    
    # Send the image with the updated caption
    await bot.send_photo(
        chat_id=msg.chat.id,
        photo=TELEGRAPH_IMAGE_URL,  # Using the URL from config.py
        caption=caption_text,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# Command to handle YouTube video link and provide resolution/audio options
@Client.on_message(filters.private & filters.user(ADMIN) & filters.regex(r'https?://(www\.)?youtube\.com/(watch\?v=|shorts/)'))
async def youtube_link_handler(bot, msg):
    url = msg.text.strip()

    # Send processing message
    processing_message = await msg.reply_text("🔄 **Processing your request...**")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',  # Prefer AVC/AAC format
        'noplaylist': True,
        'quiet': True
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        title = info_dict.get('title', 'Unknown Title')
        views = info_dict.get('view_count', 'N/A')
        likes = info_dict.get('like_count', 'N/A')
        thumb_url = info_dict.get('thumbnail', None)
        description = info_dict.get('description', 'No description available.')
        formats = info_dict.get('formats', [])      
        duration_seconds = info_dict.get('duration', 0)
        uploader = info_dict.get('uploader', 'Unknown Channel')

    # Format the duration as HH:MM:SS
    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    # Extract all available resolutions with their sizes
    available_resolutions = []
    available_audio = []

    for f in formats:
        if f['ext'] == 'mp4' and f.get('vcodec') != 'none':  # Check for video formats
            resolution = f"{f['height']}p"
            fps = f.get('fps', None)  # Get the fps (frames per second)
            if fps in [50, 60]:  # Append fps to the resolution if it's 50 or 60
                resolution += f"{fps}fps"
            filesize = f.get('filesize')  # Fetch the filesize
            if filesize:  # Only process if filesize is not None
                filesize_str = humanbytes(filesize)  # Convert size to human-readable format
                format_id = f['format_id']
                available_resolutions.append((resolution, filesize_str, format_id))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':  # Check for audio formats
            filesize = f.get('filesize')
            if filesize:
                filesize_str = humanbytes(filesize)  # Show file size instead of bitrate
                format_id = f['format_id']
                available_audio.append((filesize, filesize_str, format_id))

    buttons = []
    row = []
    
    # Add available resolutions to the buttons
    for resolution, size, format_id in available_resolutions:
        button_text = f"🎬 {resolution} - {size}"
        callback_data = f"yt_{format_id}_{resolution}_{url}"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if len(row) == 2:  # Adjust the number of buttons per row if needed
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Find the highest quality audio based on the largest file size (in bytes)
    if available_audio:
        highest_quality_audio = max(available_audio, key=lambda x: float(x[1].replace(' MB', '').replace(' KB', '').strip()) * (1000000 if 'MB' in x[1] else 1000))
        _, size, format_id = highest_quality_audio  # Extract the size and format_id
        buttons.append([InlineKeyboardButton(f"🎧 Audio - {size}", callback_data=f"audio_{format_id}_{url}")])
    
    # Add description and thumbnail buttons in the same row
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

@Client.on_callback_query(filters.regex(r'^yt_\d+_\d+p(?:\d+fps)?_https?://(www\.)?youtube\.com/watch\?v='))
async def yt_callback_handler(bot, query):
    from main.downloader.progress_hook import YTDLProgress  # Import the YTDLProgress class

    data = query.data.split('_')
    format_id = data[1]
    resolution = data[2]
    url = query.data.split('_', 3)[3]

    # Get the title from the original message caption
    title = query.message.caption.split('🎞 ')[1].split('\n')[0]

    # Send initial download started message with title and resolution
    download_message = await query.message.edit_text(f"📥 **Download started...**\n\n**🎞 {title}**\n\n**📹 {resolution}**")

    # Initialize the YTDLProgress class
    progress = YTDLProgress(bot, download_message, prefix_text=f"**🎞 {title}**\n**📹 {resolution}**")

    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]/best",  # Fallback to 'best' if format fails
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }],
        'progress_hooks': [progress.hook],  # Add the progress hook
        'noplaylist': True,  # Ensure no playlist processing
        'quiet': True,  # Suppress verbose output to avoid unreliable progress
        'no_warnings': True,  # Suppress warnings that might interfere
        'retries': 10,  # Retry on transient errors
        'fragment_retries': 10,  # Retry on fragment download failures
        'skip_unavailable_fragments': True  # Skip unavailable fragments to avoid errors
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info_dict)
            if not os.path.exists(downloaded_path):
                raise Exception("Downloaded file not found")
        
    except Exception as e:
        await download_message.edit_text(f"❌ **Error during download:** {str(e)}")
        return

    try:
        final_filesize = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        video_width, video_height = video.size
        filesize = humanbytes(final_filesize)
    except Exception as e:
        await download_message.edit_text(f"❌ **Error processing video:** {str(e)}")
        return

    thumb_url = info_dict.get('thumbnail', None)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    if thumb_url:
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
    else:
        thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎥 **{resolution}**   |   🗂 **{filesize}**\n"                     
    )

    # Delete the "Download started" message and update the caption to "Uploading started"
    await download_message.delete()

    uploading_message = await bot.send_photo(
        chat_id=query.message.chat.id,
        photo=thumb_path,
        caption="🚀 **Uploading started...** 📤"
    ) if thumb_path else await bot.send_message(
        chat_id=query.message.chat.id,
        text="🚀 **Uploading started...** 📤"
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
        await uploading_message.edit_text(f"❌ **Error during upload:** {str(e)}")
        return

    await uploading_message.delete()

    # Clean up the downloaded video file and thumbnail after sending
    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

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

@Client.on_callback_query(filters.regex(r'^desc_https?://(www\.)?youtube\.com/watch\?v='))
async def description_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])

    # Extract video information to get the description
    ydl_opts = {'quiet': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        description = info_dict.get('description', 'No description available.')

    # Truncate the description to 4096 characters, the max limit for a text message
    if len(description) > 4096:
        description = description[:4093] + "..."

    await bot.send_message(chat_id=query.message.chat.id, text=f"**📝 Description:**\n\n{description}")
