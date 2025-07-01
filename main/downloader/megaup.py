import os
import time
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION
from main.utils import progress_message, humanbytes
from mega import Mega

mega = Mega()

# Login to Mega (replace with your credentials or set env vars)
MEGA_EMAIL = os.getenv("MEGA_EMAIL", "your_email@example.com")
MEGA_PASSWORD = os.getenv("MEGA_PASSWORD", "your_mega_password")

@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply or not (reply.document or reply.video or reply.audio):
        return await msg.reply_text("⚠️ Please reply to a file, video, or audio to upload to MEGA.")

    media = reply.document or reply.video or reply.audio
    file_name = media.file_name if media.file_name else "unnamed_file"
    sts = await msg.reply_text("📥 Starting download to server...")
    c_time = time.time()

    try:
        downloaded_path = await reply.download(
            file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
            progress=progress_message,
            progress_args=("⬇️ Downloading to server...", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Download error: `{e}`")

    file_size = humanbytes(media.file_size)

    await sts.edit("🔐 Logging in to MEGA...")
    try:
        m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)
    except Exception as e:
        return await sts.edit(f"❌ MEGA login failed: `{e}`")

    await sts.edit("📤 Uploading to MEGA...")
    c_time = time.time()

    try:
        file = m.upload(downloaded_path, progress=lambda sent, total: bot.loop.create_task(
            progress_message("📤 Uploading to MEGA...", sts, c_time, sent, total)))
        public_url = m.get_upload_link(file)
    except Exception as e:
        return await sts.edit(f"❌ Upload failed: `{e}`")

    try:
        os.remove(downloaded_path)
    except Exception as e:
        print(f"Cleanup error: {e}")

    await sts.edit(f"✅ Uploaded to MEGA!\n\n📂 File: `{file_name}`\n📦 Size: {file_size}\n🔗 [Open in MEGA]({public_url})", disable_web_page_preview=True)
