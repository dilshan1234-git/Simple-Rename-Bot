import os
import time
import subprocess
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION, MEGA_EMAIL, MEGA_PASSWORD
from main.utils import humanbytes, progress_message


@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply("⚠️ Please reply to a file (video, audio, or document).")

    media = reply.document or reply.video or reply.audio
    if not media:
        return await msg.reply("❌ Unsupported media type.")

    file_name = media.file_name or "Telegram_File"
    og_media = getattr(reply, reply.media.value)

    # Download file with progress
    sts = await msg.reply("📥 Starting download...")
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
        progress=progress_message,
        progress_args=("📥 Downloading...", sts, c_time)
    )
    file_size = humanbytes(og_media.file_size)

    await sts.edit("🔐 Logging into MEGA and uploading...")

    # Upload with megaput command (from megatools)
    # --no-progress to reduce noise
    cmd = [
        "megaput",
        "--username", MEGA_EMAIL,
        "--password", MEGA_PASSWORD,
        "--no-progress",
        downloaded_path
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30 min timeout
    except subprocess.TimeoutExpired:
        return await sts.edit("❌ Upload timed out!")

    if proc.returncode != 0:
        err = proc.stderr.strip() or "Unknown error"
        return await sts.edit(f"❌ Upload failed:\n`{err}`")

    output = proc.stdout.strip()
    # Example output parsing for public link (adjust if needed)
    # megaput output usually contains the link at the end or in the output

    # Try to find the public link in output
    import re
    match = re.search(r'https://mega.nz/\S+', output)
    public_link = match.group(0) if match else None

    if not public_link:
        # If no link found, show raw output for debugging
        public_link = output or "No public link returned"

    await sts.edit(
        f"✅ Uploaded to MEGA!\n\n"
        f"📁 File: `{file_name}`\n"
        f"📦 Size: {file_size}\n"
        f"🔗 [Download Link]({public_link})",
        disable_web_page_preview=True
    )

    try:
        os.remove(downloaded_path)
    except Exception:
        pass
