import time, os, json, asyncio
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
        await callback_query.edit_message_text(f"📸 **Downloading images: 0/{total_images}**")
        
        # Download and send images
        i = 1
        for node in post.get_sidecar_nodes():
            try:
                # Download image
                file_path = os.path.join(folder, f"image_{i:03d}.jpg")
                L.download_pic(
                    filename=file_path,
                    url=node.display_url,
                    mtime=post.date_utc
                )
                
                await callback_query.edit_message_text(f"📸 **Downloading images: {i}/{total_images}**")
                
                # Get file size
                file_size = os.path.getsize(file_path)
                file_size_str = humanbytes(file_size)
                
                # Prepare caption
                caption = f"📸 **Image {i}/{total_images}**\n💽 Size: {file_size_str}"
                
                # Send photo in highest quality
                c_time = time.time()
                sts = await callback_query.message.reply_text(f"📤 **Uploading image {i}/{total_images}**")
                
                await bot.send_photo(
                    callback_query.message.chat.id,
                    photo=file_path,
                    caption=caption,
                    progress=progress_message,
                    progress_args=(f"📤 Uploading image {i}/{total_images}", sts, c_time)
                )
                
                # Clean up individual image
                try:
                    os.remove(file_path)
                except:
                    pass
                
                i += 1
                
            except Exception as e:
                print(f"Failed to download/upload image {i}: {e}")
                continue
        
        # Clean up folder
        try:
            os.rmdir(folder)
        except:
            pass
            
        await callback_query.message.reply_text(f"✅ **Successfully sent {i-1}/{total_images} images**")
        await callback_query.message.delete()
        
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
        
        # yt-dlp options
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
            "cookies": "main/cookies.json",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True
        }
        
        # Download video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Instagram_Video')
            
            # Update message with file name
            await callback_query.edit_message_text(f"📥 **Downloading:** {video_title}")
            
            # Download
            ydl.download([url])
        
        # Get downloaded file
        downloaded_file = None
        for file in os.listdir(folder):
            downloaded_file = os.path.join(folder, file)
            break
        
        if not downloaded_file:
            await callback_query.edit_message_text("❌ **Download failed!**")
            return
        
        # Get file info
        file_size = os.path.getsize(downloaded_file)
        filesize_str = humanbytes(file_size)
        
        # Get video duration
        try:
            video_clip = VideoFileClip(downloaded_file)
            duration = int(video_clip.duration)
            video_clip.close()
        except:
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
            except:
                pass
                
            await sts.delete()
            
        except Exception as e:
            await sts.edit_text(f"❌ **Upload failed:** {str(e)}")
    
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
