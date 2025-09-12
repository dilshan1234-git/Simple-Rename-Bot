import os
import json
import time
import zipfile
import asyncio
import instaloader
import yt_dlp
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from config import DOWNLOAD_LOCATION, ADMIN, CAPTION
from main.utils import progress_message, humanbytes

# Put cookies.json in repo: main/downloader/cookies.json
COOKIES_PATH = os.path.join("main", "downloader", "cookies.json")
# Temporary folders inside DOWNLOAD_LOCATION
INSTA_FOLDER = os.path.join(DOWNLOAD_LOCATION, "insta")
ALBUM_FOLDER = os.path.join(INSTA_FOLDER, "album")
VIDEO_FOLDER = os.path.join(INSTA_FOLDER, "video")

# In-memory state for multi-step flow
INSTADL_STATE = {}  # chat_id -> dict { step, last_msgs: [msg_id,...], data: {...} }

# helper: store and delete intermediate messages for clean UI
async def send_clean(bot, chat_id, text, reply_markup=None, reply_to_message_id=None):
    """Send a message and append id to state for cleanup later."""
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id)
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["last_msgs"].append(msg.message_id)
    # keep list short
    if len(st["last_msgs"]) > 8:
        st["last_msgs"].pop(0)
    return msg

async def cleanup_old(bot, chat_id):
    """Delete tracked messages to clean UI."""
    st = INSTADL_STATE.get(chat_id)
    if not st: 
        return
    for mid in st.get("last_msgs", []):
        try:
            await bot.delete_messages(chat_id, mid)
        except:
            pass
    st["last_msgs"] = []

def load_cookies_for_instaloader(L):
    """Load cookies.json into Instaloader session (cookies.json structure from Cookie-Editor)."""
    if not os.path.exists(COOKIES_PATH):
        return False
    try:
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            # instaloader uses requests.Session
            L.context._session.cookies.set(cookie.get("name"), cookie.get("value"))
        return True
    except Exception as e:
        print("Failed loading cookies:", e)
        return False

# parse shortcodes from various instagram URL patterns
def extract_shortcode(url: str):
    try:
        # common patterns: /p/<code>/ or /reel/<code>/ or /tv/<code>/
        parts = url.split("/")
        for i, p in enumerate(parts):
            if p in ("p", "reel", "tv") and i + 1 < len(parts):
                return parts[i + 1].split("?")[0]
        # fallback: if URL contains /<shortcode>?...
        # last non-empty segment
        segs = [s for s in parts if s]
        if segs:
            return segs[-1].split("?")[0]
    except:
        pass
    return None

# ---------------------
# Command entrypoint
# ---------------------
@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_start(bot, msg):
    """
    Use: reply to an Instagram post URL with /instadl
    Shows inline keyboard: Album | Video/Reel
    """
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return await msg.reply_text("Please reply to an Instagram post URL with /instadl (reply to message that contains the URL).")

    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return await msg.reply_text("Couldn't parse shortcode from that URL. Make sure it is a valid Instagram post/reel URL.")

    chat_id = msg.chat.id
    # initialize state
    INSTADL_STATE[chat_id] = {"step": "choose", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Album (images)", callback_data="insta_album"),
             InlineKeyboardButton("Video / Reel", callback_data="insta_video")]
        ]
    )
    await cleanup_old(bot, chat_id)
    await send_clean(bot, chat_id, "Select your download method:", reply_markup=kb, reply_to_message_id=msg.message_id)


# ---------------------
# Callback queries (Album / Video)
# ---------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
async def instadl_cb(bot, cq):
    choice = cq.data.split("_")[1]  # 'album' or 'video'
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice

    # delete callback message for cleanliness
    try:
        await cq.message.delete()
    except:
        pass

    if choice == "album":
        st["step"] = "await_zipname"
        # ask for zip name with ForceReply
        prompt = await send_clean(bot, chat_id, "Send the ZIP filename (include .zip) or simply send title (we'll append .zip):", reply_markup=None)
        # ForceReply to make it easier for user
        await bot.send_message(chat_id, "Reply to that message with the ZIP name.", reply_to_message_id=prompt.message_id, reply_markup=ForceReply(selective=True))
    else:
        # start video download straightaway
        st["step"] = "downloading_video"
        await handle_video_download(bot, chat_id)

