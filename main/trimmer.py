# main/trimmer.py
import os
import time
import subprocess
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, ADMIN, VID_TRIMMER_URL
from main.utils import progress_message, humanbytes
from main.downloader.ytdl_text import VID_TRIMMER_TEXT

# In-memory store for per-chat trimming state
trim_data = {}

# ⏰ Convert HH:MM:SS → seconds
def hms_to_seconds(hms: str):
    parts = hms.strip().split(":")
    parts = [int(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s

# ⏳ Convert seconds → HH:MM:SS
def seconds_to_hms(s: int):
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


# 🎬 Trim command
@Client.on_message(filters.private & filters.command("trim") & filters.user(ADMIN))
async def start_trim_process(bot, msg):
    chat_id = msg.chat.id
    trim_data[chat_id] = {}
    await bot.send_photo(
        chat_id=chat_id,
        photo=VID_TRIMMER_URL,
        caption=VID_TRIMMER_TEXT,
        parse_mode=enums.ParseMode.MARKDOWN
    )


# 📥 Receive video/document
@Client.on_message(filters.private & (filters.video | filters.document) & filters.user(ADMIN))
async def trim_receive_media(bot, msg):
    chat_id = msg.chat.id
    if chat_id not in trim_data:
        return

    media = msg.document or msg.video
    orig_name = getattr(media, "file_name", None) or f"file_{msg.id}.mp4"

    trim_data[chat_id]["media_msg"] = msg
    trim_data[chat_id]["orig_name"] = orig_name

    await bot.send_message(
        chat_id,
        f"📝 Please send start & end times for trimming ⏳\n\n"
        f"➡️ Format: `HH:MM:SS HH:MM:SS`\n📂 File: `{orig_name}`",
        parse_mode=enums.ParseMode.MARKDOWN
    )


# ⌛ Receive start & end times
@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def trim_receive_times(bot, msg):
    chat_id = msg.chat.id
    if chat_id not in trim_data:
        return

    try:
        start_txt, end_txt = msg.text.strip().split()
        start_s = hms_to_seconds(start_txt)
        end_s = hms_to_seconds(end_txt)
    except Exception:
        return await msg.reply_text("❌ Invalid format!\nUse: `HH:MM:SS HH:MM:SS`", parse_mode=enums.ParseMode.MARKDOWN)

    if end_s <= start_s:
        return await msg.reply_text("⚠️ End time must be greater than start time!")

    trim_data[chat_id].update({
        "start_s": start_s,
        "end_s": end_s,
        "start_hms": seconds_to_hms(start_s),
        "end_hms": seconds_to_hms(end_s)
    })

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"trim_confirm:{chat_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"trim_cancel:{chat_id}")
    ]])

    await bot.send_message(
        chat_id,
        f"✂️ Ready to trim `{trim_data[chat_id]['orig_name']}`\n"
        f"▶️ Start: `{trim_data[chat_id]['start_hms']}`\n"
        f"⏹ End: `{trim_data[chat_id]['end_hms']}`\n\n"
        f"👉 Confirm to start trimming!",
        reply_markup=kb,
        parse_mode=enums.ParseMode.MARKDOWN
    )


# ❌ Cancel trim
@Client.on_callback_query(filters.regex(r"^trim_cancel:") & filters.user(ADMIN))
async def trim_cancel(bot, cb):
    chat_id = int(cb.data.split(":")[1])
    trim_data.pop(chat_id, None)
    await cb.answer("❌ Trim cancelled.")
    await cb.message.edit_text("🚫 Trim cancelled.")


# ✅ Confirm trim → download → trim → upload
@Client.on_callback_query(filters.regex(r"^trim_confirm:") & filters.user(ADMIN))
async def trim_confirm(bot, cb):
    chat_id = int(cb.data.split(":")[1])
    state = trim_data.get(chat_id)
    if not state:
        return await cb.answer("⚠️ Session expired!", show_alert=True)

    media_msg = state["media_msg"]
    orig_name = state["orig_name"]
    start_s, end_s = state["start_s"], state["end_s"]
    duration = end_s - start_s
    start_hms, end_hms = state["start_hms"], state["end_hms"]

    sts = await cb.message.edit_text("📥 Downloading your file...")
    download_path = os.path.join(DOWNLOAD_LOCATION, f"trim_{chat_id}_{int(time.time())}{os.path.splitext(orig_name)[1]}")

    c_time = time.time()
    try:
        downloaded = await media_msg.download(
            file_name=download_path,
            progress=progress_message,
            progress_args=(f"⬇️ Downloading...\n📂 {orig_name}", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Download failed: {e}")

    # 🔹 Extract real thumbnail from downloaded video using ffmpeg
    thumb_path = os.path.join(DOWNLOAD_LOCATION, f"thumb_{chat_id}.jpg")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", downloaded, "-ss", "00:00:01", "-vframes", "1", thumb_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        thumb_path = None

    # Paths
    name_root, ext = os.path.splitext(orig_name)
    out_path = os.path.join(DOWNLOAD_LOCATION, f"{name_root}_trimmed{ext}")

    # 🎬 Fast trim
    await sts.edit("✂️ Trimming video (fast mode)...")
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s), "-i", downloaded,
        "-t", str(duration),
        "-c", "copy",
        out_path
    ]
    success = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    # fallback re-encode
    if not success or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        await sts.edit("⚠️ Fast trim failed. Retrying with re-encode...")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s), "-i", downloaded,
            "-t", str(duration),
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k",
            out_path
        ]
        success = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    if not success:
        return await sts.edit("❌ Trimming failed!")

    # 📤 Upload
    caption = f"🎬 **{os.path.basename(out_path)}**\n🕒 Trimmed: `{start_hms}` ➡️ `{end_hms}`"
    await sts.edit("📤 Uploading trimmed file...")
    c_time = time.time()
    try:
        await bot.send_video(
            chat_id,
            video=out_path,
            caption=caption,
            duration=duration,
            thumb=thumb_path if os.path.exists(thumb_path) else None,
            progress=progress_message,
            progress_args=(f"⬆️ Uploading...\n📂 {os.path.basename(out_path)}", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Upload failed: {e}")

    # Cleanup
    for f in [downloaded, out_path, thumb_path]:
        try:
            if f and os.path.exists(f):
                os.remove(f)
        except:
            pass

    await sts.delete()
    trim_data.pop(chat_id, None)
