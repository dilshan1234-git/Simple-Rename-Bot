import os
import time
import json
import asyncio
import instaloader
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# ----------------------
# Paths & folders
# ----------------------
INSTA_FOLDER = os.path.join(DOWNLOAD_LOCATION, "insta")
ALBUM_FOLDER = os.path.join(INSTA_FOLDER, "album")
VIDEO_FOLDER = os.path.join(INSTA_FOLDER, "video")
DOWNLOAD_FOLDER = VIDEO_FOLDER  # For yt-dlp downloads

# ----------------------
# Google Colab style cookie setup
# ----------------------
COOKIE_JSON = "/content/cookies.json"  # JSON exported from browser
COOKIE_FILE_TXT = "/content/cookies.txt"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(ALBUM_FOLDER, exist_ok=True)

def convert_json_to_netscape(json_file, output_file):
    """Convert JSON cookies to Netscape format for compatibility"""
    try:
        with open(json_file, "r", encoding="utf-8-sig") as f:  # handles BOM
            cookies = json.load(f)

        lines = [
            "# Netscape HTTP Cookie File",
            "# This file was generated automatically from JSON cookies",
            "# https://curl.se/docs/http-cookies.html\n"
        ]

        for c in cookies:
            domain = c.get("domain", ".instagram.com")
            tailmatch = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expires = str(c.get("expirationDate", 0) or 0)
            name = c.get("name")
            value = c.get("value")
            if name and value:
                value = value.replace("\n", "")
                line = "\t".join([domain, tailmatch, path, secure, expires, name, value])
                lines.append(line)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"✅ Converted JSON cookies to Netscape format: {output_file}")
    except FileNotFoundError:
        print(f"⚠️ Cookie file not found: {json_file}")
    except Exception as e:
        print(f"❌ Error converting cookies: {e}")

# Convert cookies on startup
if os.path.exists(COOKIE_JSON):
    convert_json_to_netscape(COOKIE_JSON, COOKIE_FILE_TXT)
else:
    print(f"⚠️ Cookie JSON file not found at {COOKIE_JSON}")

# ----------------------
# In-memory state
# ----------------------
INSTADL_STATE = {}  # chat_id -> dict { step, last_msgs: [msg_id,...], data: {...} }

# ----------------------
# Helper functions
# ----------------------
async def send_clean(bot, chat_id, text, reply_markup=None, reply_to_message_id=None):
    """Send a message and track it for cleanup"""
    msg = await bot.send_message(
        chat_id, 
        text, 
        reply_markup=reply_markup, 
        reply_to_message_id=reply_to_message_id
    )
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["last_msgs"].append(msg.id)
    if len(st["last_msgs"]) > 8:
        st["last_msgs"].pop(0)
    return msg

async def cleanup_old(bot, chat_id):
    """Delete old tracked messages"""
    st = INSTADL_STATE.get(chat_id)
    if not st:
        return
    for mid in st.get("last_msgs", []):
        try:
            await bot.delete_messages(chat_id, mid)
        except Exception as e:
            print(f"Could not delete message {mid}: {e}")
    st["last_msgs"] = []

def extract_shortcode(url: str):
    """Extract Instagram shortcode from URL"""
    try:
        parts = url.split("/")
        for i, p in enumerate(parts):
            if p in ("p", "reel", "tv") and i + 1 < len(parts):
                return parts[i + 1].split("?")[0]
        segs = [s for s in parts if s]
        if segs:
            return segs[-1].split("?")[0]
    except Exception as e:
        print(f"Error extracting shortcode: {e}")
    return None

# ----------------------
# /instadl command
# ----------------------
@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_start(bot, msg):
    """Start Instagram download flow"""
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("⚠️ Reply to an Instagram post URL with /instadl.")

    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return await msg.reply_text("❌ Couldn't parse shortcode. Use a valid Instagram URL.")

    chat_id = msg.chat.id
    INSTADL_STATE[chat_id] = {
        "step": "choose", 
        "last_msgs": [], 
        "data": {"url": url, "shortcode": shortcode}
    }

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
                InlineKeyboardButton("🎞 Video / Reel", callback_data="insta_video")
            ]
        ]
    )
    await cleanup_old(bot, chat_id)
    await send_clean(
        bot, 
        chat_id, 
        "Select your download method:", 
        reply_markup=kb, 
        reply_to_message_id=msg.id
    )

