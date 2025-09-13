# main/instadl.py
import os
import time
import json
import zipfile
import requests
import instaloader
import yt_dlp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# ----------------------
# Paths & folders
# ----------------------
COOKIES_PATH = os.path.join("main", "downloader", "cookies.json")
INSTA_FOLDER = os.path.join(DOWNLOAD_LOCATION, "insta")
ALBUM_FOLDER = os.path.join(INSTA_FOLDER, "album")
VIDEO_FOLDER = os.path.join(INSTA_FOLDER, "video")

# ----------------------
# In-memory state
# ----------------------
INSTADL_STATE = {}  # chat_id -> {step, last_msgs, data}

# Semaphore to limit concurrent downloads
download_semaphore = asyncio.Semaphore(2)  # Allow max 2 concurrent downloads

# ----------------------
# Helper functions
# ----------------------
def extract_shortcode(url: str):
    try:
        parts = url.split("/")
        for i, p in enumerate(parts):
            if p in ("p", "reel", "tv") and i + 1 < len(parts):
                return parts[i + 1].split("?")[0]
        segs = [s for s in parts if s]
        if segs:
            return segs[-1].split("?")[0]
    except:
        pass
    return None

def load_cookies():
    if not os.path.exists(COOKIES_PATH):
        return False
    try:
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        return cookies
    except:
        return False

async def send_clean(bot, chat_id, text, reply_markup=None, reply_to_message_id=None):
    """Send message and track for cleanup"""
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id)
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["last_msgs"].append(msg.id)
    if len(st["last_msgs"]) > 8:
        st["last_msgs"].pop(0)
    return msg

async def cleanup_old(bot, chat_id):
    st = INSTADL_STATE.get(chat_id)
    if not st:
        return
    for mid in st.get("last_msgs", []):
        try:
            await bot.delete_messages(chat_id, mid)
        except:
            pass
    st["last_msgs"] = []

# ----------------------
# Step 1: /instadl command
# ----------------------
@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_start(bot, msg):
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("Reply to an Instagram URL with /instadl.")
    
    chat_id = msg.chat.id
    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return await msg.reply_text("Couldn't parse shortcode. Use a valid Instagram URL.")

    # Check if already processing
    if download_semaphore.locked():
        return await msg.reply_text("⏳ Already processing downloads. Please wait and try again.")

    INSTADL_STATE[chat_id] = {"step": "await_cookies", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}
    await cleanup_old(bot, chat_id)
    await send_clean(bot, chat_id, "Please send your `cookies.json` file to proceed.", reply_to_message_id=msg.id, reply_markup=ForceReply(selective=True))

# ----------------------
# Step 2: Receive cookies.json
# ----------------------
@Client.on_message(filters.private & filters.document & filters.user(ADMIN))
async def instadl_receive_cookies(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_cookies":
        return

    file_name = msg.document.file_name
    if not file_name.endswith(".json"):
        return await msg.reply_text("❌ Invalid file. Please send your cookies.json file.")

    download_path = COOKIES_PATH
    await msg.download(download_path)
    st["step"] = "choose_download"
    await send_clean(bot, chat_id, "✅ Cookies added successfully!")

    # Show choice buttons
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
         InlineKeyboardButton("🎞 Video / Reel", callback_data="insta_video")]
    ])
    await send_clean(bot, chat_id, "Select your download method:", reply_markup=kb)

# ----------------------
# Step 3: Choice buttons
# ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
async def instadl_choice(bot, cq):
    chat_id = cq.message.chat.id
    choice = cq.data.split("_")[1]
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice
    await cq.message.delete()
    
    if choice == "album":
        st["step"] = "await_zipname"
        prompt = await send_clean(bot, chat_id, "Send ZIP filename (with or without .zip):")
        await send_clean(bot, chat_id, "Reply to that message with the ZIP name.", reply_to_message_id=prompt.id, reply_markup=ForceReply(selective=True))
    else:
        st["step"] = "downloading_video"
        await handle_video(bot, chat_id)

# ----------------------
# Step 4: Receive ZIP name
# ----------------------
@Client.on_message(filters.private & filters.user(ADMIN))
async def instadl_receive_zip(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_zipname":
        return

    zipname = msg.text.strip()
    if not zipname.lower().endswith(".zip"):
        zipname += ".zip"
    st["data"]["zipname"] = zipname
    st["step"] = "downloading_album"
    await handle_album(bot, chat_id)

# ----------------------
# Step 5: Album download (Non-blocking)
# ----------------------
async def handle_album(bot, chat_id):
    async with download_semaphore:  # Limit concurrent downloads
        st = INSTADL_STATE[chat_id]
        shortcode = st["data"]["shortcode"]
        zipname = st["data"]["zipname"]

        # Create folders in executor to avoid blocking
        await asyncio.get_event_loop().run_in_executor(None, setup_album_folder)
        
        msg = await send_clean(bot, chat_id, "📥 Downloading images...")

        try:
            # Run instaloader operations in executor to avoid blocking
            sidecar, total = await asyncio.get_event_loop().run_in_executor(
                None, get_post_sidecar, shortcode
            )
            
            if total == 0:
                await msg.edit("❌ No images found in this post.")
                return

            await msg.edit(f"📥 Downloading images... (0/{total})")
            
            # Download images in executor with progress updates
            await download_album_images(sidecar, msg, total)
            
            # Create ZIP in executor
            zip_path = await asyncio.get_event_loop().run_in_executor(
                None, create_album_zip, zipname
            )
            
            if not zip_path or not os.path.exists(zip_path):
                await msg.edit("❌ Failed to create ZIP file.")
                return

            await msg.edit("🚀 Uploading ZIP...")
            c_time = time.time()
            
            # Upload with progress
            await bot.send_document(
                chat_id, zip_path, 
                caption=zipname, 
                progress=progress_message, 
                progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time)
            )

            # Cleanup in executor
            await asyncio.get_event_loop().run_in_executor(None, cleanup_album_files, zip_path)
            
        except Exception as e:
            await msg.edit(f"❌ Error downloading album: {e}")
        
        finally:
            try:
                await msg.delete()
            except:
                pass
            INSTADL_STATE.pop(chat_id, None)

