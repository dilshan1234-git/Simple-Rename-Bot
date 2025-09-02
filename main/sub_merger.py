import os, time, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

merge_data = {}  # Store session data


# ───────────────────────────────
# STEP 1: Handle /merge command
# ───────────────────────────────
@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def ask_for_subtitle(bot, msg):
    reply = msg.reply_to_message
    if not reply or not (reply.video or reply.document or reply.audio):
        return await msg.reply_text("❌ Please reply to a file (video/audio/document) with `/merge`.")

    media = reply.video or reply.document or reply.audio
    file_size = humanbytes(media.file_size)

    sts = await msg.reply_text("⏳ Fetching file info...")

    # Download the main file
    try:
        file_path = await reply.download(file_name=os.path.join(DOWNLOAD_LOCATION, media.file_name))
    except Exception as e:
        return await sts.edit(f"❌ Download failed: {e}")

    duration = 0
    if reply.video or reply.audio:
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.stdout.strip():
                duration = int(float(result.stdout.strip()))
        except Exception as e:
            print("FFPROBE ERROR:", e)
            duration = 0

    # Save session
    merge_data[msg.from_user.id] = {
        "media_msg": reply,
        "file_name": media.file_name,
        "file_size": file_size,
        "duration": duration,
        "file_path": file_path,
        "subtitle_file": None
    }

    await sts.edit(
        f"📂 **File Selected:** `{media.file_name}`\n"
        f"💽 **Size:** {file_size}\n"
        f"🕒 **Duration:** {duration} sec\n\n"
        f"📥 Now send me your subtitle file (any format/extension)"
    )


# ───────────────────────────────
# STEP 2: Get subtitle file
# ───────────────────────────────
@Client.on_message(filters.private & filters.document & filters.user(ADMIN))
async def get_subtitle(bot, msg):
    user_id = msg.from_user.id
    if user_id not in merge_data:
        return  # ignore stray files

    subtitle = msg.document
    sub_path = os.path.join(DOWNLOAD_LOCATION, subtitle.file_name)
    try:
        await msg.download(file_name=sub_path)
    except Exception as e:
        return await msg.reply_text(f"❌ Subtitle download failed: {e}")

    merge_data[user_id]["subtitle_file"] = sub_path

    main_file = merge_data[user_id]["file_name"]
    file_size = merge_data[user_id]["file_size"]
    duration = merge_data[user_id]["duration"]

    text = (
        f"📂 **Main File:** `{main_file}`\n"
        f"💽 **Size:** {file_size}\n"
        f"🕒 **Duration:** {duration} sec\n\n"
        f"📄 **Subtitle/File:** `{subtitle.file_name}`\n\n"
        "✅ Do you want to merge this into the file?"
    )

    buttons = [
        [InlineKeyboardButton("✅ Confirm", callback_data=f"merge_confirm_{user_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"merge_cancel_{user_id}")]
    ]

    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ───────────────────────────────
# STEP 3: Handle Confirm / Cancel
# ───────────────────────────────
@Client.on_callback_query(filters.regex(r"merge_(confirm|cancel)_(\d+)"))
async def merge_process(bot, query: CallbackQuery):
    action, user_id = query.data.split("_")[1], int(query.data.split("_")[2])

    if query.from_user.id != user_id:
        return await query.answer("Not your request.", show_alert=True)

    if action == "cancel":
        merge_data.pop(user_id, None)
        await query.message.delete()
        return await query.message.reply_text("❌ Merge cancelled.")

    data = merge_data.get(user_id)
    if not data:
        return await query.message.edit("❌ Data expired, start again with /merge.")

    input_file = data["file_path"]
    subtitle_file = data["subtitle_file"]
    output_path = os.path.join(DOWNLOAD_LOCATION, f"processed_{data['file_name']}")

    sts = await query.message.edit(
        f"📥 Download complete!\n⚙️ Now merging `{os.path.basename(subtitle_file)}` ..."
    )
    c_time = time.time()

    # ffmpeg merge (soft-sub)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_file, "-i", subtitle_file,
            "-c", "copy", "-c:s", "mov_text",
            "-map", "0", "-map", "1", output_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print("FFMPEG ERROR:", result.stderr)
            return await sts.edit("❌ Failed during merging.")
    except Exception as e:
        return await sts.edit(f"❌ Merge failed: {e}")

    await sts.edit("✅ Processing done!\n🚀 Now uploading...")

    try:
        if data["media_msg"].video:  # send as video
            await bot.send_video(
                chat_id=query.message.chat.id,
                video=output_path,
                caption="✅ Processed File (with subtitles)",
                duration=data["duration"],
                progress=progress_message,
                progress_args=("Uploading...", sts, c_time)
            )
        else:  # send as document
            await bot.send_document(
                chat_id=query.message.chat.id,
                document=output_path,
                caption="✅ Processed File (with subtitles/extra track)",
                progress=progress_message,
                progress_args=("Uploading...", sts, c_time)
            )
    except Exception as e:
        return await sts.edit(f"❌ Upload failed: {e}")

    await sts.delete()
    # ⚠️ Files are not deleted (Colab keeps them)