# ----------------------
# Callback handler
# ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
async def instadl_cb(bot, cq):
    """Handle download method selection"""
    choice = cq.data.split("_")[1]
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice

    try:
        await cq.message.delete()
    except Exception as e:
        print(f"Could not delete callback message: {e}")

    if choice == "album":
        st["step"] = "downloading_album"
        await handle_album_download(bot, chat_id)
    else:
        st["step"] = "downloading_video"
        await handle_video_download(bot, chat_id)

# ----------------------
# Album download
# ----------------------
async def handle_album_download(bot, chat_id):
    """Download Instagram album/carousel images"""
    st = INSTADL_STATE[chat_id]
    shortcode = st["data"]["shortcode"]

    # Clean album folder
    for f in os.listdir(ALBUM_FOLDER):
        try: 
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except Exception as e:
            print(f"Error removing {f}: {e}")

    msg = await send_clean(bot, chat_id, "📥 Initializing download...")

    L = instaloader.Instaloader(
        download_videos=False, 
        download_video_thumbnails=False, 
        dirname_pattern=ALBUM_FOLDER
    )
    
    # Load cookies
    try:
        L.context._session.cookies.clear()
        
        if not os.path.exists(COOKIE_FILE_TXT):
            await msg.edit(f"❌ Cookie file not found: {COOKIE_FILE_TXT}")
            INSTADL_STATE.pop(chat_id, None)
            return
            
        with open(COOKIE_FILE_TXT, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) != 7:
                    continue
                domain, tailmatch, path, secure, expires, name, value = parts
                secure = secure.upper() == "TRUE"
                value = value.strip('"')
                L.context._session.cookies.set(
                    name, value, domain=domain, path=path, secure=secure
                )
        print("✅ Cookies loaded successfully")
    except Exception as e:
        await msg.edit(f"❌ Failed to load cookies: {e}")
        INSTADL_STATE.pop(chat_id, None)
        return

    # Fetch post
    try:
        await msg.edit("📥 Fetching post information...")
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        sidecar = list(post.get_sidecar_nodes()) if post.typename == 'GraphSidecar' else [post]
        total = len(sidecar)
        await msg.edit(f"📥 Found {total} image(s). Starting download...")
    except Exception as e:
        await msg.edit(f"❌ Failed to fetch post: {e}\n\nPossible issues:\n• Invalid URL\n• Private account\n• Expired cookies")
        INSTADL_STATE.pop(chat_id, None)
        return

    # Download and upload images
    downloaded_files = []
    for i, node in enumerate(sidecar, 1):
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        
        try:
            await msg.edit(f"📥 Downloading image {i}/{total}...")
            
            # Try instaloader download first
            try:
                L.download_pic(filename, node.display_url, mtime=post.date_utc)
            except:
                # Fallback to requests
                import requests
                r = requests.get(node.display_url, timeout=30)
                r.raise_for_status()
                with open(filename, "wb") as f:
                    f.write(r.content)
            
            # Verify file was downloaded
            if not os.path.exists(filename):
                raise Exception("File not created")
            
            file_size = os.path.getsize(filename)
            if file_size == 0:
                raise Exception("Empty file downloaded")
                
            print(f"✅ Downloaded image {i}: {filename} ({file_size} bytes)")
            downloaded_files.append(filename)
            
        except Exception as e:
            print(f"❌ Error downloading image {i}: {e}")
            await msg.edit(f"⚠️ Failed to download image {i}/{total}: {e}\nContinuing...")
            await asyncio.sleep(2)
            continue

    # Upload downloaded images
    if not downloaded_files:
        await msg.edit("❌ No images were downloaded successfully.")
        INSTADL_STATE.pop(chat_id, None)
        return

    await msg.edit(f"📤 Uploading {len(downloaded_files)} image(s)...")
    
    uploaded_count = 0
    for i, filepath in enumerate(downloaded_files, 1):
        try:
            await msg.edit(f"📤 Uploading image {i}/{len(downloaded_files)}...")
            
            file_size = humanbytes(os.path.getsize(filepath))
            caption = f"Image {i}/{len(downloaded_files)}\n💽 Size: {file_size}"
            
            await bot.send_document(
                chat_id, 
                document=filepath, 
                caption=caption
            )
            uploaded_count += 1
            print(f"✅ Uploaded image {i}")
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Warning: Could not delete {filepath}: {e}")
                
        except Exception as e:
            print(f"❌ Error uploading image {i}: {e}")
            await msg.edit(f"⚠️ Failed to upload image {i}/{len(downloaded_files)}: {e}")
            await asyncio.sleep(2)

    # Final status
    if uploaded_count == len(downloaded_files):
        await msg.edit(f"✅ Successfully uploaded all {uploaded_count} images!")
    else:
        await msg.edit(f"⚠️ Uploaded {uploaded_count}/{len(downloaded_files)} images. Some failed.")
    
    # Clean up any remaining files
    for f in os.listdir(ALBUM_FOLDER):
        try:
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except:
            pass
    
    # Keep final message for 5 seconds then clean up
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except:
        pass
    
    INSTADL_STATE.pop(chat_id, None)

