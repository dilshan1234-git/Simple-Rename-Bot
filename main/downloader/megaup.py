import os
import time
import json
import subprocess
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

    # Step 1: Download from Telegram
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

    # Step 3: Create rclone config
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    obscured_pass = os.popen(f"rclone obscure \"{password.strip()}\"").read().strip()
    with open(os.path.join(rclone_config_path, "rclone.conf"), "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Start rclone upload
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", 
        "--progress", "--stats=1s", "--stats-one-line",
        "--log-level", "INFO", "--config", os.path.join(rclone_config_path, "rclone.conf")
    ]

    print(f"🔄 Uploading '{filename}' to Mega.nz...\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    upload_start_time = time.time()
    last_update_time = time.time()
    update_interval = 1  # Update every 1 second

    async def live_progress():
        nonlocal last_update_time
        # Poll rclone stats every second
        while proc.poll() is None:
            try:
                stats_json = os.popen(
                    f"rclone about mega: --json --config {os.path.join(rclone_config_path, 'rclone.conf')}"
                ).read()
                stats = json.loads(stats_json)
                used_bytes = stats.get("used", 0)
                total_bytes = stats.get("total", 0)
                if time.time() - last_update_time >= update_interval:
                    await progress_message(
                        used_bytes if used_bytes <= total_size else total_size,
                        total_size,
                        f"☁️ **Uploading:** **`{filename}`**",
                        sts,
                        upload_start_time
                    )
                    last_update_time = time.time()
            except Exception as e:
                # Ignore occasional JSON parse errors while uploading
                pass
            await asyncio.sleep(1)

    # Run live progress in parallel
    progress_task = asyncio.create_task(live_progress())
    proc.wait()
    await progress_task

    # Step 5: Mega storage info
    try:
        about_output = os.popen(
            f"rclone about mega: --json --config {os.path.join(rclone_config_path, 'rclone.conf')}"
        ).read()
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
        final_text = "❌ Upload failed. Please check credentials or try again later."

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
