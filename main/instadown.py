import os
import json
import time
import zipfile
import threading
import instaloader
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# ---------------------- Paths & folders ----------------------
INSTA_FOLDER = os.path.join(DOWNLOAD_LOCATION, "insta")
ALBUM_FOLDER = os.path.join(INSTA_FOLDER, "album")
VIDEO_FOLDER = os.path.join(INSTA_FOLDER, "video")
COOKIES_PATH = os.path.join(INSTA_FOLDER, "cookies.json")  # will request user to send

# ---------------------- In-memory state ----------------------
INSTADL_STATE = {}  # chat_id -> dict { step, last_msgs: [msg_id,...], data: {...} }

# ---------------------- Helper functions ----------------------
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

def load_cookies_for_instaloader(L):
    if not os.path.exists(COOKIES_PATH):
        return False
    try:
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            L.context._session.cookies.set(cookie.get("name"), cookie.get("value"))
        return True
    except Exception as e:
        print("Failed loading cookies:", e)
        return False

# ---------------------- Step 1: /instadl command ----------------------
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
    INSTADL_STATE[chat_id] = {"step": "await_cookies", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}

    await cleanup_old(bot, chat_id)
    await send_clean(bot, chat_id, "Please send your `cookies.json` file for Instagram login.", reply_to_message_id=msg.id)

# ---------------------- Step 2: Receive cookies.json ----------------------
@Client.on_message(filters.private & filters.user(ADMIN) & filters.document)
async def instadl_receive_cookies(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_cookies":
        return

    file = msg.document
    if not file.file_name.endswith(".json"):
        return await msg.reply_text("Please send a valid `cookies.json` file.")

    os.makedirs(INSTA_FOLDER, exist_ok=True)
    cookies_file_path = os.path.join(INSTA_FOLDER, "cookies.json")
    await bot.download_media(file.file_id, cookies_file_path)
    
    st["data"]["cookies"] = cookies_file_path
    st["step"] = "choose_method"
    await cleanup_old(bot, chat_id)
    await send_clean(bot, chat_id, "✅ Cookies added successfully!")

    # Show InlineKeyboard
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
         InlineKeyboardButton("🎞 Video / Reel", callback_data="insta_video")]
    ])
    await send_clean(bot, chat_id, "Select download method:", reply_markup=kb)

# ---------------------- Step 3: Handle InlineKeyboard ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
async def instadl_cb(bot, cq):
    choice = cq.data.split("_")[1]
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice

    try: await cq.message.delete()
    except: pass

    if choice == "album":
        st["step"] = "await_zipname"
        prompt = await send_clean(bot, chat_id, "Send ZIP filename (with or without `.zip`):")
        await bot.send_message(chat_id, "Reply to this message with the ZIP name.", reply_to_message_id=prompt.id, reply_markup=ForceReply(selective=True))
    else:
        st["step"] = "download_video"
        threading.Thread(target=handle_video_download, args=(bot, chat_id), daemon=True).start()

# ---------------------- Step 4: Receive ZIP name ----------------------
@Client.on_message(filters.private & filters.user(ADMIN))
async def instadl_zipname(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_zipname":
        return

    text = msg.text.strip()
    zipname = text if text.lower().endswith(".zip") else f"{text}.zip"
    st["data"]["zipname"] = zipname
    st["step"] = "download_album"
    threading.Thread(target=handle_album_download, args=(bot, chat_id), daemon=True).start()

# ---------------------- Album download ----------------------
def handle_album_download(bot, chat_id):
    import requests
    st = INSTADL_STATE[chat_id]
    shortcode = st["data"]["shortcode"]
    zipname = st["data"]["zipname"]

    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try: os.remove(os.path.join(ALBUM_FOLDER, f))
        except: pass

    msg = bot.loop.run_until_complete(send_clean(bot, chat_id, "📥 Downloading images..."))

    L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False, dirname_pattern=ALBUM_FOLDER)
    load_cookies_for_instaloader(L)

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        sidecar = list(post.get_sidecar_nodes())
        if not sidecar:
            sidecar = [post]
        total = len(sidecar)
    except Exception as e:
        bot.loop.run_until_complete(msg.edit(f"Failed to fetch post: {e}"))
        return

    for i, node in enumerate(sidecar, 1):
        filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
        try:
            L.download_pic(filename, node.display_url, mtime=post.date_utc)
        except:
            try:
                r = requests.get(node.display_url, timeout=30)
                with open(filename, "wb") as f:
                    f.write(r.content)
            except:
                pass

    bot.loop.run_until_complete(msg.edit(f"📥 Downloaded {total} Images."))

    # ZIP
    zip_path = os.path.join(INSTA_FOLDER, zipname)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(os.listdir(ALBUM_FOLDER)):
            zf.write(os.path.join(ALBUM_FOLDER, file), arcname=file)

    bot.loop.run_until_complete(msg.edit("🚀 Uploading ZIP..."))
    c_time = time.time()
    bot.loop.run_until_complete(bot.send_document(chat_id, zip_path, caption=zipname,
                                progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time)))

    # Cleanup
    for f in os.listdir(ALBUM_FOLDER):
        try: os.remove(os.path.join(ALBUM_FOLDER, f))
        except: pass
    if os.path.exists(zip_path):
        os.remove(zip_path)
    try: bot.loop.run_until_complete(msg.delete())
    except: pass
    INSTADL_STATE.pop(chat_id, None)

# ---------------------- Video download ----------------------
def handle_video_download(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try: os.remove(os.path.join(VIDEO_FOLDER, f))
        except: pass

    msg = bot.loop.run_until_complete(send_clean(bot, chat_id, "📥 Downloading Video/Reel..."))

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "cookies": COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        "quiet": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        bot.loop.run_until_complete(msg.edit("Downloaded file not found."))
        return

    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    # Get duration
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

    bot.loop.run_until_complete(msg.edit(f"📥 Downloaded: {file_name}"))
    bot.loop.run_until_complete(msg.edit("🚀 Uploading Video..."))
    c_time = time.time()
    bot.loop.run_until_complete(bot.send_video(chat_id, video=file_path, caption=cap,
                                progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time)))

    try: os.remove(file_path)
    except: pass
    try: bot.loop.run_until_complete(msg.delete())
    except: pass
    INSTADL_STATE.pop(chat_id, None)
