import os
import json
import time
import zipfile
import subprocess
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
INSTADL_STATE = {}  # chat_id -> dict { step, last_msgs: [msg_id,...], data: {...} }

# ----------------------
# Helper functions
# ----------------------
def send_clean_sync(bot, chat_id, text):
    """Send message synchronously (blocking is minimal)."""
    msg = bot.send_message(chat_id, text)
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["last_msgs"].append(msg.id)
    if len(st["last_msgs"]) > 8:
        st["last_msgs"].pop(0)
    return msg

def cleanup_old_sync(bot, chat_id):
    st = INSTADL_STATE.get(chat_id)
    if not st:
        return
    for mid in st.get("last_msgs", []):
        try:
            bot.delete_messages(chat_id, mid)
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
    INSTADL_STATE[chat_id] = {"step": "choose", "last_msgs": [], "data": {"url": url, "shortcode": shortcode}}

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🖼 Album (images)", callback_data="insta_album"),
             InlineKeyboardButton("🎞 Video / Reel", callback_data="insta_video")]
        ]
    )
    cleanup_old_sync(bot, chat_id)
    send_clean_sync(bot, chat_id, "Select your download method:").edit_reply_markup(kb)

# ----------------------
# Callback handler
# ----------------------
@Client.on_callback_query(filters.user(ADMIN) & filters.regex(r"^insta_(album|video)$"))
def instadl_cb(bot, cq):
    choice = cq.data.split("_")[1]
    chat_id = cq.message.chat.id
    st = INSTADL_STATE.setdefault(chat_id, {"last_msgs": [], "data": {}, "step": None})
    st["data"]["choice"] = choice

    try:
        cq.message.delete()
    except:
        pass

    if choice == "album":
        st["step"] = "await_zipname"
        prompt = send_clean_sync(bot, chat_id, "Send ZIP filename (with .zip or without, we'll append):")
        bot.send_message(chat_id, "Reply to that message with the ZIP name.", reply_to_message_id=prompt.id, reply_markup=ForceReply(selective=True))
    else:
        st["step"] = "downloading_video"
        download_video_process(bot, chat_id)

# ----------------------
# Text reply handler for ZIP
# ----------------------
@Client.on_message(filters.private & filters.user(ADMIN))
def instadl_text_handler(bot, msg):
    chat_id = msg.chat.id
    st = INSTADL_STATE.get(chat_id)
    if not st or st.get("step") != "await_zipname":
        return

    text = msg.text.strip()
    zipname = text if text.lower().endswith(".zip") else f"{text}.zip"
    st["data"]["zipname"] = zipname
    st["step"] = "downloading_album"
    cleanup_old_sync(bot, chat_id)
    download_album_process(bot, chat_id)

# ----------------------
# Album download subprocess
# ----------------------
def download_album_process(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    shortcode = st["data"]["shortcode"]
    zipname = st["data"]["zipname"]

    os.makedirs(ALBUM_FOLDER, exist_ok=True)
    for f in os.listdir(ALBUM_FOLDER):
        try:
            os.remove(os.path.join(ALBUM_FOLDER, f))
        except:
            pass

    msg = send_clean_sync(bot, chat_id, "📥 Downloading images...")

    # Run instaloader in subprocess
    command = [
        "python3", "-u", "-m", "instaloader",
        "--dirname-pattern", ALBUM_FOLDER,
        "--no-videos",
        "--no-video-thumbnails",
        shortcode
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Count images
    count = len([f for f in os.listdir(ALBUM_FOLDER) if f.endswith(".jpg")])
    bot.edit_message_text(chat_id, msg.id, f"📥 Downloading images... ({count} Images)")

    # Zip files
    zip_path = os.path.join(INSTA_FOLDER, zipname)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(os.listdir(ALBUM_FOLDER)):
            zf.write(os.path.join(ALBUM_FOLDER, file), arcname=file)

    # Upload ZIP
    c_time = time.time()
    bot.send_document(chat_id, zip_path, caption=zipname, progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time))

    # Cleanup
    for f in os.listdir(ALBUM_FOLDER):
        os.remove(os.path.join(ALBUM_FOLDER, f))
    os.remove(zip_path)
    try:
        bot.delete_messages(chat_id, msg.id)
    except: pass
    INSTADL_STATE.pop(chat_id, None)

# ----------------------
# Video/Reel download subprocess
# ----------------------
def download_video_process(bot, chat_id):
    st = INSTADL_STATE[chat_id]
    url = st["data"]["url"]

    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    for f in os.listdir(VIDEO_FOLDER):
        try:
            os.remove(os.path.join(VIDEO_FOLDER, f))
        except:
            pass

    msg = send_clean_sync(bot, chat_id, "📥 Downloading Video/Reel...")

    # yt-dlp command
    outtmpl = os.path.join(VIDEO_FOLDER, "%(title)s.%(ext)s")
    command = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "-o", outtmpl,
        url
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Find downloaded file
    files = [f for f in os.listdir(VIDEO_FOLDER) if not f.startswith(".")]
    if not files:
        bot.edit_message_text(chat_id, msg.id, "Downloaded file not found.")
        return
    file_path = os.path.join(VIDEO_FOLDER, files[0])
    file_name = files[0]

    bot.edit_message_text(chat_id, msg.id, f"📥 Downloading Video/Reel: {file_name}")

    # Upload video
    filesize = humanbytes(os.path.getsize(file_path))
    cap = f"{file_name}\n💽 Size: {filesize}"
    c_time = time.time()
    bot.send_video(chat_id, file_path, caption=cap, progress=progress_message, progress_args=("Upload Started..... Thanks To All Who Supported ❤", msg, c_time))

    # Cleanup
    try:
        os.remove(file_path)
        bot.delete_messages(chat_id, msg.id)
    except:
        pass
    INSTADL_STATE.pop(chat_id, None)
