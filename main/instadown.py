import os
import json
import time
import random
import instaloader
import yt_dlp
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
# Rate limiting & tracking
# ----------------------
LAST_REQUEST_TIME = {}  # Track last request time per chat
MIN_REQUEST_INTERVAL = 30  # Minimum seconds between requests
MAX_DAILY_REQUESTS = 50   # Maximum requests per day
DAILY_REQUEST_COUNT = {}  # Track daily usage per chat

# ----------------------
# In-memory state
# ----------------------
INSTADL_STATE = {}  # chat_id -> dict { step, last_msgs: [msg_id,...], data: {...} }

# ----------------------
# Helper functions
# ----------------------
async def send_clean(bot, chat_id, text, reply_markup=None, reply_to_message_id=None):
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

def check_rate_limit(chat_id):
    """Check if user is within rate limits"""
    current_time = time.time()
    today = time.strftime("%Y-%m-%d")
    
    # Check daily limit
    daily_key = f"{chat_id}_{today}"
    daily_count = DAILY_REQUEST_COUNT.get(daily_key, 0)
    if daily_count >= MAX_DAILY_REQUESTS:
        return False, f"Daily limit reached ({MAX_DAILY_REQUESTS} downloads per day). Try again tomorrow."
    
    # Check interval limit
    last_time = LAST_REQUEST_TIME.get(chat_id, 0)
    time_diff = current_time - last_time
    if time_diff < MIN_REQUEST_INTERVAL:
        remaining = int(MIN_REQUEST_INTERVAL - time_diff)
        return False, f"Please wait {remaining} seconds before next download."
    
    return True, None

def update_rate_limit(chat_id):
    """Update rate limit counters"""
    current_time = time.time()
    today = time.strftime("%Y-%m-%d")
    daily_key = f"{chat_id}_{today}"
    
    LAST_REQUEST_TIME[chat_id] = current_time
    DAILY_REQUEST_COUNT[daily_key] = DAILY_REQUEST_COUNT.get(daily_key, 0) + 1

def load_cookies_for_instaloader(L):
    if not os.path.exists(COOKIES_PATH):
        print("[INSTADL] Cookies file not found!")
        return False
    try:
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            L.context._session.cookies.set(cookie.get("name"), cookie.get("value"))
        print("[INSTADL] Cookies loaded successfully ✅")
        return True
    except Exception as e:
        print("[INSTADL] Failed loading cookies:", e)
        return False

def get_enhanced_ydl_opts():
    """Get yt-dlp options with better cookie handling and headers"""
    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "cookiefile": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        "sleep_interval": random.randint(1, 3),  # Random delay
        "max_sleep_interval": 5,
        "sleep_interval_subtitles": 1,
        "http_headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip,deflate',
            'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        "extractor_retries": 3,
        "fragment_retries": 3,
        "retry_sleep": 2,
        "skip_unavailable_fragments": True,
    }
    return opts

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

# ----------------------
# /instadl command
# ----------------------
@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_start(bot, msg):
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("Reply to an Instagram post URL with /instadl.")

    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return await msg.reply_text("Couldn't parse shortcode. Use a valid Instagram URL.")

    chat_id = msg.chat.id
    
    # Check rate limits
    allowed, error_msg = check_rate_limit(chat_id)
    if not allowed:
        return await msg.reply_text(f"⚠️ Rate limit exceeded!\n{error_msg}")

    INSTADL_STATE[chat_id] = {"step": "choose", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
             InlineKeyboardButton("🎞 Video / Reel", callback_data="insta_video")]
        ]
    )
    await cleanup_old(bot, chat_id)
    await send_clean(bot, chat_id, "Select your download method:", reply_markup=kb, reply_to_message_id=msg.id)

# ----------------------
# Callback handler
# ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
async def instadl_cb(bot, cq):
    choice = cq.data.split("_")[1]
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice

    try:
        await cq.message.delete()
    except:
        pass

    # Update rate limit when actually starting download
    update_rate_limit(chat_id)

    if choice == "album":
        st["step"] = "downloading_album"
        await handle_album_download(bot, chat_id)
    else:
        st["step"] = "downloading_video"
        await handle_video_download(bot, chat_id)

