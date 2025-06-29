import time, os
from pyrogram import Client, filters
from mega import Mega
from config import ADMIN, DOWNLOAD_LOCATION, MEGA_EMAIL, MEGA_PASSWORD
from main.utils import progress_message, humanbytes

@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("⚠️ Please reply to a file, video, or audio to upload to MEGA.")

    media = reply.document or reply.video or reply.audio
    if not media:
        return await msg.reply_text("⚠️ Unsupported file type. Please reply to a file, video, or audio.")

    file_name = media.file_name or "Telegram_File"
    og_media = getattr(reply, reply.media.value)

    sts = await msg.reply_text("🔄 Trying to Download.....📥")
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
        progress=progress_message,
        progress_args=("📥 Download Started.....", sts, c_time)
    )
    file_size = humanbytes(og_media.file_size)

    await sts.edit("🔐 Logging into MEGA....")
    try:
        mega = Mega()
        m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)
    except Exception as e:
        return await sts.edit(f"❌ MEGA Login Failed:\n`{e}`")

    await sts.edit("🚀 Uploading to MEGA.....")
    c_time = time.time()

    def mega_progress(current, total):
        # update progress bar during upload
        try:
            percent = (current / total) * 100
            status = f"📤 Uploading to MEGA...\n{humanbytes(current)} of {humanbytes(total)} ({percent:.2f}%)"
            if percent % 10 < 1:  # update roughly every 10%
                bot.loop.create_task(sts.edit(status))
        except:
            pass

    try:
        uploaded = m.upload(file=downloaded_path, dest=None, dest_filename=file_name, progress=mega_progress)
        link = m.get_upload_link(uploaded)
        await sts.edit(f"✅ Uploaded to MEGA!\n\n📁 File: `{file_name}`\n📦 Size: {file_size}\n🔗 [Download Link]({link})")
    except Exception as e:
        return await sts.edit(f"❌ Upload Failed:\n`{e}`")

    try:
        os.remove(downloaded_path)
    except:
        pass
