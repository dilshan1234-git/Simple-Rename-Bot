import os, time, asyncio, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes
from moviepy.editor import VideoFileClip

# Temporary store
merge_data = {}

@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def ask_for_subtitle(bot, msg):
    reply = msg.reply_to_message
    if not reply or not (reply.video or reply.document or reply.audio):
        return await msg.reply_text("❌ Please reply to a video/file with `/merge`.")

    media = reply.video or reply.document or reply.audio
    file_size = humanbytes(media.file_size)
    sts = await msg.reply_text("⏳ Fetching file info...")

    # Download original file
    file_path = await reply.download(file_name=os.path.join(DOWNLOAD_LOCATION, media.file_name))

    # Try to get duration if it's a video/audio
    duration = 0
    if reply.video or reply.audio:
        try:
            clip = VideoFileClip(file_path)
            duration = int(clip.duration)
            clip.close()
        except:
            duration = 0

    merge_data[msg.from_user.id] = {
        "media_msg": reply,
        "file_name": media.file_name,
        "file_size": file_size,
        "duration": duration,
        "file_path": file_path,
        "subtitle_file": None
    }

    await sts.delete()
    text = (
        f"📂 **File Selected:** `{media.file_name}`\n"
        f"💽 **Size:** {file_size}\n"
        f"🕒 **Duration:** {duration} sec\n\n"
        f"📥 Now send me your subtitle file (any format/extension)"
    )
    await msg.reply_text(text)


@Client.on_message(filters.private & filters.document & filters.user(ADMIN))
async def get_subtitle(bot, msg):
    user_id = msg.from_user.id
    if user_id not in merge_data:
        return

    subtitle = msg.document
    sub_path = os.path.join(DOWNLOAD_LOCATION, subtitle.file_name)
    await msg.download(file_name=sub_path)

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

    sts = await query.message.edit(f"📥 Download complete!\n⚙️ Now merging `{os.path.basename(subtitle_file)}` ...")
    c_time = time.time()

    # Merge with ffmpeg (soft-sub)
    cmd = [
        "ffmpeg", "-y", "-i", input_file, "-i", subtitle_file,
        "-c", "copy", "-c:s", "mov_text",
        "-map", "0", "-map", "1", output_path
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    await process.communicate()

    await sts.edit("✅ Processing done!\n🚀 Now uploading...")

    try:
        await bot.send_video(
            chat_id=query.message.chat.id,
            video=output_path,
            caption="✅ Processed File (with subtitles)",
            duration=data["duration"],
            progress=progress_message,
            progress_args=("Uploading...", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Upload failed: {e}")

    await sts.delete()
    # keep files on Colab
