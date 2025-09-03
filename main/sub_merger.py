import os, time, asyncio, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes
from pyrogram.filters import create

# ─────────────────────────
# Session store (per chat)
# ─────────────────────────
MERGE_STATE = {}  # { chat_id: { "media_msg": Message, "stage": "await_sub", "subtitle_msg": Message | None } }

os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)

# Custom filter: only accept a subtitle document while we are waiting for it
def _awaiting_subtitle(_, __, msg):
    try:
        return (
            msg.chat
            and msg.chat.id in MERGE_STATE
            and MERGE_STATE[msg.chat.id].get("stage") == "await_sub"
            and msg.document is not None
        )
    except Exception:
        return False

awaiting_subtitle = create(_awaiting_subtitle)


# ─────────────────────────
# Step 1: /merge (must reply to a video or document)
# ─────────────────────────
@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def merge_start(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("⚠️ Please *reply* to a **video or document** with `/merge`.")

    media = reply.video or reply.document
    if not media:
        return await msg.reply_text("⚠️ Unsupported message. Reply to a **video/document** and use `/merge`.")

    MERGE_STATE[msg.chat.id] = {"media_msg": reply, "stage": "await_sub", "subtitle_msg": None}

    filename = media.file_name or "unnamed"
    filesize = humanbytes(media.file_size)
    dur = getattr(media, "duration", None)
    dur_text = f"\n🕒 Duration: `{dur} sec`" if dur else ""

    await msg.reply_text(
        f"🎬 **File Selected**\n\n"
        f"📂 File: `{filename}`\n"
        f"💾 Size: `{filesize}`{dur_text}\n\n"
        f"📑 Now send your **subtitle file** here (e.g. `.srt`, `.ass`, `.vtt`).",
        quote=True,
        disable_web_page_preview=True
    )


# ─────────────────────────
# Step 2: receive subtitle (only when session active)
# ─────────────────────────
@Client.on_message(filters.private & awaiting_subtitle & filters.user(ADMIN))
async def subtitle_receive(bot, msg):
    chat_id = msg.chat.id
    sub = msg.document
    if not sub:
        return

    MERGE_STATE[chat_id]["subtitle_msg"] = msg

    media_msg = MERGE_STATE[chat_id]["media_msg"]
    video_name = media_msg.video.file_name if media_msg.video else media_msg.document.file_name

    await msg.reply_text(
        f"✅ **Files Ready**\n\n"
        f"🎬 Main: `{video_name}`\n"
        f"📄 Subtitle: `{sub.file_name}`\n\n"
        f"Proceed to merge?",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Confirm", callback_data=f"sm_confirm:{chat_id}"),
                InlineKeyboardButton("❌ Cancel",  callback_data=f"sm_cancel:{chat_id}")
            ]]
        )
    )


# ─────────────────────────
# Step 3: callbacks (unique sm_ prefix)
# ─────────────────────────
@Client.on_callback_query(filters.regex(r"^sm_(confirm|cancel):(-?\d+)$") & filters.user(ADMIN))
async def merge_cb(bot, query: CallbackQuery):
    action, chat_id_str = query.data.split(":")
    chat_id = int(chat_id_str)

    if query.message.chat.id != chat_id or chat_id not in MERGE_STATE:
        return await query.answer("Session not found / expired.", show_alert=True)

    if action == "sm_cancel":
        MERGE_STATE.pop(chat_id, None)
        await query.message.edit("❌ Merge cancelled.")
        return

    # sm_confirm
    data = MERGE_STATE[chat_id]
    media_msg = data["media_msg"]
    sub_msg = data["subtitle_msg"]
    if not sub_msg:
        return await query.message.edit("⚠️ No subtitle attached. Send a subtitle file first.")

    await query.message.edit("⏳ Downloading files...")

    # Download main file
    c_time = time.time()
    main_name = media_msg.video.file_name if media_msg.video else media_msg.document.file_name
    main_path = await media_msg.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, main_name),
        progress=progress_message,
        progress_args=("📥 Downloading main file...", query.message, c_time)
    )

    # Download subtitle
    sub_name = sub_msg.document.file_name
    sub_path = await sub_msg.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, sub_name),
        progress=progress_message,
        progress_args=("📥 Downloading subtitle...", query.message, c_time)
    )

    await query.message.edit("✅ Downloaded.\n⚙️ Processing...")

    base, ext = os.path.splitext(main_path)
    output_path = f"{base}_merged{ext}"

    container = ext.lower()
    sub_ext = os.path.splitext(sub_path)[1].lower()

    if container == ".mp4":
        sub_codec = "mov_text"
    else:
        sub_codec = "srt" if sub_ext in [".srt", ".vtt"] else "ass"

    # ffmpeg command → keep all streams from main file, add new subtitle
    cmd = [
        "ffmpeg", "-y",
        "-i", main_path, "-i", sub_path,
        "-map", "0",           # keep everything from main (video, audio, old subs)
        "-map", "1:0",         # add only the new subtitle
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", sub_codec,
        "-disposition:s:0", "default",
        output_path
    ]

    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        short_err = err.decode(errors="ignore").splitlines()[-10:]
        return await query.message.edit("❌ Failed during merging.\n" + "```\n" + "\n".join(short_err) + "\n```")

    # Generate thumbnail
    thumb_path = f"{base}_thumb.jpg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", output_path, "-ss", "00:00:02", "-vframes", "1", thumb_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if not os.path.exists(thumb_path):
            thumb_path = None
    except Exception:
        thumb_path = None

    await query.message.edit("✅ Processed.\n📤 Uploading...")

    c_time = time.time()
    try:
        await bot.send_video(
            chat_id,
            video=output_path,
            caption=os.path.basename(output_path),  # only filename
            thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
            progress=progress_message,
            progress_args=("Uploading...", query.message, c_time)
        )
    except Exception as e:
        return await query.message.edit(f"❌ Upload failed: `{e}`")

    # Keep processed video in Colab, but cleanup temp subtitle & thumbnail & main
    try:
        if os.path.exists(sub_path):
            os.remove(sub_path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        if os.path.exists(main_path):
            os.remove(main_path)
    except:
        pass

    await query.message.delete()
    MERGE_STATE.pop(chat_id, None)