# ----------------------
# Album download flow (with retry logic)
# ----------------------
async def handle_album_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]
    shortcode = st["data"]["shortcode"]

    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try:
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except:
            pass

    msg = await send_clean(bot, chat_id, "📥 Downloading images... (0/0)")

    # Add random delay before starting
    await asyncio.sleep(random.uniform(1, 3))

    L = instaloader.Instaloader(
        download_videos=False, 
        download_video_thumbnails=False, 
        dirname_pattern=ALBUM_FOLDER,
        sleep=True,  # Enable sleep between requests
        rate_controller=lambda query_type: random.uniform(1, 3)  # Random delays
    )
    
    if not load_cookies_for_instaloader(L):
        await msg.edit("❌ Cookies not loaded or invalid! Please update your cookies.")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            sidecar = list(post.get_sidecar_nodes())
            if not sidecar:
                sidecar = [post]
            total = len(sidecar)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                await msg.edit(f"Attempt {attempt + 1} failed, retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                await msg.edit(f"❌ Failed to fetch post after {max_retries} attempts: {str(e)[:100]}")
                return

    for i, node in enumerate(sidecar, 1):
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        try:
            L.download_pic(filename, node.display_url, mtime=post.date_utc)
        except:
            try:
                import requests
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                r = requests.get(node.display_url, timeout=30, headers=headers)
                with open(filename, "wb") as f:
                    f.write(r.content)
            except:
                pass
        
        try:
            await msg.edit(f"📥 Downloading images... ({i}/{total})")
        except:
            pass

        # Send each image to bot
        try:
            await bot.send_photo(chat_id, photo=filename, caption=f"Image {i}/{total}")
            os.remove(filename)
        except:
            pass
        
        # Small delay between images
        await asyncio.sleep(0.5)

    try:
        await msg.delete()
    except:
        pass
    INSTADL_STATE.pop(chat_id, None)

# ----------------------
# Video/reel download flow (enhanced with retry)
# ----------------------
async def handle_video_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try: 
            os.remove(os.path.join(VIDEO_FOLDER, f))
        except: 
            pass

    status_msg = await send_clean(bot, chat_id, "📥 Preparing to download video...")

    # Add random delay before starting
    import asyncio
    await asyncio.sleep(random.uniform(2, 5))

    ydl_opts = get_enhanced_ydl_opts()

    def ytdl_hook(d):
        try:
            if d.get("status") == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)
                percent = int(downloaded_bytes / total_bytes * 100) if total_bytes else 0
                text = f"📥 Downloading video: {d.get('filename','')}\n{percent}% • {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes or 0)}"
                asyncio.get_event_loop().create_task(status_msg.edit(text))
            elif d.get("status") == "finished":
                asyncio.get_event_loop().create_task(status_msg.edit("🔄 Processing video..."))
        except:
            pass

    ydl_opts["progress_hooks"] = [ytdl_hook]

    # Retry logic for yt-dlp
    max_retries = 3
    success = False
    
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_event_loop()
            def run_ydl():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            
            await loop.run_in_executor(None, run_ydl)
            success = True
            break
            
        except Exception as e:
            error_msg = str(e).lower()
            if "rate" in error_msg or "login" in error_msg or "cookies" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10  # Increase wait time each attempt
                    await status_msg.edit(f"⚠️ Rate limited. Waiting {wait_time} seconds before retry {attempt + 2}/{max_retries}...")
                    await asyncio.sleep(wait_time)
                else:
                    await status_msg.edit("❌ Download failed due to rate limiting. Please wait longer before trying again or update your cookies.")
                    INSTADL_STATE.pop(chat_id, None)
                    return
            else:
                if attempt < max_retries - 1:
                    await status_msg.edit(f"❌ Attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(5)
                else:
                    await status_msg.edit(f"❌ Download failed after {max_retries} attempts: {str(e)[:100]}")
                    INSTADL_STATE.pop(chat_id, None)
                    return

    if not success:
        await status_msg.edit("❌ Download failed after all retry attempts.")
        INSTADL_STATE.pop(chat_id, None)
        return

    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        await status_msg.edit("❌ Downloaded file not found.")
        INSTADL_STATE.pop(chat_id, None)
        return

    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    duration = None
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(file_path)
        duration = int(clip.duration)
        clip.close()
    except:
        pass

    filesize = humanbytes(os.path.getsize(file_path))
    cap = f"{file_name}\n\n💽 Size: {filesize}\n🕒 Duration: {duration or 'Unknown'} seconds"

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
    except Exception as e:
        await status_msg.edit(f"Upload failed: {e}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

    try:
        await status_msg.delete()
    except:
        pass
    INSTADL_STATE.pop(chat_id, None)
