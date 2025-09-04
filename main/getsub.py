import os, time, json, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Temporary storage
sub_extract_store = {}

@Client.on_message(filters.private & filters.command("getsub") & filters.user(ADMIN))
async def get_subtitles(bot, msg):
    reply = msg.reply_to_message
    if not reply or not (reply.video or reply.document):
        return await msg.reply_text("❌ Please reply to a `.mkv` file!")

    media = reply.document or reply.video
    if not (media and media.file_name.endswith(".mkv")):
        return await msg.reply_text("❌ This command only works with `.mkv` files.")

    file_name = media.file_name
    file_size = humanbytes(media.file_size)

    # Start downloading
    sts = await msg.reply_text("📥 **Preparing to download file...**")
    c_time = time.time()
    try:
        downloaded = await reply.download(
            file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
            progress=progress_message,
            progress_args=("⬇️ **Downloading MKV...**", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"⚠️ Download failed: {e}")

    # Extract subtitle info using ffprobe
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "s", downloaded
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        streams = json.loads(result.stdout)["streams"]
    except Exception as e:
        await sts.edit(f"⚠️ Error reading subtitle info: {e}")
        os.remove(downloaded)
        return

    if not streams:
        await sts.edit("❌ No subtitles found in this MKV.")
        os.remove(downloaded)
        return

    # Format subtitle info
    sub_info = []
    for idx, s in enumerate(streams):
        lang = s.get("tags", {}).get("language", f"und_{idx}")
        codec = s.get("codec_name", "unknown")
        sub_info.append(f"🎞️ Track {idx}: `{lang}` ({codec})")

    # Save info for confirm step
    sub_extract_store[msg.id] = {
        "path": downloaded,
        "chat_id": msg.chat.id,
        "message_id": msg.id,
        "file_name": file_name,
        "subs": streams
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data=f"sub_confirm_{msg.id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"sub_cancel_{msg.id}")]
    ])

    await sts.delete()
    await msg.reply_text(
        f"📂 **File:** `{file_name}`\n"
        f"💾 **Size:** {file_size}\n\n"
        f"📝 **Subtitles Found:**\n" + "\n".join(sub_info),
        reply_markup=kb
    )


@Client.on_callback_query(filters.regex("^sub_"))
async def sub_callbacks(bot, query: CallbackQuery):
    data = query.data
    _, action, msg_id = data.split("_", 2)
    msg_id = int(msg_id)

    if msg_id not in sub_extract_store:
        return await query.message.edit("⚠️ This request expired. Please try again.")

    info = sub_extract_store[msg_id]

    if action == "cancel":
        os.remove(info["path"])
        sub_extract_store.pop(msg_id, None)
        return await query.message.edit("❌ Cancelled by user.")

    if action == "confirm":
        sts = await query.message.edit("📤 **Extracting subtitles... please wait**")
        output_files = []

        try:
            for idx, s in enumerate(info["subs"]):
                lang = s.get("tags", {}).get("language", f"und_{idx}")
                ext = "srt" if s.get("codec_name") == "subrip" else "ass"
                out_file = os.path.join(DOWNLOAD_LOCATION, f"{info['file_name']}.{lang}.{ext}")

                cmd = ["ffmpeg", "-y", "-i", info["path"], "-map", f"0:s:{idx}", out_file]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                if os.path.exists(out_file):
                    output_files.append(out_file)

            if not output_files:
                await sts.edit("⚠️ Failed to extract subtitles.")
            else:
                await sts.delete()
                for f in output_files:
                    await bot.send_document(info["chat_id"], f, caption=f"📝 Extracted subtitle: `{os.path.basename(f)}`")
                    os.remove(f)

        except Exception as e:
            await sts.edit(f"⚠️ Error: {e}")

        finally:
            os.remove(info["path"])
            sub_extract_store.pop(msg_id, None)
