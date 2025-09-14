import os
import time
import asyncio
import requests
import yt_dlp as youtube_dl
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from moviepy.editor import VideoFileClip
from PIL import Image
from config import DOWNLOAD_LOCATION, ADMIN, TELEGRAPH_IMAGE_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import YTDL_WELCOME_TEXT

# Global dictionary to store progress data
progress_data = {}

def create_progress_bar(percentage):
    """Create a visual progress bar"""
    filled = int(percentage / 5)  # 20 segments
    empty = 20 - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {percentage:.1f}%"

def format_speed(speed_bytes):
    """Format download speed"""
    if speed_bytes is None or speed_bytes <= 0:
        return "0 B/s"
    
    if speed_bytes < 1024:
        return f"{speed_bytes:.0f} B/s"
    elif speed_bytes < 1024**2:
        return f"{speed_bytes/1024:.1f} KB/s"
    elif speed_bytes < 1024**3:
        return f"{speed_bytes/(1024**2):.1f} MB/s"
    else:
        return f"{speed_bytes/(1024**3):.1f} GB/s"

def format_time(seconds):
    """Convert seconds to MM:SS format"""
    if seconds is None or seconds <= 0:
        return "00:00"
    if seconds < 3600:
        return time.strftime('%M:%S', time.gmtime(seconds))
    else:
        return time.strftime('%H:%M:%S', time.gmtime(seconds))

def progress_hook(d):
    """Simple progress hook that stores data globally"""
    global progress_data
    
    try:
        # Create a unique key for this download
        filename = d.get('filename', 'unknown')
        download_key = os.path.basename(filename).split('.')[0][:50]  # Use first 50 chars of filename
        
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            # Determine if it's video or audio
            is_video = '.f' in filename and '.mp4' in filename
            is_audio = '.m4a' in filename or '.webm' in filename
            
            if is_video:
                phase = "📹 Downloading Video"
            elif is_audio:
                phase = "🎵 Downloading Audio"
            else:
                phase = "📥 Downloading"
            
            progress_data[download_key] = {
                'status': 'downloading',
                'phase': phase,
                'downloaded': downloaded,
                'total': total,
                'speed': speed,
                'eta': eta,
                'percentage': (downloaded / total * 100) if total > 0 else 0,
                'timestamp': time.time()
            }
            
        elif d['status'] == 'finished':
            is_video = '.f' in filename and '.mp4' in filename
            is_audio = '.m4a' in filename or '.webm' in filename
            
            if is_video:
                phase = "✅ Video Downloaded"
                next_phase = "⏳ Waiting for audio..."
            elif is_audio:
                phase = "✅ Audio Downloaded"
                next_phase = "🔄 Merging files..."
            else:
                phase = "✅ Download Complete"
                next_phase = "🎉 Ready!"
            
            progress_data[download_key] = {
                'status': 'finished',
                'phase': phase,
                'next_phase': next_phase,
                'total_bytes': d.get('total_bytes', 0),
                'filename': filename,
                'timestamp': time.time()
            }
            
    except Exception as e:
        # Silent error handling
        pass

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
@Client.on_message(filters.private & filters.user(ADMIN) & filters.regex(r'https?://(www\.)?youtube\.com/(watch\?v=|shorts/)'))
async def youtube_link_handler(bot, msg):
    url = msg.text.strip()
    processing_message = await msg.reply_text("🔄 **Processing your request...**")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'noplaylist': True,
        'quiet': True
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get('title', 'Unknown Title')
            views = info_dict.get('view_count', 'N/A')
            likes = info_dict.get('like_count', 'N/A')
            thumb_url = info_dict.get('thumbnail', None)
            formats = info_dict.get('formats', [])
            duration_seconds = info_dict.get('duration', 0)
            uploader = info_dict.get('uploader', 'Unknown Channel')
    except Exception as e:
        await processing_message.edit_text(f"❌ **Error processing video:** {e}")
        return

    duration = time.strftime('%H:%M:%S', time.gmtime(duration_seconds))

    # Extract available resolutions and audio
    available_resolutions = []
    available_audio = []

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
        highest_quality_audio = max(available_audio, key=lambda x: float(x[1].replace(' MB', '').replace(' KB', '').strip()) * (1000000 if 'MB' in x[1] else 1000))
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

    if thumb_url:
        try:
            thumb_response = requests.get(thumb_url, timeout=10)
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
            with open(thumb_path, 'wb') as thumb_file:
                thumb_file.write(thumb_response.content)
            await bot.send_photo(chat_id=msg.chat.id, photo=thumb_path, caption=caption, reply_markup=markup)
            os.remove(thumb_path)
        except:
            await bot.send_message(chat_id=msg.chat.id, text=caption, reply_markup=markup)
    else:
        await bot.send_message(chat_id=msg.chat.id, text=caption, reply_markup=markup)

    await msg.delete()
    await processing_message.delete()

