import os
import json
import time
import zipfile
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
COOKIES_PATH = os.path.join(INSTA_FOLDER, "cookies.json")

# ----------------------
# In-memory state
# ----------------------
INSTADL_STATE = {}  # chat_id -> { step, last_msgs:[], data:{} }

# ----------------------
# Helper functions
# ----------------------
def cleanup_messages(bot, chat_id):
    st = INSTADL_STATE.get(chat_id)
    if not st:
        return
    for mid in st.get("last_msgs", []):
        try:
            bot.delete_messages(chat_id, mid)
        except:
            pass
    st["last_msgs"] = []

def send_clean(bot, chat_id, text, reply_markup=None, reply_to=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup, reply_to_message_id=reply_to)
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["last_msgs"].append(msg.id)
    if len(st["last_msgs"]) > 8:
        st["last_msgs"].pop(0)
    return msg

def extract_shortcode(url):
    try:
        parts = url.split("/")
        for i, p in enumerate(parts):
            if p in ("p", "reel", "tv") and i + 1 < len(parts):
                return parts[i+1].split("?")[0]
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
def instadl_start(bot, msg):
    replied = msg.reply_to_message
    if not replied or not replied.text:
        return msg.reply_text("Reply to an Instagram post URL with /instadl.")

    url = replied.text.strip().split()[0]
    shortcode = extract_shortcode(url)
    if not shortcode:
        return msg.reply_text("Couldn't parse shortcode. Use a valid Instagram URL.")

    chat_id = msg.chat.id
    INSTADL_STATE[chat_id] = {"step": "await_cookies", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}

    cleanup_messages(bot, chat_id)
    send_clean(bot, chat_id, "Please send your `cookies.json` file for Instagram login.")

# ----------------------
# Cookies upload
# ----------------------
@Client.on_message(filters.private & filters.user(ADMIN) & filters.document)
def cookies_upload(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_cookies":
        return

    if not msg.document.file_name.endswith(".json"):
        return send_clean(bot, chat_id, "Please send a valid JSON file.")

    os.makedirs(INSTA_FOLDER, exist_ok=True)
    file_path = COOKIES_PATH
    msg.download(file_path)

    st["data"]["cookies"] = file_path
    st["step"] = "choose_method"

    cleanup_messages(bot, chat_id)
    send_clean(bot, chat_id, "✅ Cookies added successfully!")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
         InlineKeyboardButton("🎞 Video/Reel", callback_data="insta_video")]
    ])
    send_clean(bot, chat_id, "Select download method:", reply_markup=kb)

# ----------------------
# Inline callback
# ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
def choose_method(bot, cq):
    choice = cq.data.split("_")[1]
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice
    try:
        cq.message.delete()
    except: pass

    if choice == "album":
        st["step"] = "await_zipname"
        prompt = send_clean(bot, chat_id, "Send ZIP filename (with or without .zip):")
        bot.send_message(chat_id, "Reply to that message with the ZIP name.", reply_to_message_id=prompt.id, reply_markup=ForceReply(selective=True))
    else:
        st["step"] = "downloading_video"
        download_video(bot, chat_id)

# ----------------------
# ZIP name handler
# ----------------------
@Client.on_message(filters.private & filters.user(ADMIN))
def zip_name_handler(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_zipname":
        return

    text = msg.text.strip()
    zipname = text if text.lower().endswith(".zip") else f"{text}.zip"
    st["data"]["zipname"] = zipname
    st["step"] = "downloading_album"

    cleanup_messages(bot, chat_id)
    download_album(bot, chat_id)

# ----------------------
# Download album
# ----------------------
def download_album(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    shortcode = st["data"]["shortcode"]
    zipname = st["data"]["zipname"]
    cookies_file = st["data"].get("cookies")

    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try: os.remove(os.path.join(ALBUM_FOLDER, f))
        except: pass

    msg = send_clean(bot, chat_id, "📥 Downloading images...")

    # Instaloader
    L = instaloader.Instaloader(download_videos=False, download_video_thumbnails=False, dirname_pattern=ALBUM_FOLDER)
    # Load cookies
    if cookies_file and os.path.exists(cookies_file):
        with open(cookies_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            L.context._session.cookies.set(cookie.get("name"), cookie.get("value"))

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        sidecar = list(post.get_sidecar_nodes())
        if not sidecar:
            sidecar = [post]
        total = len(sidecar)
        for i, node in enumerate(sidecar, 1):
            filename = os.path.join(ALBUM_FOLDER, f"image_{i}.jpg")
            try:
                L.download_pic(filename, node.display_url, mtime=post.date_utc)
            except:
                import requests
                r = requests.get(node.display_url)
                with open(filename, "wb") as f:
                    f.write(r.content)
    except Exception as e:
        send_clean(bot, chat_id, f"Failed to fetch post: {e}")
        return

    bot.edit_message_text(chat_id, msg.id, f"📥 Downloading images... ({total} Images)")

    # ZIP and upload
    zip_path = os.path.join(INSTA_FOLDER, zipname)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(ALBUM_FOLDER)):
            zf.write(os.path.join(ALBUM_FOLDER, f), arcname=f)

    c_time = time.time()
    bot.send_document(chat_id, zip_path, caption=zipname,
                      progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time))

    # Cleanup
    for f in os.listdir(ALBUM_FOLDER):
        os.remove(os.path.join(ALBUM_FOLDER, f))
    if os.path.exists(zip_path):
        os.remove(zip_path)
    try: bot.delete_messages(chat_id, msg.id)
    except: pass
    INSTADL_STATE.pop(chat_id, None)

# ----------------------
# Download video/reel
# ----------------------
def download_video(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]
    cookies_file = st["data"].get("cookies")

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try: os.remove(os.path.join(VIDEO_FOLDER, f))
        except: pass

    msg = send_clean(bot, chat_id, "📥 Downloading Video/Reel...")

    outtmpl = os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": outtmpl,
    }
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookies"] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        bot.edit_message_text(chat_id, msg.id, "Downloaded file not found.")
        return

    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    bot.edit_message_text(chat_id, msg.id, f"📥 Downloading Video/Reel: {file_name}")

    # Generate caption
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

    c_time = time.time()
    bot.send_video(chat_id, file_path, caption=cap, progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time))

    # Cleanup
    try:
        os.remove(file_path)
        bot.delete_messages(chat_id, msg.id)
    except: pass
    INSTADL_STATE.pop(chat_id, None)
