import os, time, asyncio, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Temporary storage
merge_data = {}

@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def merge_start(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("⚠️ Please reply to a video/document to merge subtitles.")

    media = reply.video or reply.document
    if not media:
        return await msg.reply_text("⚠️ This file type is not supported.")

    # Save video info in memory
    merge_data[msg.chat.id] = {"video_msg": reply, "subtitle_msg": None}

    filename = media.file_name or "unnamed"
    filesize = humanbytes(media.file_size)
    duration = getattr(media, "duration", None)
    dur_text = f"\n🕒 Duration: {duration} sec" if duration else ""

    await msg.reply_text(
        f"🎬 **Video Selected**\n\n"
        f"📂 File: `{filename}`\n"
        f"💾 Size: `{filesize}`{dur_text}\n\n"
        f"📑 Now send me your subtitle file...",
        quote=True
    )


@Client.on_message(filters.private & filters.user(ADMIN))
async def subtitle_receive(bot, msg):
    chat_id = msg.chat.id
    if chat_id not in merge_data or merge_data[chat_id].get("subtitle_msg"):
        return

    if not msg.document:
        return await msg.reply_text("⚠️ Please send a subtitle file (e.g. .srt, .ass, .vtt).")

    merge_data[chat_id]["subtitle_msg"] = msg

    video = merge_data[chat_id]["video_msg"]
    sub = msg.document

    await msg.reply_text(
        f"✅ **Files Ready**\n\n"
        f"🎬 Video: `{video.video.file_name if video.video else video.document.file_name}`\n"
        f"📑 Subtitle: `{sub.file_name}`\n\n"
        f"Do you want to merge them?",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Confirm", callback_data="merge_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="merge_cancel")
            ]]
        )
    )


@Client.on_callback_query(filters.regex("merge_confirm"))
async def merge_confirm(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    data = merge_data.get(chat_id)

    if not data:
        return await query.message.edit("⚠️ Session expired. Please start again.")

    video_msg = data["video_msg"]
    sub_msg = data["subtitle_msg"]

    sts = await query.message.edit("⏳ Downloading files...")

    c_time = time.time()
    video_path = await video_msg.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, video_msg.document.file_name if video_msg.document else video_msg.video.file_name),
        progress=progress_message,
        progress_args=("Downloading video...", sts, c_time)
    )
    subtitle_path = await sub_msg.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, sub_msg.document.file_name),
        progress=progress_message,
        progress_args=("Downloading subtitle...", sts, c_time)
    )

    await sts.edit("✅ Download complete!\n⚒️ Now processing...")

    # Create output file path
    base, ext = os.path.splitext(video_path)
    output_path = base + "_merged" + ext

    # Merge with ffmpeg (soft subtitle, selectable in players)
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", subtitle_path,
        "-c", "copy", "-c:s", "mov_text",  # mov_text works for mp4, mkv will store normally
        output_path
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()

    await sts.edit("🚀 Uploading processed file...")

    c_time = time.time()
    try:
        await bot.send_document(
            chat_id,
            document=output_path,
            caption="✅ Processed File",
            progress=progress_message,
            progress_args=("Uploading...", sts, c_time)
        )
    except Exception as e:
        await sts.edit(f"❌ Upload failed: {e}")
        return

    await sts.delete()
    # ⚠️ Do not delete output file (as you said keep it in Colab)


@Client.on_callback_query(filters.regex("merge_cancel"))
async def merge_cancel(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    merge_data.pop(chat_id, None)
    await query.message.edit("❌ Merge cancelled.")
