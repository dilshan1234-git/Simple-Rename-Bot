import time, os, json, zipfile, asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, CAPTION, ADMIN
from main.utils import progress_message, humanbytes
import instaloader
import yt_dlp
from moviepy.editor import VideoFileClip

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
    
    # Create inline keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Album", callback_data=f"album:{url}"),
            InlineKeyboardButton("🎥 Video/Reel", callback_data=f"video:{url}")
        ]
    ])
    
    await msg.reply_text("📱 **Select Download Method:**", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^album:"))
async def handle_album_download(bot, callback_query: CallbackQuery):
    url = callback_query.data.split(":", 1)[1]
    user_id = callback_query.from_user.id
    
    # Store state
    user_states[user_id] = {"type": "album", "url": url}
    
    await callback_query.edit_message_text("📝 **Send name for your ZIP file:**")

@Client.on_callback_query(filters.regex(r"^video:"))
async def handle_video_download(bot, callback_query: CallbackQuery):
    url = callback_query.data.split(":", 1)[1]
    user_id = callback_query.from_user.id
    
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

@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def handle_zip_name(bot, msg):
    user_id = msg.from_user.id
    
    if user_id not in user_states or user_states[user_id]["type"] != "album":
        return
    
    zip_name = msg.text.strip()
    if not zip_name.endswith('.zip'):
        zip_name += '.zip'
    
    url = user_states[user_id]["url"]
    
    # Delete user state
    del user_states[user_id]
    
    sts = await msg.reply_text("🔍 **Fetching album information...**")
    
    try:
        # Extract shortcode from URL
        if "/p/" in url:
            shortcode = url.split("/p/")[1].split("/")[0]
        elif "/reel/" in url:
            shortcode = url.split("/reel/")[1].split("/")[0]
        else:
            await sts.edit_text("❌ **Invalid Instagram URL**")
            return
        
        # Fetch post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Check if it's an album
        if not post.mediacount > 1:
            await sts.edit_text("❌ **This is not an album. Use Video/Reel option instead.**")
            return
        
        # Create folder
        folder = f"{DOWNLOAD_LOCATION}/album_{user_id}_{int(time.time())}"
        os.makedirs(folder, exist_ok=True)
        
        total_images = post.mediacount
        await sts.edit_text(f"📸 **Downloading images: 0/{total_images}**")
        
        # Download images
        i = 1
        for node in post.get_sidecar_nodes():
            try:
                L.download_pic(
                    os.path.join(folder, f"image_{i:03d}.jpg"),
                    url=node.display_url,
                    mtime=post.date_utc
                )
                await sts.edit_text(f"📸 **Downloading images: {i}/{total_images}**")
                i += 1
            except Exception as e:
                print(f"Failed to download image {i}: {e}")
                continue
        
        await sts.edit_text("📦 **Zipping images...**")
        
        # Create ZIP
        zip_path = os.path.join(DOWNLOAD_LOCATION, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in os.listdir(folder):
                file_path = os.path.join(folder, file)
                zipf.write(file_path, arcname=file)
        
        # Get ZIP file size
        zip_size = os.path.getsize(zip_path)
        zip_size_str = humanbytes(zip_size)
        
        await sts.edit_text(f"📤 **Uploading: {zip_name}**")
        c_time = time.time()
        
        # Upload ZIP
        try:
            caption = f"📦 **{zip_name}**\n\n📸 Images: {i-1}\n💽 Size: {zip_size_str}"
            
            await bot.send_document(
                msg.chat.id,
                document=zip_path,
                caption=caption,
                progress=progress_message,
                progress_args=(f"📤 Uploading: {zip_name}", sts, c_time)
            )
            
            # Clean up
            try:
                os.remove(zip_path)
                for file in os.listdir(folder):
                    os.remove(os.path.join(folder, file))
                os.rmdir(folder)
            except:
                pass
                
            await sts.delete()
            
        except Exception as e:
            await sts.edit_text(f"❌ **Upload failed:** {str(e)}")
    
    except Exception as e:
        await sts.edit_text(f"❌ **Error:** {str(e)}")

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

# Add timestamp to user states
def add_timestamp_to_state(user_id):
    if user_id in user_states:
        user_states[user_id]["timestamp"] = time.time()

# Update the callback handlers to include timestamps
@Client.on_callback_query(filters.regex(r"^album:"))
async def handle_album_download_updated(bot, callback_query: CallbackQuery):
    url = callback_query.data.split(":", 1)[1]
    user_id = callback_query.from_user.id
    
    # Store state with timestamp
    user_states[user_id] = {"type": "album", "url": url, "timestamp": time.time()}
    
    await callback_query.edit_message_text("📝 **Send name for your ZIP file:**")
