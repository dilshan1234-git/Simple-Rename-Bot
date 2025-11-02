import os
import time
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("📌 Please reply to a file (video, audio, doc) to upload to Mega.nz.")

    media = reply.document or reply.video or reply.audio
    if not media:
        return await msg.reply_text("❌ Unsupported file type.")

    og_media = getattr(reply, reply.media.value)
    filename = og_media.file_name or "uploaded_file"

    # Initial download message
    sts = await msg.reply_text(f"📥 **Downloading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 1: Download file from Telegram
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, filename),
        progress=progress_message,
        progress_args=(f"📥 **Downloading:** **`{filename}`**", sts, c_time)
    )

    filesize = humanbytes(og_media.file_size)

    # Step 2: Prepare persistent Mega config
    repo_conf = os.path.join(os.path.dirname(__file__), "rclone.conf")
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    rclone_conf = os.path.join(rclone_config_path, "rclone.conf")

    if not os.path.exists(repo_conf):
        return await sts.edit("❌ Missing `rclone.conf` in your bot directory.\n\n"
                              "Please copy it once from `/root/.config/rclone/rclone.conf` after configuring rclone.")

    # Copy stored rclone.conf into runtime config
    os.system(f"cp '{repo_conf}' '{rclone_conf}'")

    # Step 3: Show Uploading Status
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 4: Upload to Mega
    cmd = [
        "rclone",
        "copy",
        downloaded_path,
        "mega:",
        "--progress",
        "--stats-one-line",
        "--stats=1s",
        "--log-level",
        "INFO",
        "--config",
        rclone_conf
    ]

    print(f"🔄 Uploading '{filename}' to Mega.nz...\n")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(line.strip())

    proc.wait()

    # Step 5: Get Mega Storage Info
    try:
        about_output = os.popen(f"rclone about mega: --json --config {rclone_conf}").read()
        stats = json.loads(about_output)

        total_bytes = stats.get("total", 0)
        used_bytes = stats.get("used", 0)
        free_bytes = stats.get("free", 0)

        total = humanbytes(total_bytes)
        used = humanbytes(used_bytes)
        used_pct = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0

        # Storage usage bar
        full_blocks = used_pct // 10
        empty_blocks = 10 - full_blocks
        bar = "█" * full_blocks + "░" * empty_blocks

    except Exception:
        total = used = "Unknown"
        used_pct = 0
        bar = "░" * 10

    # Step 6: Final message
    if proc.returncode == 0:
        final_text = (
            f"✅ **Upload Complete to Mega.nz!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"💽 **Size:** {filesize}\n\n"
            f"📦 **Mega Storage**\n"
            f"Used: `{used}` / Total: `{total}`\n"
            f"{bar} `{used_pct}%` used"
        )
    else:
        final_text = "❌ Upload failed. Please check your Mega config or try again later."

    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Delete", callback_data="delmegamsg")]])
    await sts.edit(final_text, reply_markup=btn)

    # Step 7: Cleanup
    try:
        os.remove(downloaded_path)
    except:
        pass


@Client.on_callback_query(filters.regex("delmegamsg"))
async def delete_megamsg(bot, query: CallbackQuery):
    try:
        await query.message.delete()
    except:
        pass
    await query.answer("🗑️ Message deleted", show_alert=False)
