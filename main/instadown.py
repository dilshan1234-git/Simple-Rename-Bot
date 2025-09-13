import time, os, zipfile, json, asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, CAPTION, ADMIN
from main.utils import progress_message, humanbytes
import instaloader
import yt_dlp

# Store user states and data
user_states = {}
user_data = {}

# Initialize Instaloader
L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False)

def load_cookies():
    """Load cookies from git repo"""
    cookies_file = "cookies.json"  # Store this file in your git repo root
    try:
        with open(cookies_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        
        # Apply cookies to Instaloader session
        for cookie in cookies:
            L.context._session.cookies.set(cookie["name"], cookie["value"])
        
        return cookies_file
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return None

# Load cookies on startup
cookies_file = load_cookies()

@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instagram_downloader(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.text:
        return await msg.reply_text("Please reply to an Instagram URL with /instadl command")
    
    url = reply.text.strip()
    if "instagram.com" not in url:
        return await msg.reply_text("Please provide a valid Instagram URL")
    
    # Store URL for later use
    user_data[msg.from_user.id] = {"url": url}
    
    # Create inline keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Album", callback_data="dl_album")],
        [InlineKeyboardButton("🎥 Video/Reel", callback_data="dl_video")]
    ])
    
    await msg.reply_text("Select your download method:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^dl_"))
async def handle_download_callback(bot, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_data:
        return await callback_query.answer("Session expired. Please start again.", show_alert=True)
    
    if data == "dl_album":
        user_states[user_id] = "waiting_zip_name"
        await callback_query.edit_message_text("📝 Send name for your zip file (without .zip extension):")
    
    elif data == "dl_video":
        await callback_query.edit_message_text("🔄 Downloading your video/reel...")
        await download_video(bot, callback_query.message, user_data[user_id]["url"])

@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def handle_zip_name(bot, msg):
    user_id = msg.from_user.id
    
    if user_id in user_states and user_states[user_id] == "waiting_zip_name":
        zip_name = msg.text.strip()
        user_data[user_id]["zip_name"] = zip_name
        user_states[user_id] = None
        
        # Delete the message and start downloading
        await msg.delete()
        
        # Start album download
        await download_album(bot, msg, user_data[user_id]["url"], zip_name)

async def download_album(bot, msg, url, zip_name):
    try:
        # Extract shortcode from URL
        if "/p/" in url:
            shortcode = url.split("/p/")[1].split("/")[0]
        else:
            return await msg.reply_text("❌ Invalid Instagram post URL")
        
        # Progress message
        progress_msg = await msg.reply_text("🔄 Downloading your images... 0/0")
        
        # Fetch post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Create folder
        folder = os.path.join(DOWNLOAD_LOCATION, f"album_{int(time.time())}")
        os.makedirs(folder, exist_ok=True)
        
        # Get total images count
        sidecar_nodes = list(post.get_sidecar_nodes())
        total_images = len(sidecar_nodes)
        
        if total_images == 0:
            return await progress_msg.edit("❌ No images found in this post")
        
        # Download images
        for i, node in enumerate(sidecar_nodes, 1):
            await progress_msg.edit(f"🔄 Downloading your images... {i}/{total_images}")
            
            L.download_pic(
                os.path.join(folder, f"image_{i}.jpg"),
                url=node.display_url,
                mtime=post.date_utc
            )
        
        # Zip files
        await progress_msg.edit("📦 Now zipping...")
        zip_path = os.path.join(DOWNLOAD_LOCATION, f"{zip_name}.zip")
        
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for file in os.listdir(folder):
                zipf.write(os.path.join(folder, file), arcname=file)
        
        # Upload zip
        await progress_msg.edit("🚀 Uploading your zip...")
        
        zip_size = os.path.getsize(zip_path)
        caption = f"📦 {zip_name}.zip\n💽 Size: {humanbytes(zip_size)}\n📸 Images: {total_images}"
        
        c_time = time.time()
        await bot.send_document(
            msg.chat.id,
            document=zip_path,
            caption=caption,
            progress=progress_message,
            progress_args=("Upload Started..... Thanks To All Who Supported ❤", progress_msg, c_time)
        )
        
        # Cleanup
        import shutil
        shutil.rmtree(folder)
        os.remove(zip_path)
        await progress_msg.delete()
        
        # Clear user data
        if msg.from_user.id in user_data:
            del user_data[msg.from_user.id]
            
    except Exception as e:
        await progress_msg.edit(f"❌ Error: {str(e)}")

async def download_video(bot, msg, url):
    try:
        if not cookies_file:
            return await msg.edit("❌ Cookies file not found. Please add cookies.json to your git repo.")
        
        # Create folder
        folder = os.path.join(DOWNLOAD_LOCATION, f"video_{int(time.time())}")
        os.makedirs(folder, exist_ok=True)
        
        # Progress tracking
        progress_msg = msg
        download_progress = {"downloaded": 0, "total": 0, "filename": ""}
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                if 'total_bytes' in d:
                    download_progress["total"] = d['total_bytes']
                    download_progress["downloaded"] = d['downloaded_bytes']
                elif 'total_bytes_estimate' in d:
                    download_progress["total"] = d['total_bytes_estimate']
                    download_progress["downloaded"] = d['downloaded_bytes']
                    
            elif d['status'] == 'finished':
                download_progress["filename"] = os.path.basename(d['filename'])
        
        # yt-dlp options
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
            "cookies": cookies_file,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook]
        }
        
        # Download in thread to avoid blocking
        def download_video_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        
        # Run download in executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(download_video_sync)
            
            # Monitor progress
            while not future.done():
                if download_progress["total"] > 0:
                    percent = (download_progress["downloaded"] / download_progress["total"]) * 100
                    downloaded_size = humanbytes(download_progress["downloaded"])
                    total_size = humanbytes(download_progress["total"])
                    
                    progress_text = f"🔄 Downloading your video/reel...\n📊 {percent:.1f}%\n💾 {downloaded_size} / {total_size}"
                    
                    try:
                        await progress_msg.edit(progress_text)
                    except:
                        pass
                
                await asyncio.sleep(2)
            
            # Wait for completion
            future.result()
        
        # Get downloaded file
        files_in_folder = os.listdir(folder)
        if not files_in_folder:
            return await progress_msg.edit("❌ No file was downloaded")
        
        video_file = os.path.join(folder, files_in_folder[0])
        file_size = os.path.getsize(video_file)
        
        # Get filename without extension for caption
        filename = os.path.splitext(files_in_folder[0])[0]
        
        # Upload video
        await progress_msg.edit("🚀 Uploading...")
        
        caption = f"🎥 {filename}\n💽 Size: {humanbytes(file_size)}"
        
        c_time = time.time()
        await bot.send_video(
            msg.chat.id,
            video=video_file,
            caption=caption,
            progress=progress_message,
            progress_args=("Upload Started..... Thanks To All Who Supported ❤", progress_msg, c_time)
        )
        
        # Cleanup
        import shutil
        shutil.rmtree(folder)
        await progress_msg.delete()
        
        # Clear user data
        if msg.from_user.id in user_data:
            del user_data[msg.from_user.id]
            
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)}")

# Add required imports to your main bot file or requirements
"""
Required packages in requirements.txt:
instaloader
yt-dlp
"""
