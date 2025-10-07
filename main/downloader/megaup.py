import os
import time
import subprocess
import json
import re
import asyncio
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
    total_size = og_media.file_size

    # Step 2: Load Mega credentials
    login_path = os.path.join(os.path.dirname(__file__), "mega_login.txt")
    try:
        with open(login_path, "r") as f:
            creds = f.read().strip()
        email, password = creds.split(":", 1)
    except Exception as e:
        return await sts.edit(f"❌ Failed to load mega_login.txt: {e}")

    # Step 3: Create rclone config file
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    obscured_pass = os.popen(f"rclone obscure \"{password.strip()}\"").read().strip()
    with open(os.path.join(rclone_config_path, "rclone.conf"), "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Upload to Mega with real-time progress
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--progress", "--stats-one-line",
        "--stats=1s", "--log-level", "INFO", "--config", os.path.join(rclone_config_path, "rclone.conf")
    ]

    print(f"🔄 Uploading '{filename}' to Mega.nz...\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    upload_start_time = time.time()
    last_update_time = time.time()
    update_interval = 2  # Update every 2 seconds

    # Pattern to extract progress from rclone output
    pattern = re.compile(r'(\d+\.?\d*)\s*([KMGT]?i?B)\s*/\s*(\d+\.?\d*)\s*([KMGT]?i?B),\s*(\d+)%')

    async def update_upload_progress():
        nonlocal last_update_time
        buffer = ""

        while True:
            char = proc.stdout.read(1)
            if not char:
                break
            buffer += char

            if "\n" in buffer or "\r" in buffer:
                lines = re.split(r'[\r\n]+', buffer)
                for line in lines[:-1]:
                    print(line.strip())
                    match = pattern.search(line)
                    if match and time.time() - last_update_time >= update_interval:
                        try:
                            transferred_val = float(match.group(1))
                            transferred_unit = match.group(2)
                            units = {'B':1,'KiB':1024,'MiB':1024**2,'GiB':1024**3,'TiB':1024**4,
                                     'KB':1000,'MB':1000**2,'GB':1000**3,'TB':1000**4}
                            current_bytes = int(transferred_val * units.get(transferred_unit,1))
                            await progress_message(
                                current_bytes,
                                total_size,
                                f"☁️ **Uploading:** **`{filename}`**",
                                sts,
                                upload_start_time
                            )
                            last_update_time = time.time()
                        except Exception as e:
                            if "MESSAGE_NOT_MODIFIED" not in str(e):
                                print(f"Error updating progress: {e}")
                buffer = lines[-1]

    # Run progress updates
    await update_upload_progress()
    proc.wait()

    # Step 5: Get Mega Storage Info (via --json)
    try:
        about_output = os.popen(f"rclone about mega: --json --config {os.path.join(rclone_config_path, 'rclone.conf')}").read()
        stats = json.loads(about_output)
        total_bytes = stats.get("total", 0)
        used_bytes = stats.get("used", 0)
        free_bytes = stats.get("free", 0)

        total = humanbytes(total_bytes)
        used = humanbytes(used_bytes)
        free = humanbytes(free_bytes)

        used_pct = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0
        full_blocks = used_pct // 10
        empty_blocks = 10 - full_blocks
        bar = "█" * full_blocks + "░" * empty_blocks
    except Exception:
        total = used = free = "Unknown"
        used_pct = 0
        bar = "░" * 10

    # Step 6: Final Message
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
        final_text = "❌ Upload failed. Please check your credentials or try again later."

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Delete", callback_data="delmegamsg")]
    ])

    try:
        await sts.edit(final_text, reply_markup=btn)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            print(f"Error updating final message: {e}")

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
