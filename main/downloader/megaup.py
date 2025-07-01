import os
import time
import subprocess
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION, MEGA_EMAIL, MEGA_PASSWORD
from main.utils import progress_message, humanbytes

@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply or not (reply.document or reply.video or reply.audio):
        return await msg.reply_text("⚠️ Please reply to a file, video, or audio to upload to MEGA.")

    media = reply.document or reply.video or reply.audio
    file_name = media.file_name if media.file_name else "unnamed_file"
    sts = await msg.reply_text("📥 Downloading file to server...")
    c_time = time.time()

    try:
        downloaded_path = await reply.download(
            file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
            progress=progress_message,
            progress_args=("⬇️ Downloading...", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Download error: `{e}`")

    await sts.edit("🔐 Uploading to MEGA...")
    c_time = time.time()

    try:
        cmd = [
            "megaput",
            downloaded_path,
            "--username", MEGA_EMAIL,
            "--password", MEGA_PASSWORD
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            raise Exception(proc.stderr)

        # Extract MEGA link (optional)
        mega_link = None
        for line in proc.stdout.splitlines():
            if "https://mega.nz" in line:
                mega_link = line.strip()
                break

    except Exception as e:
        return await sts.edit(f"❌ Upload failed: `{e}`")

    try:
        os.remove(downloaded_path)
    except:
        pass

    await sts.edit(
        f"✅ File uploaded to MEGA!\n\n📂 File: `{file_name}`\n🔗 Link: {mega_link or 'Not found (check your Mega account manually)'}",
        disable_web_page_preview=True
    )
