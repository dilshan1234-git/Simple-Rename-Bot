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
from concurrent.futures import ThreadPoolExecutor
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT

# Set up logging to debug issues
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Command to display welcome text with the YouTube link handler
@Client.on_message(filters.private & filters.command("ytdl") & filters.user(ADMIN))
async def ytdl(bot, msg):
    caption_text = YTDL_WELCOME_TEXT.replace("TELEGRAPH_IMAGE_URL", TELEGRAPH_IMAGE_URL)
    await bot.send_photo(
        chat_id=msg.chat.id,
        photo=TELEGRAPH_IMAGE_URL,
        caption=caption_text,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# Command to handle YouTube video link and provide resolution/audio options
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
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'cookiefile': os.path.join(DOWNLOAD_LOCATION, 'cookies.txt') if os.path.exists(os.path.join(DOWNLOAD_LOCATION, 'cookies.txt')) else None,
        'retries': 15,
        'fragment_retries': 15,
        'socket_timeout': 30,
    }

    try:
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
    except Exception as e:
        logger.error(f"Failed to extract video info: {str(e)}")
        await processing_message.edit_text(f"❌ **Error extracting video info:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    available_resolutions = []
    available_audio = []

    logger.info(f"Found {len(formats)} formats for video")
    for f in formats:
        if f['ext'] == 'mp4' and f.get('vcodec') != 'none':
            resolution = f"{f.get('height', 'Unknown')}p"
            fps = f.get('fps', None)
            if fps in [50, 60]:
                resolution += f"{fps}fps"
            filesize = f.get('filesize') or f.get('filesize_approx')
            format_id = f.get('format_id')
            if format_id:
                filesize_str = humanbytes(filesize) if filesize else 'Unknown'
                available_resolutions.append((resolution, filesize_str, format_id))
        elif f['ext'] in ['m4a', 'webm'] and f.get('acodec') != 'none':
            filesize = f.get('filesize') or f.get('filesize_approx')
            format_id = f.get('format_id')
            if format_id:
                filesize_str = humanbytes(filesize) if filesize else 'Unknown'
                available_audio.append((filesize or 0, filesize_str, format_id))

    logger.info(f"Available resolutions: {available_resolutions}")
    logger.info(f"Available audio formats: {available_audio}")

    buttons = []
    row = []
    
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

    if not buttons:
        logger.error("No buttons generated; sending error message")
        await processing_message.edit_text("❌ **No valid formats found for this video.**", parse_mode=enums.ParseMode.MARKDOWN)
        return

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
            thumb_response = requests.get(thumb_url)
            if thumb_response.status_code == 200:
                thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
                with open(thumb_path, 'wb') as thumb_file:
                    thumb_file.write(thumb_response.content)
                await bot.send_photo(
                    chat_id=msg.chat.id,
                    photo=thumb_path,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            else:
                logger.error(f"Failed to download thumbnail: HTTP {thumb_response.status_code}")
                await bot.send_message(
                    chat_id=msg.chat.id,
                    text=caption,
                    reply_markup=markup,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
        else:
            logger.warning("No thumbnail URL available; sending caption with buttons")
            await bot.send_message(
                chat_id=msg.chat.id,
                text=caption,
                reply_markup=markup,
                parse_mode=enums.ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Failed to send message with buttons: {str(e)}")
        await processing_message.edit_text(f"❌ **Error sending video options:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    await msg.delete()
    await processing_message.delete()

@Client.on_callback_query(filters.regex(r'^yt_\d+_\d+p(?:\d+fps)?_https?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)'))
async def yt_callback_handler(bot, query):
    from main.downloader.progress_hook import YTDLProgress

    data = query.data.split('_')
    format_id = data[1]
    resolution = data[2]
    url = query.data.split('_', 3)[3]

    try:
        title = query.message.caption.split('🎞 ')[1].split('\n')[0]
    except IndexError:
        title = "Unknown Title"

    # Send the "Download started" message by editing the query message
    try:
        download_message = await query.message.edit_text(
            f"📥 **Download started...**\n\n**🎞 {title}**\n\n**📹 {resolution}**",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit download started message: {str(e)}")
        download_message = await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"📥 **Download started...**\n\n**🎞 {title}**\n\n**📹 {resolution}**",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    # Initialize the YTDLProgress class
    progress = YTDLProgress(bot, query.message.chat.id, prefix_text=f"**🎞 {title}**\n**📹 {resolution}**")

    # Send initial progress message after a delay to ensure "Download started" is visible
    await asyncio.sleep(2)
    initial_progress_text = f"**🎞 {title}**\n**📹 {resolution}**\n📥 **Preparing download...**"
    await progress.update_msg(initial_progress_text)

    ydl_opts = {
        'format': f"{format_id}+bestaudio[ext=m4a]/best",
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }],
        'progress_hooks': [progress.hook],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'retries': 15,
        'fragment_retries': 15,
        'socket_timeout': 30,
        'skip_unavailable_fragments': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'cookiefile': os.path.join(DOWNLOAD_LOCATION, 'cookies.txt') if os.path.exists(os.path.join(DOWNLOAD_LOCATION, 'cookies.txt')) else None,
    }

    def download_video():
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info_dict)
                return info_dict, downloaded_path
        except Exception as e:
            raise e

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            info_dict, downloaded_path = executor.submit(download_video).result()
        if not os.path.exists(downloaded_path):
            raise Exception("Downloaded file not found")
            
        # Only cleanup after successful download
        await progress.cleanup()
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        # Cleanup on error
        await progress.cleanup()
        try:
            await download_message.edit_text(
                f"❌ **Error during download:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to edit error message: {str(e)}")
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=f"❌ **Error during download:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        return

    try:
        await download_message.delete()
    except Exception as e:
        logger.error(f"Failed to delete download message: {str(e)}")

    try:
        final_filesize = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        video_width, video_height = video.size
        video.close()  # Important: close the video file to free memory
        filesize = humanbytes(final_filesize)
    except Exception as e:
        logger.error(f"Video processing error: {str(e)}")
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"❌ **Error processing video:** {str(e)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        # Clean up downloaded file on error
        if os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        return

    # Generate thumbnail
    thumb_path = None
    thumb_url = info_dict.get('thumbnail', None)
    if thumb_url:
        try:
            response = requests.get(thumb_url, timeout=10)
            if response.status_code == 200:
                thumb_path = os.path.join(DOWNLOAD_LOCATION, f'thumb_{int(time.time())}.jpg')
                with open(thumb_path, 'wb') as thumb_file:
                    thumb_file.write(response.content)
                
                # Resize thumbnail to match video dimensions
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
        except Exception as e:
            logger.error(f"Thumbnail processing error: {str(e)}")
            thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎥 **{resolution}**   |   🗂 **{filesize}**\n"
    )

    uploading_message = None
    try:
        if thumb_path and os.path.exists(thumb_path):
            uploading_message = await bot.send_photo(
                chat_id=query.message.chat.id,
                photo=thumb_path,
                caption="🚀 **Uploading started...** 📤",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            uploading_message = await bot.send_message(
                chat_id=query.message.chat.id,
                text="🚀 **Uploading started...** 📤",
                parse_mode=enums.ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Failed to send uploading message: {str(e)}")

    c_time = time.time()
    try:
        await bot.send_video(
            chat_id=query.message.chat.id,
            video=downloaded_path,
            thumb=thumb_path,
            caption=caption,
            duration=duration,
            width=video_width,
            height=video_height,
            progress=progress_message,
            progress_args=(f"**📤 Uploading Started...Thanks To All Who Supported ❤\n\n🎞 {info_dict['title']}**", uploading_message, c_time)
        )
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        if uploading_message:
            try:
                await uploading_message.edit_text(f"❌ **Error during upload:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
            except:
                await bot.send_message(
                    chat_id=query.message.chat.id,
                    text=f"❌ **Error during upload:** {str(e)}",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
        return

    # Clean up messages and files
    if uploading_message:
        try:
            await uploading_message.delete()
        except Exception as e:
            logger.error(f"Failed to delete uploading message: {str(e)}")

    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

@Client.on_callback_query(filters.regex(r'^audio_\d+_https?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)'))
async def audio_callback_handler(bot, query):
    from main.downloader.progress_hook import YTDLProgress
    
    data = query.data.split('_')
    format_id = data[1]
    url = query.data.split('_', 2)[2]

    try:
        title = query.message.caption.split('🎞 ')[1].split('\n')[0]
    except IndexError:
        title = "Unknown Title"

    # Send the "Download started" message
    try:
        download_message = await query.message.edit_text(
            f"📥 **Audio download started...**\n\n**🎞 {title}**\n\n**🎧 Audio**",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit download started message: {str(e)}")
        download_message = await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"📥 **Audio download started...**\n\n**🎞 {title}**\n\n**🎧 Audio**",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    # Initialize progress tracker
    progress = YTDLProgress(bot, query.message.chat.id, prefix_text=f"**🎞 {title}**\n**🎧 Audio**")

    await asyncio.sleep(2)
    initial_progress_text = f"**🎞 {title}**\n**🎧 Audio**\n📥 **Preparing download...**"
    await progress.update_msg(initial_progress_text)

    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
        'progress_hooks': [progress.hook],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'retries': 15,
        'fragment_retries': 15,
        'socket_timeout': 30,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'cookiefile': os.path.join(DOWNLOAD_LOCATION, 'cookies.txt') if os.path.exists(os.path.join(DOWNLOAD_LOCATION, 'cookies.txt')) else None,
    }

    def download_audio():
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info_dict)
                return info_dict, downloaded_path
        except Exception as e:
            raise e

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            info_dict, downloaded_path = executor.submit(download_audio).result()
        if not os.path.exists(downloaded_path):
            raise Exception("Downloaded audio file not found")
            
        await progress.cleanup()
        
    except Exception as e:
        logger.error(f"Audio download error: {str(e)}")
        await progress.cleanup()
        try:
            await download_message.edit_text(
                f"❌ **Error during audio download:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to edit error message: {str(e)}")
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=f"❌ **Error during audio download:** {str(e)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        return

    try:
        await download_message.delete()
    except Exception as e:
        logger.error(f"Failed to delete download message: {str(e)}")

    # Get audio file info
    try:
        final_filesize = os.path.getsize(downloaded_path)
        filesize = humanbytes(final_filesize)
        
        # Try to get duration from the audio file
        try:
            from mutagen import File
            audio_file = File(downloaded_path)
            duration = int(audio_file.info.length) if audio_file and audio_file.info else info_dict.get('duration', 0)
        except:
            duration = info_dict.get('duration', 0)
            
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}")
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"❌ **Error processing audio:** {str(e)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        if os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        return

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎧 **Audio**   |   🗂 **{filesize}**\n"
    )

    uploading_message = await bot.send_message(
        chat_id=query.message.chat.id,
        text="🚀 **Uploading audio...** 📤",
        parse_mode=enums.ParseMode.MARKDOWN
    )

    c_time = time.time()
    try:
        await bot.send_audio(
            chat_id=query.message.chat.id,
            audio=downloaded_path,
            caption=caption,
            duration=duration,
            title=info_dict.get('title', 'Audio'),
            performer=info_dict.get('uploader', 'Unknown'),
            progress=progress_message,
            progress_args=(f"**📤 Uploading Audio...Thanks To All Who Supported ❤\n\n🎞 {info_dict['title']}**", uploading_message, c_time)
        )
    except Exception as e:
        logger.error(f"Audio upload error: {str(e)}")
        await uploading_message.edit_text(f"❌ **Error during audio upload:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
        return

    try:
        await uploading_message.delete()
    except Exception as e:
        logger.error(f"Failed to delete uploading message: {str(e)}")

    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)

@Client.on_callback_query(filters.regex(r'^thumb_https?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)'))
async def thumb_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    ydl_opts = {'quiet': True, 'no_warnings': True}

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            thumb_url = info_dict.get('thumbnail', None)

        if not thumb_url:
            await query.message.edit_text("❌ **No thumbnail found for this video.**", parse_mode=enums.ParseMode.MARKDOWN)
            return

        thumb_response = requests.get(thumb_url, timeout=10)
        if thumb_response.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, f'thumb_{int(time.time())}.jpg')
            with open(thumb_path, 'wb') as thumb_file:
                thumb_file.write(thumb_response.content)
            
            await bot.send_photo(
                chat_id=query.message.chat.id, 
                photo=thumb_path,
                caption=f"**🖼️ Thumbnail for:** {info_dict.get('title', 'Video')}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        else:
            logger.error(f"Thumbnail download failed: HTTP {thumb_response.status_code}")
            await query.message.edit_text("❌ **Failed to download thumbnail.**", parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Thumbnail handler error: {str(e)}")
        await query.message.edit_text(f"❌ **Error getting thumbnail:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)

@Client.on_callback_query(filters.regex(r'^desc_https?://(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|shorts/)'))
async def description_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])

    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            description = info_dict.get('description', 'No description available.')
            title = info_dict.get('title', 'Video')

        if len(description) > 4000:
            description = description[:3997] + "..."

        await bot.send_message(
            chat_id=query.message.chat.id, 
            text=f"**📝 Description for:** {title}\n\n{description}", 
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Description handler error: {str(e)}")
        await query.message.edit_text(f"❌ **Error getting description:** {str(e)}", parse_mode=enums.ParseMode.MARKDOWN)