@Client.on_callback_query(filters.regex(r'^yt_\d+_\d+p(?:\d+fps)?_https?://(www\.)?youtube\.com/watch\?v='))
async def yt_callback_handler(bot, query):
    global progress_data
    
    data = query.data.split('_')
    format_id = data[1]
    resolution = data[2]
    url = query.data.split('_', 3)[3]

    title = query.message.caption.split('🎞 ')[1].split('\n')[0]

    download_message = await query.message.edit_text(
        f"🔄 **Initializing Download...**\n\n"
        f"**🎞 {title}**\n"
        f"**📹 {resolution}**\n\n"
        f"⏳ **Preparing download...**"
    )

    # Clear any existing progress data
    progress_data.clear()
    
    # Create download task
    async def run_download():
        ydl_opts = {
            'format': f"{format_id}+bestaudio[ext=m4a]",
            'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }],
            'progress_hooks': [progress_hook]
        }

        loop = asyncio.get_event_loop()
        
        def download():
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info_dict), info_dict
            except Exception as e:
                return None, str(e)
        
        return await loop.run_in_executor(None, download)

    # Start progress monitoring task
    async def monitor_progress():
        last_message = ""
        video_done = False
        audio_done = False
        
        while True:
            try:
                current_message = ""
                current_progress = None
                
                # Look for the most recent progress
                for key, data in progress_data.items():
                    if data['timestamp'] > time.time() - 5:  # Only consider recent data
                        current_progress = data
                        break
                
                if current_progress:
                    if current_progress['status'] == 'downloading':
                        phase = current_progress['phase']
                        percentage = current_progress['percentage']
                        downloaded = humanbytes(current_progress['downloaded'])
                        total = humanbytes(current_progress['total']) if current_progress['total'] > 0 else "Unknown"
                        speed = format_speed(current_progress['speed'])
                        eta = format_time(current_progress['eta'])
                        progress_bar = create_progress_bar(percentage)
                        
                        current_message = (
                            f"{phase}...\n\n"
                            f"**🎞 {title}**\n"
                            f"**📹 {resolution}**\n\n"
                            f"{progress_bar}\n\n"
                            f"**📊 Downloaded:** {downloaded} / {total}\n"
                            f"**⚡ Speed:** {speed}\n"
                            f"**⏱️ ETA:** {eta}"
                        )
                        
                    elif current_progress['status'] == 'finished':
                        phase = current_progress['phase']
                        next_phase = current_progress.get('next_phase', '')
                        size = humanbytes(current_progress['total_bytes'])
                        
                        if "Video" in phase:
                            video_done = True
                        elif "Audio" in phase:
                            audio_done = True
                        
                        current_message = (
                            f"{phase}!\n\n"
                            f"**🎞 {title}**\n"
                            f"**📹 {resolution}**\n\n"
                            f"**📁 Size:** {size}\n\n"
                            f"{next_phase}"
                        )
                
                # If both video and audio are done, show merging message
                if video_done and audio_done and not current_progress:
                    current_message = (
                        f"🔄 **Merging Complete!**\n\n"
                        f"**🎞 {title}**\n"
                        f"**📹 {resolution}**\n\n"
                        f"✅ **Processing final file...**"
                    )
                
                # Update message only if content changed
                if current_message and current_message != last_message:
                    try:
                        await download_message.edit_text(current_message)
                        last_message = current_message
                    except Exception:
                        # Ignore edit errors
                        pass
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception:
                # Continue monitoring despite errors
                await asyncio.sleep(2)

    # Start both tasks
    monitor_task = asyncio.create_task(monitor_progress())
    
    try:
        # Wait for download
        result = await run_download()
        downloaded_path, info_or_error = result
        
        # Stop monitoring
        monitor_task.cancel()
        
        if downloaded_path is None:
            await download_message.edit_text(f"❌ **Error during download:** {info_or_error}")
            return
        
        info_dict = info_or_error
        
    except Exception as e:
        monitor_task.cancel()
        await download_message.edit_text(f"❌ **Error during download:** {str(e)}")
        return

    # Clear progress data
    progress_data.clear()
    
    # Show final completion message
    await download_message.edit_text(
        f"✅ **Download Complete!**\n\n"
        f"**🎞 {title}**\n"
        f"**📹 {resolution}**\n\n"
        f"🔄 **Processing video file...**"
    )

    try:
        final_filesize = os.path.getsize(downloaded_path)
        video = VideoFileClip(downloaded_path)
        duration = int(video.duration)
        video_width, video_height = video.size
        video.close()
        filesize = humanbytes(final_filesize)
    except Exception as e:
        await download_message.edit_text(f"❌ **Error processing video file:** {str(e)}")
        return

    # Process thumbnail
    thumb_url = info_dict.get('thumbnail', None)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    
    if thumb_url:
        try:
            response = requests.get(thumb_url, timeout=10)
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
        except:
            thumb_path = None
    else:
        thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎥 **{resolution}**   |   🗂 **{filesize}**\n"
    )

    # Update message for upload preparation
    await download_message.edit_text(
        f"✅ **Ready to Upload!**\n\n"
        f"**🎞 {title}**\n"
        f"**📹 {resolution}**\n\n"
        f"🚀 **Starting upload...**"
    )

    uploading_message = await bot.send_photo(
        chat_id=query.message.chat.id,
        photo=thumb_path if thumb_path else "https://via.placeholder.com/300x300/1f1f1f/ffffff?text=📤",
        caption="🚀 **Upload starting...** 📤"
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
    await download_message.delete()

    # Clean up files
    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

@Client.on_callback_query(filters.regex(r'^audio_\d+_https?://(www\.)?youtube\.com/watch\?v='))
async def audio_callback_handler(bot, query):
    global progress_data
    
    data = query.data.split('_')
    format_id = data[1]
    url = query.data.split('_', 2)[2]

    title = query.message.caption.split('🎞 ')[1].split('\n')[0]

    download_message = await query.message.edit_text(
        f"🔄 **Initializing Audio Download...**\n\n"
        f"**🎞 {title}**\n"
        f"**🎧 Audio Only**\n\n"
        f"⏳ **Preparing download...**"
    )

    # Clear progress data
    progress_data.clear()

    async def run_download():
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(DOWNLOAD_LOCATION, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook]
        }

        loop = asyncio.get_event_loop()
        
        def download():
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info_dict), info_dict
            except Exception as e:
                return None, str(e)
        
        return await loop.run_in_executor(None, download)

    async def monitor_progress():
        last_message = ""
        
        while True:
            try:
                current_message = ""
                current_progress = None
                
                for key, data in progress_data.items():
                    if data['timestamp'] > time.time() - 5:
                        current_progress = data
                        break
                
                if current_progress:
                    if current_progress['status'] == 'downloading':
                        percentage = current_progress['percentage']
                        downloaded = humanbytes(current_progress['downloaded'])
                        total = humanbytes(current_progress['total']) if current_progress['total'] > 0 else "Unknown"
                        speed = format_speed(current_progress['speed'])
                        eta = format_time(current_progress['eta'])
                        progress_bar = create_progress_bar(percentage)
                        
                        current_message = (
                            f"🎧 **Downloading Audio...**\n\n"
                            f"**🎞 {title}**\n"
                            f"**🎧 Audio Only**\n\n"
                            f"{progress_bar}\n\n"
                            f"**📊 Downloaded:** {downloaded} / {total}\n"
                            f"**⚡ Speed:** {speed}\n"
                            f"**⏱️ ETA:** {eta}"
                        )
                        
                    elif current_progress['status'] == 'finished':
                        size = humanbytes(current_progress['total_bytes'])
                        
                        current_message = (
                            f"✅ **Audio Downloaded!**\n\n"
                            f"**🎞 {title}**\n"
                            f"**🎧 Audio Only**\n\n"
                            f"**📁 Size:** {size}\n\n"
                            f"🎉 **Ready to upload!**"
                        )
                
                if current_message and current_message != last_message:
                    try:
                        await download_message.edit_text(current_message)
                        last_message = current_message
                    except Exception:
                        pass
                
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)

    monitor_task = asyncio.create_task(monitor_progress())
    
    try:
        result = await run_download()
        downloaded_path, info_or_error = result
        
        monitor_task.cancel()
        
        if downloaded_path is None:
            await download_message.edit_text(f"❌ **Error during audio download:** {info_or_error}")
            return
        
        info_dict = info_or_error
        
    except Exception as e:
        monitor_task.cancel()
        await download_message.edit_text(f"❌ **Error during audio download:** {str(e)}")
        return

    progress_data.clear()

    final_filesize = os.path.getsize(downloaded_path)
    filesize = humanbytes(final_filesize)

    thumb_url = info_dict.get('thumbnail', None)
    thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
    if thumb_url:
        try:
            response = requests.get(thumb_url, timeout=10)
            if response.status_code == 200:
                with open(thumb_path, 'wb') as thumb_file:
                    thumb_file.write(response.content)
            else:
                thumb_path = None
        except:
            thumb_path = None
    else:
        thumb_path = None

    caption = (
        f"**🎞 {info_dict['title']}   |   [🔗 URL]({url})**\n\n"
        f"🎧 **Audio**   |   🗂 **{filesize}**\n"
    )

    await download_message.edit_text(
        f"✅ **Audio Download Complete!**\n\n"
        f"**🎞 {title}**\n"
        f"**🎧 Audio Only**\n\n"
        f"🚀 **Preparing to upload...**"
    )

    uploading_message = await bot.send_photo(
        chat_id=query.message.chat.id,
        photo=thumb_path if thumb_path else "https://via.placeholder.com/300x300/1f1f1f/ffffff?text=🎧",
        caption="🚀 **Audio uploading...** 📤"
    )

    c_time = time.time()
    try:
        await bot.send_audio(
            chat_id=query.message.chat.id,
            audio=downloaded_path,
            thumb=thumb_path,
            caption=caption,
            progress=progress_message,
            progress_args=(f"**📤 Audio Uploading...\n\n🎞 {info_dict['title']}**", uploading_message, c_time)
        )
    except Exception as e:
        await uploading_message.edit_text(f"❌ **Error during audio upload:** {str(e)}")
        return

    await uploading_message.delete()
    await download_message.delete()

    if os.path.exists(downloaded_path):
        os.remove(downloaded_path)
    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