# ---------------------
# Handle text reply for ZIP name
# ---------------------
@Client.on_message(filters.private & filters.user(ADMIN))
async def instadl_text_handler(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st:
        return  # ignore unrelated texts
    if st.get("step") != "await_zipname":
        return

    text = msg.text.strip()
    # ensure .zip
    if not text.lower().endswith(".zip"):
        zipname = f"{text}.zip"
    else:
        zipname = text

    st["data"]["zipname"] = zipname
    st["step"] = "downloading_album"
    # clean previous messages
    await cleanup_old(bot, chat_id)
    await handle_album_download(bot, chat_id)


# ---------------------
# Album download flow
# ---------------------
async def handle_album_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]
    shortcode = st["data"]["shortcode"]
    zipname = st["data"]["zipname"]

    # Prepare folders
    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    # cleanup old files
    for f in os.listdir(ALBUM_FOLDER):
        try: os.remove(os.path.join(ALBUM_FOLDER, f))
        except: pass

    # start message
    msg = await send_clean(bot, chat_id, "⏬ Downloading images... (0/0)")
    start_time = time.time()

    # Init instaloader
    L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False, dirname_pattern=ALBUM_FOLDER)
    load_cookies_for_instaloader(L)

    try:
        # get post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        sidecar = list(post.get_sidecar_nodes())
        total = len(sidecar)
        if total == 0:
            # maybe it's a single image (not album)
            # use the display_url
            sidecar = [post]
            total = 1
    except Exception as e:
        await msg.edit(f"Failed to fetch post: {e}")
        return

    # Download each image and update progress message
    i = 0
    for node in sidecar:
        i += 1
        # create filename
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        try:
            # instaloader's download_pic
            L.download_pic(filename, node.display_url, mtime=post.date_utc)
        except Exception as e:
            print("Error saving image:", e)
            # try direct requests as fallback
            try:
                import requests
                r = requests.get(node.display_url, timeout=30)
                with open(filename, "wb") as f:
                    f.write(r.content)
            except Exception as ee:
                print("Fallback failed:", ee)

        # update progress
        try:
            await msg.edit(f"⏬ Downloading images... ({i}/{total})")
        except:
            pass

    # now zipping
    try:
        await msg.edit(f"🗜️ Download complete ({total}/{total}). Now zipping...")
    except:
        pass

    zip_path = os.path.join(INSTA_FOLDER, zipname)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(os.listdir(ALBUM_FOLDER)):
                full = os.path.join(ALBUM_FOLDER, file)
                zf.write(full, arcname=file)
    except Exception as e:
        await msg.edit(f"Zipping error: {e}")
        return

    # Upload the ZIP with progress
    try:
        await msg.edit("🚀 Uploading ZIP...")
        c_time = time.time()
        # Use send_document with progress callback
        await bot.send_document(chat_id, zip_path, caption=zipname, progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time))
    except Exception as e:
        await msg.edit(f"Upload error: {e}")
        return
    finally:
        # cleanup server files
        try:
            for f in os.listdir(ALBUM_FOLDER):
                os.remove(os.path.join(ALBUM_FOLDER, f))
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except:
            pass

    await msg.delete()
    INSTADL_STATE.pop(chat_id, None)


# ---------------------
# Video/reel download flow
# ---------------------
async def handle_video_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    # cleanup folder
    for f in os.listdir(VIDEO_FOLDER):
        try: os.remove(os.path.join(VIDEO_FOLDER, f))
        except: pass

    # message for progress
    status_msg = await send_clean(bot, chat_id, "⏬ Preparing to download video...")

    # prepare yt-dlp options
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "cookies": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        # progress hook
    }

    # attach hook to update message
    def ytdl_hook(d):
        try:
            if d.get("status") == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded_bytes = d.get("downloaded_bytes", 0)
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                percent = 0.0
                if total_bytes:
                    percent = downloaded_bytes / total_bytes * 100
                text = f"⏬ Downloading video: {d.get('filename','')}\n{int(percent)}% • {humanbytes(downloaded_bytes)}/{humanbytes(total_bytes or 0)} • ETA {eta}s"
                # we must schedule edit in asyncio loop
                asyncio.get_event_loop().create_task(status_msg.edit(text))
            elif d.get("status") == "finished":
                asyncio.get_event_loop().create_task(status_msg.edit("Merging/processing video..."))
        except Exception as e:
            print("ytdl hook error:", e)

    ydl_opts["progress_hooks"] = [ytdl_hook]

    # run download in executor (yt_dlp is blocking)
    try:
        loop = asyncio.get_event_loop()
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        await loop.run_in_executor(None, run_ydl)
    except Exception as e:
        await status_msg.edit(f"Download failed: {e}")
        return

    # find downloaded file
    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        await status_msg.edit("Downloaded file not found.")
        return
    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    # try to get duration and filesize for caption (use moviepy if available)
    duration = None
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(file_path)
        duration = int(clip.duration)
        clip.close()
    except:
        duration = None

    filesize = humanbytes(os.path.getsize(file_path))

    # Prepare caption using CAPTION or default
    if CAPTION:
        try:
            cap = CAPTION.format(file_name=file_name, file_size=filesize, duration=duration or "Unknown")
        except Exception as e:
            cap = f"{file_name}\n\n💽 size: {filesize}\n🕒 duration: {duration or 'Unknown'} seconds"
    else:
        cap = f"{file_name}\n\n💽 size: {filesize}\n🕒 duration: {duration or 'Unknown'} seconds"

    # Upload video with progress using your progress_message helper. progress_message expects (current, total, speed??) - 
    # We will call send_video and use progress_message as callback consistent with your other scripts.
    try:
        await status_msg.edit("🚀 Uploading video...")
        c_time = time.time()
        await bot.send_video(chat_id, video=file_path, caption=cap, progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", status_msg, c_time))
    except Exception as e:
        await status_msg.edit(f"Upload failed: {e}")
        return
    finally:
        # cleanup local files
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass

    await status_msg.delete()
    INSTADL_STATE.pop(chat_id, None)

