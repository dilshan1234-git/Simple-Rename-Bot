import os
import time
import instaloader
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# ----------------------
# Paths & folders
# ----------------------
INSTA_FOLDER = os.path.join(DOWNLOAD_LOCATION, "insta")
ALBUM_FOLDER = os.path.join(INSTA_FOLDER, "album")
VIDEO_FOLDER = os.path.join(INSTA_FOLDER, "video")
COOKIE_FILE = os.path.join("main", "downloader", "insta_cookies.txt")  # saved Netscape cookies

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
# /save_cookie command
# ----------------------
@Client.on_message(filters.private & filters.command("save_cookie") & filters.user(ADMIN))
async def save_cookie_cmd(bot, msg):
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("⚠️ Reply to your Netscape HTTP Cookie content with /save_cookie command.")

    cookie_text = replied.text.strip()
    lines = cookie_text.splitlines()
    processed_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            processed_lines.append(line)
            continue
        # Split on any whitespace (including \xa0)
        parts = line.split()
        if len(parts) >= 7:
            # Fields: domain, tailmatch, path, secure, expires, name, value (value may have spaces)
            domain, tailmatch, path, secure, expires, name = parts[:6]
            value = ' '.join(parts[6:])
            processed_line = '\t'.join([domain, tailmatch, path, secure, expires, name, value])
            processed_lines.append(processed_line)

    if not processed_lines:
        return await msg.reply_text("⚠️ No valid cookie entries found in the provided text.")

    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            for pline in processed_lines:
                f.write(pline + "\n")
        await msg.reply_text("✅ Instagram cookie saved successfully!")
    except Exception as e:
        await msg.reply_text(f"❌ Failed to save cookie: {e}")

# ----------------------
# Cookie loaders
# ----------------------
def load_cookies_for_instaloader(L):
    """Load Netscape cookies into Instaloader session"""
    if not os.path.exists(COOKIE_FILE):
        print("[INSTADL] Cookie file not found!")
        return False
    try:
        L.load_session_from_file("dummy")  # avoid login
        L.context._session.cookies.clear()  # clear default
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, _, path, secure, _, name, value = parts[:7]
                    L.context._session.cookies.set(name, value, domain=domain, path=path)
        print("[INSTADL] Cookies loaded successfully ✅")
        return True
    except Exception as e:
        print("[INSTADL] Failed loading cookies:", e)
        return False

def get_cookiefile_for_yt_dlp():
    """Return cookiefile path for yt-dlp if exists, else None"""
    return COOKIE_FILE if os.path.exists(COOKIE_FILE) else None

# ----------------------
# /instadl command
# ----------------------
@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_start(bot, msg):
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("⚠️ Reply to an Instagram post URL with /instadl.")

    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return await msg.reply_text("❌ Couldn't parse shortcode. Use a valid Instagram URL.")

    chat_id = msg.chat.id
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

    if choice == "album":
        st["step"] = "downloading_album"
        await handle_album_download(bot, chat_id)
    else:
        st["step"] = "downloading_video"
        await handle_video_download(bot, chat_id)

# ----------------------
# Album download flow
# ----------------------
async def handle_album_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]
    shortcode = st["data"]["shortcode"]

    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try: os.remove(os.path.join(ALBUM_FOLDER, f))
        except: pass

    msg = await send_clean(bot, chat_id, "📥 Downloading images... (0/0)")

    L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False, dirname_pattern=ALBUM_FOLDER)
    if not load_cookies_for_instaloader(L):
        await msg.edit("❌ Cookies not loaded or invalid! Use /save_cookie first.")
        return

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        sidecar = list(post.get_sidecar_nodes())
        if not sidecar:
            sidecar = [post]
        total = len(sidecar)
    except Exception as e:
        await msg.edit(f"❌ Failed to fetch post: {e}")
        return

    for i, node in enumerate(sidecar, 1):
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        try:
            L.download_pic(filename, node.display_url, mtime=post.date_utc)
        except:
            try:
                import requests
                r = requests.get(node.display_url, timeout=30)
                with open(filename, "wb") as f:
                    f.write(r.content)
            except:
                pass
        try:
            await msg.edit(f"📥 Downloading images... ({i}/{total})")
        except:
            pass

        try:
            await bot.send_photo(chat_id, photo=filename, caption=f"Image {i}/{total}")
            os.remove(filename)
        except:
            pass

    try:
        await msg.delete()
    except:
        pass
    INSTADL_STATE.pop(chat_id, None)

# ----------------------
# Video/reel download flow
# ----------------------
async def handle_video_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try: os.remove(os.path.join(VIDEO_FOLDER, f))
        except: pass

    status_msg = await send_clean(bot, chat_id, "📥 Preparing to download video...")

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "cookiefile": get_cookiefile_for_yt_dlp(),
        "retries": 5,
        "fragment_retries": 5,
        "sleep_interval": 2,
        "max_sleep_interval": 5,
    }

    def ytdl_hook(d):
        try:
            import asyncio
            if d.get("status") == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)
                percent = int(downloaded_bytes / total_bytes * 100) if total_bytes else 0
                text = f"📥 Downloading video: {os.path.basename(d.get('filename',''))}\n{percent}% • {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes or 0)}"
                asyncio.get_event_loop().create_task(status_msg.edit(text))
            elif d.get("status") == "finished":
                asyncio.get_event_loop().create_task(status_msg.edit("Merging/processing video..."))
        except:
            pass

    ydl_opts["progress_hooks"] = [ytdl_hook]

    import asyncio
    loop = asyncio.get_event_loop()
    def run_ydl():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    await loop.run_in_executor(None, run_ydl)

    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        await status_msg.edit("❌ Downloaded file not found.")
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
        await status_msg.edit(f"❌ Upload failed: {e}")
    finally:
        try: os.remove(file_path)
        except: pass

    try:
        await status_msg.delete()
    except:
        pass
    INSTADL_STATE.pop(chat_id, None)