def setup_album_folder():
    """Setup album folder - runs in executor"""
    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try:
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except:
            pass

def get_post_sidecar(shortcode):
    """Get post sidecar nodes - runs in executor"""
    L = instaloader.Instaloader(
        download_videos=False, 
        download_video_thumbnails=False, 
        dirname_pattern=ALBUM_FOLDER
    )
    load_cookies()
    
    post = instaloader.Post.from_shortcode(L.context, shortcode)
    sidecar = list(post.get_sidecar_nodes())
    if not sidecar:
        sidecar = [post]
    
    return sidecar, len(sidecar)

async def download_album_images(sidecar, msg, total):
    """Download images with progress updates"""
    for i, node in enumerate(sidecar, 1):
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        
        # Download each image in executor
        await asyncio.get_event_loop().run_in_executor(
            None, download_single_image, filename, node.display_url
        )
        
        # Update progress every few images to avoid too many updates
        if i % max(1, total // 10) == 0 or i == total:
            try:
                await msg.edit(f"📥 Downloading images... ({i}/{total})")
            except:
                pass

def download_single_image(filename, url):
    """Download single image - runs in executor"""
    try:
        r = requests.get(url, timeout=30)
        with open(filename, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Failed to download image: {e}")

def create_album_zip(zipname):
    """Create ZIP file - runs in executor"""
    try:
        zip_path = os.path.join(INSTA_FOLDER, zipname)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(os.listdir(ALBUM_FOLDER)):
                file_path = os.path.join(ALBUM_FOLDER, file)
                if os.path.exists(file_path):
                    zf.write(file_path, arcname=file)
        return zip_path
    except Exception as e:
        print(f"Failed to create ZIP: {e}")
        return None

def cleanup_album_files(zip_path):
    """Cleanup files - runs in executor"""
    for f in os.listdir(ALBUM_FOLDER):
        try:
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except:
            pass
    try:
        os.remove(zip_path)
    except:
        pass

# ----------------------
# Step 6: Video download (Non-blocking)
# ----------------------
async def handle_video(bot, chat_id):
    async with download_semaphore:  # Limit concurrent downloads
        st = INSTADL_STATE[chat_id]
        url = st["data"]["url"]

        # Setup video folder in executor
        await asyncio.get_event_loop().run_in_executor(None, setup_video_folder)
        
        msg = await send_clean(bot, chat_id, "📥 Downloading Video/Reel...")

        try:
            # Download video in executor to avoid blocking
            file_info = await asyncio.get_event_loop().run_in_executor(
                None, download_video_with_ytdlp, url
            )
            
            if not file_info:
                await msg.edit("❌ Failed to download video.")
                return
            
            file_path, file_name, filesize = file_info
            cap = f"{file_name}\n\n💽 Size: {filesize}"
            
            await msg.edit(f"📥 Downloaded: {file_name}")
            await msg.edit("🚀 Uploading video...")
            
            c_time = time.time()
            await bot.send_video(
                chat_id, 
                video=file_path, 
                caption=cap, 
                progress=progress_message, 
                progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time)
            )
            
            # Cleanup in executor
            await asyncio.get_event_loop().run_in_executor(None, os.remove, file_path)
            
        except Exception as e:
            await msg.edit(f"❌ Error downloading video: {e}")
        
        finally:
            try:
                await msg.delete()
            except:
                pass
            INSTADL_STATE.pop(chat_id, None)

def setup_video_folder():
    """Setup video folder - runs in executor"""
    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try:
            os.remove(os.path.join(VIDEO_FOLDER, f))
        except:
            pass

def download_video_with_ytdlp(url):
    """Download video with yt-dlp - runs in executor"""
    try:
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "cookies": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
            "quiet": True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
        if not files:
            return None
        
        file_path = os.path.join(VIDEO_FOLDER, files[0])
        file_name = files[0]
        filesize = humanbytes(os.path.getsize(file_path))
        
        return file_path, file_name, filesize
    
    except Exception as e:
        print(f"yt-dlp download error: {e}")
        return None
