import os, time, asyncio, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Store temp data
MERGE_DATA = {}

@Client.on_message(filters.private & filters.command("merge") & filters.user(ADMIN))
async def merge_start(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("Please reply to a video/document with `/merge` command.")

    media = reply.document or reply.video
    if not media:
        return await msg.reply_text("Please reply to a valid video/document file.")

    file_name = media.file_name
    file_size = humanbytes(media.file_size)
    duration = getattr(media, "duration", None)

    txt = f"**🎬 File Name:** `{file_name}`\n" \
          f"**💽 Size:** `{file_size}`\n"
    if duration:
        txt += f"**🕒 Duration:** `{duration} sec`\n"
    txt += "\n📩 Now send me your subtitle file (e.g. .srt, .ass)."

    MERGE_DATA[msg.chat.id] = {"video_msg": reply}
    await msg.reply_text(txt)


@Client.on_message(filters.private & filters.user(ADMIN))
async def subtitle_receive(bot, msg):
    if msg.chat.id not in MERGE_DATA:
        return
    if not msg.document:
        return await msg.reply_text("Please send me a valid subtitle file (.srt/.ass).")

    sub_file = msg.document.file_name
    MERGE_DATA[msg.chat.id]["subtitle_msg"] = msg

    video_name = MERGE_DATA[msg.chat.id]["video_msg"].document.file_name if MERGE_DATA[msg.chat.id]["video_msg"].document else MERGE_DATA[msg.chat.id]["video_msg"].video.file_name

    txt = f"**🎬 Video File:** `{video_name}`\n" \
          f"**📄 Subtitle File:** `{sub_file}`\n\n✅ Do you want to continue?"

    buttons = [[
        InlineKeyboardButton("✅ Confirm", callback_data="merge_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="merge_cancel")
    ]]

    await msg.reply_text(txt, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("merge_"))
async def merge_callback(bot, query: CallbackQuery):
    data = query.data
    chat_id = query.message.chat.id
    user_data = MERGE_DATA.get(chat_id)

    if not user_data:
        return await query.message.edit("Session expired. Please try again.")

    if data == "merge_cancel":
        MERGE_DATA.pop(chat_id, None)
        return await query.message.edit("❌ Merge cancelled.")

    if data == "merge_confirm":
        await query.message.delete()
        video_msg = user_data["video_msg"]
        sub_msg = user_data["subtitle_msg"]

        sts = await bot.send_message(chat_id, "⏳ Downloading video...")
        c_time = time.time()

        video_path = await video_msg.download(
            file_name=video_msg.document.file_name if video_msg.document else video_msg.video.file_name,
            progress=progress_message,
            progress_args=("Downloading video...", sts, c_time)
        )
        await sts.edit("✅ Video downloaded.\n⏳ Downloading subtitle...")

        subtitle_path = await sub_msg.download(
            file_name=sub_msg.document.file_name,
            progress=progress_message,
            progress_args=("Downloading subtitle...", sts, c_time)
        )

        await sts.edit("✅ Subtitle downloaded.\n⚙️ Processing...")

        base, ext = os.path.splitext(video_path)
        output_file = base + "_merged" + ext

        # Merge using ffmpeg
        cmd = [
            "ffmpeg", "-i", video_path, "-i", subtitle_path,
            "-c", "copy", "-c:s", "srt",
            output_file, "-y"
        ]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await process.communicate()

        await sts.edit("✅ Processing done.\n📤 Uploading...")

        c_time = time.time()
        try:
            if video_msg.document:
                await bot.send_document(
                    chat_id, document=output_file,
                    caption="✅ Processed File",
                    progress=progress_message,
                    progress_args=("Uploading...", sts, c_time)
                )
            else:
                await bot.send_video(
                    chat_id, video=output_file,
                    caption="✅ Processed File",
                    progress=progress_message,
                    progress_args=("Uploading...", sts, c_time)
                )
        except Exception as e:
            await sts.edit(f"❌ Upload failed: {e}")
            return

        await sts.delete()
        MERGE_DATA.pop(chat_id, None)
