import time, os, json, asyncio, requests
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, CAPTION, ADMIN
from main.utils import progress_message, humanbytes
import instaloader
import yt_dlp
from moviepy.editor import VideoFileClip
import uuid

# Initialize Instaloader
L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False)

# Load cookies on startup
def load_cookies():
    try:
        with open("main/cookies.json", "r", encoding="utf-8") as f:
            cookies = json.load(f)
        
        # Apply cookies to Instaloader session
        for cookie in cookies:
            L.context._session.cookies.set(cookie["name"], cookie["value"])
        print("✅ Cookies loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to load cookies: {e}")
        return False

# Load cookies when module imports
load_cookies()

# Store user states
user_states = {}

@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instagram_downloader(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.text:
        return await msg.reply_text("Please reply to an Instagram URL with /instadl command")
    
    url = reply.text.strip()
    if "instagram.com" not in url:
        return await msg.reply_text("Please provide a valid Instagram URL")
    
    # Generate a unique ID for this request
    request_id = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
    
    # Store URL in user_states
    user_id = msg.from_user.id
    user_states[user_id] = {"url": url, "timestamp": time.time()}
    
    # Create inline keyboard with short callback data
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Album", callback_data=f"album:{request_id}"),
            InlineKeyboardButton("🎥 Video/Reel", callback_data=f"video:{request_id}")
        ]
    ])
    
    await msg.reply_text("📱 **Select Download Method:**", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^album:"))
async def handle_album_download(bot, callback_query: CallbackQuery):
    request_id = callback_query.data.split(":", 1)[1]
    user_id = callback_query.from_user.id
    
    # Retrieve URL from user_states
    if user_id not in user_states or "url" not in user_states[user_id]:
        await callback_query.edit_message_text("❌ **Session expired. Please start again with /instadl**")
        return
    
    url = user_states[user_id]["url"]
    
    # Update state with timestamp
    user_states[user_id]["type"] = "album"
    user_states[user_id]["timestamp"] = time.time()
    
    await callback_query.edit_message_text("🔄 **Preparing to download album images...**")
    
    try:
        # Extract shortcode from URL
        if "/p/" in url:
            shortcode = url.split("/p/")[1].split("/")[0]
        elif "/reel/" in url:
            shortcode = url.split("/reel/")[1].split("/")[0]
        else:
            await callback_query.edit_message_text("❌ **Invalid Instagram URL**")
            return
        
        # Fetch post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Check if it's an album
        if not post.mediacount > 1:
            await callback_query.edit_message_text("❌ **This is not an album. Use Video/Reel option instead.**")
            return
        
        # Create folder
        folder = f"{DOWNLOAD_LOCATION}/album_{user_id}_{int(time.time())}"
        os.makedirs(folder, exist_ok=True)
        
        total_images = post.mediacount
        last_message = f"📸 **Downloading images: 0/{total_images}**"
        await callback_query.edit_message_text(last_message)
        
        # Download and send images
        successful_uploads = 0
        i = 1
        
        for node in post.get_sidecar_nodes():
            try:
                # Create proper filename without double extension
                file_path = os.path.join(folder, f"image_{i:03d}.jpg")
                
                # Download image using requests (more reliable than download_pic)
                response = requests.get(node.display_url, stream=True, 
                                      cookies=L.context._session.cookies)
                response.raise_for_status()
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Update progress only if message content changes
                new_message = f"📸 **Downloading images: {i}/{total_images}**"
                if new_message != last_message:
                    await callback_query.edit_message_text(new_message)
                    last_message = new_message
                
                # Verify file exists and has content
                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    print(f"❌ Failed to download image {i}: File not created or empty")
                    i += 1
                    continue
                
                # Get file size
                file_size = os.path.getsize(file_path)
                file_size_str = humanbytes(file_size)
                
                # Prepare caption
                caption = f"📸 **Image {i}/{total_images}**\n💽 Size: {file_size_str}"
                
                # Send photo in highest quality
                c_time = time.time()
                sts = await callback_query.message.reply_text(f"📤 **Uploading image {i}/{total_images}**")
                
                try:
                    await bot.send_photo(
                        callback_query.message.chat.id,
                        photo=file_path,
                        caption=caption,
                        progress=progress_message,
                        progress_args=(f"📤 Uploading image {i}/{total_images}", sts, c_time)
                    )
                    successful_uploads += 1
                    await sts.delete()
                except Exception as upload_error:
                    print(f"❌ Upload failed for image {i}: {upload_error}")
                    await sts.edit_text(f"❌ **Upload failed for image {i}**")
                
                # Clean up individual image
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    print(f"⚠️ Failed to cleanup {file_path}: {cleanup_error}")
                
                i += 1
                
            except Exception as e:
                print(f"❌ Failed to download/upload image {i}: {e}")
                i += 1
                continue
        
        # Clean up folder
        try:
            os.rmdir(folder)
        except Exception as cleanup_error:
            print(f"⚠️ Failed to cleanup folder {folder}: {cleanup_error}")
            
        await callback_query.message.reply_text(f"✅ **Successfully sent {successful_uploads}/{total_images} images**")
        
        # Delete the original selection message
        try:
            await callback_query.message.delete()
        except:
            pass
        
    except Exception as e:
        await callback_query.edit_message_text(f"❌ **Error:** {str(e)}")
    
    # Delete user state
    if user_id in user_states:
        del user_states[user_id]

@Client.on_callback_query(filters.regex(r"^video:"))
async def handle_video_download(bot, callback_query: CallbackQuery):
    request_id = callback_query.data.split(":", 1)[1]
    user_id = callback_query.from_user.id
    
    # Retrieve URL from user_states
    if user_id not in user_states or "url" not in user_states[user_id]:
        await callback_query.edit_message_text("❌ **Session expired. Please start again with /instadl**")
        return
    
    url = user_states[user_id]["url"]
    
    await callback_query.edit_message_text("🔄 **Downloading your video/reel...**")
    
    try:
        # Create folder
        folder = f"{DOWNLOAD_LOCATION}/video_{user_id}_{int(time.time())}"
        os.makedirs(folder, exist_ok=True)
        
        # yt-dlp options with better error handling
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
            "cookiefile": "main/cookies.json",  # Changed from "cookies" to "cookiefile"
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
        }
        
        # Download video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'Instagram_Video')
                
                # Clean title for filename
                video_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                
                # Update message with file name
                await callback_query.edit_message_text(f"📥 **Downloading:** {video_title}")
                
                # Download
                ydl.download([url])
            except Exception as download_error:
                await callback_query.edit_message_text(f"❌ **Download failed:** {str(download_error)}")
                return
        
        # Get downloaded file
        downloaded_file = None
        for file in os.listdir(folder):
            if file.endswith(('.mp4', '.mkv', '.webm', '.avi')):
                downloaded_file = os.path.join(folder, file)
                break
        
        if not downloaded_file or not os.path.exists(downloaded_file):
            await callback_query.edit_message_text("❌ **Download failed! No video file found.**")
            return
        
        # Get file info
        file_size = os.path.getsize(downloaded_file)
        filesize_str = humanbytes(file_size)
        
        # Check file size limit (2GB for Telegram)
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            await callback_query.edit_message_text("❌ **File too large! Maximum size is 2GB.**")
            # Clean up
            try:
                os.remove(downloaded_file)
                os.rmdir(folder)
            except:
                pass
            return
        
        # Get video duration
        try:
            video_clip = VideoFileClip(downloaded_file)
            duration = int(video_clip.duration)
            video_clip.close()
        except Exception as duration_error:
            print(f"⚠️ Failed to get duration: {duration_error}")
            duration = 0
        
        # Prepare caption
        if CAPTION:
            try:
                cap = CAPTION.format(file_name=video_title, file_size=filesize_str, duration=duration)
            except:
                cap = f"📹 **{video_title}**\n\n💽 Size: {filesize_str}\n🕒 Duration: {duration} seconds"
        else:
            cap = f"📹 **{video_title}**\n\n💽 Size: {filesize_str}\n🕒 Duration: {duration} seconds"
        
        # Update message for upload
        sts = await callback_query.edit_message_text(f"📤 **Uploading:** {video_title}")
        c_time = time.time()
        
        # Upload video
        try:
            await bot.send_video(
                callback_query.message.chat.id,
                video=downloaded_file,
                caption=cap,
                duration=duration,
                progress=progress_message,
                progress_args=(f"📤 Uploading: {video_title}", sts, c_time)
            )
            
            # Clean up
            try:
                os.remove(downloaded_file)
                os.rmdir(folder)
            except Exception as cleanup_error:
                print(f"⚠️ Failed to cleanup: {cleanup_error}")
                
            await sts.delete()
            
        except Exception as upload_error:
            await sts.edit_text(f"❌ **Upload failed:** {str(upload_error)}")
    
    except Exception as e:
        await callback_query.edit_message_text(f"❌ **Error:** {str(e)}")
    
    # Delete user state
    if user_id in user_states:
        del user_states[user_id]

# Clean up old user states periodically
async def cleanup_states():
    while True:
        await asyncio.sleep(300)  # Clean every 5 minutes
        current_time = time.time()
        to_remove = []
        
        for user_id, state in user_states.items():
            if current_time - state.get("timestamp", current_time) > 300:  # 5 minutes
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del user_states[user_id]

# Start cleanup task
asyncio.create_task(cleanup_states())
