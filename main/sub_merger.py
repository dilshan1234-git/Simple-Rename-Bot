import os, time, asyncio, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes
from moviepy.editor import VideoFileClip

# Temporary storage
merge_data = {}

@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def ask_for_subtitle(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.video:
        return await msg.reply_text("❌ Please reply to a video file with `/merge` to continue.")

    video = reply.video
    file_size = humanbytes(video.file_size)

    # Get duration
    sts = await msg.reply_text("⏳ Fetching video info...")
    video_clip = VideoFileClip(await reply.download(file_name=os.path.join(DOWNLOAD_LOCATION, video.file_name)))
    duration = int(video_clip.duration)
    video_clip.close()

    merge_data[msg.from_user.id] = {
        "video_msg": reply,
        "video_file": video.file_name,
        "video_size": file_size,
        "duration": duration,
        "video_path": os.path.join(DOWNLOAD_LOCATION, video.file_name),
        "subtitle_file": None
    }

    await sts.delete()
    text = (
        f"🎬 **Video Selected:** `{video.file_name}`\n"
        f"💽 **Size:** {file_size}\n"
        f"🕒 **Duration:** {duration} sec\n\n"
        f"📥 Now send me your subtitle file (e.g. `.srt`, `.ass`, `.vtt`)"
    )
    await msg.reply_text(text)


@Client.on_message(filters.private & filters.document & filters.user(ADMIN))
async def get_subtitle(bot, msg):
    user_id = msg.from_user.id
    if user_id not in merge_data:
        return  # ignore if no /merge before

    subtitle = msg.document
    sub_ext = os.path.splitext(subtitle.file_name)[1].lower()
    if sub_ext not in [".srt", ".ass", ".vtt"]:
        return await msg.reply_text("❌ Unsupported subtitle format. Use `.srt`, `.ass`, or `.vtt`.")

    # Download subtitle
    sub_path = os.path.join(DOWNLOAD_LOCATION, subtitle.file_name)
    await msg.download(file_name=sub_path)

    merge_data[user_id]["subtitle_file"] = sub_path

    video_name = merge_data[user_id]["video_file"]
    file_size = merge_data[user_id]["video_size"]
    duration = merge_data[user_id]["duration"]

    text = (
        f"🎬 **Video:** `{video_name}`\n"
        f"💽 **Size:** {file_size}\n"
        f"🕒 **Duration:** {duration} sec\n\n"
        f"📄 **Subtitle:** `{subtitle.file_name}`\n\n"
        "✅ Do you want to merge this subtitle into the video?"
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
        return await query.message.reply_text("❌ Merge process cancelled.")

    data = merge_data.get(user_id)
    if not data:
        return await query.message.edit("❌ Data expired, start again with /merge.")

    video_path = data["video_path"]
    subtitle_path = data["subtitle_file"]
    output_path = os.path.join(DOWNLOAD_LOCATION, f"processed_{data['video_file']}")

    # Start download + process simulation
    sts = await query.message.edit(f"📥 Downloading **{data['video_file']}** ...")
    c_time = time.time()

    # Already downloaded in first step, so skip actual download
    await asyncio.sleep(1)

    await sts.edit("✅ Download complete!\n⚙️ Now merging subtitles...")

    # Merge with ffmpeg (soft-sub)
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", subtitle_path,
        "-c", "copy", "-c:s", "mov_text",  # keep streams intact
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
    # Don't delete files (as per request)