@Client.on_callback_query(filters.regex(r'^thumb_https?://(www\.)?youtube\.com/watch\?v='))
async def thumb_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])
    ydl_opts = {'quiet': True}

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            thumb_url = info_dict.get('thumbnail', None)
    except Exception as e:
        await query.message.edit_text(f"❌ **Error getting thumbnail:** {str(e)}")
        return

    if not thumb_url:
        await query.message.edit_text("❌ **No thumbnail found for this video.**")
        return

    try:
        thumb_response = requests.get(thumb_url, timeout=10)
        if thumb_response.status_code == 200:
            thumb_path = os.path.join(DOWNLOAD_LOCATION, 'thumb.jpg')
            with open(thumb_path, 'wb') as thumb_file:
                thumb_file.write(thumb_response.content)
            await bot.send_photo(chat_id=query.message.chat.id, photo=thumb_path)
            os.remove(thumb_path)
        else:
            await query.message.edit_text("❌ **Failed to download thumbnail.**")
    except Exception as e:
        await query.message.edit_text(f"❌ **Error downloading thumbnail:** {str(e)}")

@Client.on_callback_query(filters.regex(r'^desc_https?://(www\.)?youtube\.com/watch\?v='))
async def description_callback_handler(bot, query):
    url = '_'.join(query.data.split('_')[1:])

    ydl_opts = {'quiet': True}
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            description = info_dict.get('description', 'No description available.')
    except Exception as e:
        await query.message.edit_text(f"❌ **Error getting description:** {str(e)}")
        return

    if len(description) > 4096:
        description = description[:4093] + "..."

    await bot.send_message(chat_id=query.message.chat.id, text=f"**📝 Description:**\n\n{description}")
