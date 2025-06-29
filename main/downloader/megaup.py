import os
import time
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION, MEGA_EMAIL, MEGA_PASSWORD
from main.utils import humanbytes, progress_message
from main.mega_fixed.mega import Mega  # using the bundled local version

@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply("⚠️ Please reply to a file (video, audio, or document).")

    media = reply.document or reply.video or reply.audio
    if not media:
        return await msg.reply("❌ This media type is not supported for upload.")

    file_name = media.file_name or "Telegram_File"
    og_media = getattr(reply, reply.media.value)

    sts = await msg.reply("📥 Starting download...")
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
        progress=progress_message,
        progress_args=("Downloading file...", sts, c_time)
    )
    file_size = humanbytes(og_media.file_size)

    await sts.edit("🔐 Logging into MEGA account...")
    try:
        mega = Mega()
        m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)
    except Exception as e:
        return await sts.edit(f"❌ MEGA login failed:\n`{e}`")

    await sts.edit("📤 Uploading to MEGA...")
    c_time = time.time()

    def mega_progress(current, total):
        percent = (current / total) * 100
        status = f"📤 Uploading...\n{humanbytes(current)} of {humanbytes(total)} ({percent:.2f}%)"
        if percent % 10 < 1:  # updates every 10%
            try:
                bot.loop.create_task(sts.edit(status))
            except:
                pass

    try:
        uploaded = m.upload(
            file=downloaded_path,
            dest_filename=file_name,
            progress=mega_progress
        )
        mega_link = m.get_upload_link(uploaded)
        await sts.edit(f"✅ Uploaded to MEGA!\n\n📁 File: `{file_name}`\n📦 Size: {file_size}\n🔗 [Download Link]({mega_link})", disable_web_page_preview=True)
    except Exception as e:
        return await sts.edit(f"❌ Upload failed:\n`{e}`")

    try:
        os.remove(downloaded_path)
    except:
        pass