# ----------------------
# Video/reel download
# ----------------------
async def handle_video_download(bot, chat_id):
    """Download Instagram video or reel"""
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    # Clean video folder
    for f in os.listdir(VIDEO_FOLDER):
        try:
            os.remove(os.path.join(VIDEO_FOLDER, f))
        except Exception as e:
            print(f"Error removing {f}: {e}")

    status_msg = await send_clean(bot, chat_id, "📥 Preparing to download video...")

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "cookiefile": COOKIE_FILE_TXT,
        "retries": 5,
        "fragment_retries": 5,
        "sleep_interval": 2,
        "max_sleep_interval": 5,
        "quiet": False,
        "no_warnings": False,
    }

    def ytdl_hook(d):
        """Progress hook for yt-dlp downloads"""
        try:
            if d.get("status") == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)
                percent = int(downloaded_bytes / total_bytes * 100) if total_bytes else 0
                text = f"📥 Downloading video: {os.path.basename(d.get('filename',''))}\n{percent}% • {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes or 0)}"
                asyncio.create_task(status_msg.edit(text))
            elif d.get("status") == "finished":
                asyncio.create_task(status_msg.edit("⚙️ Merging/processing video..."))
        except Exception as e:
            print(f"Progress hook error: {e}")

    ydl_opts["progress_hooks"] = [ytdl_hook]

    # Download video
    try:
        await status_msg.edit("📥 Starting download with yt-dlp...")
        
        loop = asyncio.get_event_loop()
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        
        await loop.run_in_executor(None, run_ydl)
        print("✅ Video downloaded successfully")
        
    except Exception as e:
        await status_msg.edit(f"❌ Download failed: {e}\n\nPossible issues:\n• Invalid URL\n• Private account\n• Expired cookies")
        INSTADL_STATE.pop(chat_id, None)
        return

    # Find downloaded file
    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        await status_msg.edit("❌ Downloaded file not found.")
        INSTADL_STATE.pop(chat_id, None)
        return

    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    # Get video duration
    duration = None
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(file_path)
        duration = int(clip.duration)
        clip.close()
    except Exception as e:
        print(f"Could not get video duration: {e}")

    filesize = humanbytes(os.path.getsize(file_path))
    cap = f"{file_name}\n\n💽 Size: {filesize}\n🕒 Duration: {duration or 'Unknown'} seconds"

    # Upload video
    try:
        await status_msg.edit("🚀 Uploading video...")
        c_time = time.time()
        await bot.send_video(
            chat_id,
            video=file_path,
            caption=cap,
            progress=progress_message,
            progress_args=("Upload Started..... Thanks To All Who Supported ❤", status_msg, c_time)
        )
        print("✅ Video uploaded successfully")
    except Exception as e:
        await status_msg.edit(f"❌ Upload failed: {e}")
        print(f"Upload error: {e}")
    finally:
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Could not delete video file: {e}")

    # Cleanup
    try:
        await asyncio.sleep(3)
        await status_msg.delete()
    except:
        pass
    
    INSTADL_STATE.pop(chat_id, None)
