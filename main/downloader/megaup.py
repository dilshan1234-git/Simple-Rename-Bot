import os, time, subprocess, json
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

    # Step 4: Show Uploading Status in Bot (Live Progress)
    await sts.edit(f"☁️ **Uploading to Mega.nz:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 5: Upload to Mega and update progress
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", 
        "--progress", "--stats-one-line", "--stats=1s",
        "--log-level", "INFO",
        "--config", os.path.join(rclone_config_path, "rclone.conf")
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    c_time = time.time()

    # Helper: convert "5.12 MiB" -> bytes
    def human_to_bytes(s):
        units = {"B":1, "KiB":1024, "MiB":1024**2, "GiB":1024**3, "TiB":1024**4}
        num, unit = s.split()
        return int(float(num) * units.get(unit, 1))

    async def update_upload_progress(line):
        # Example line:
        # "Transferred:    5.123 MiB / 50.000 MiB, 10%, 1.234 MiB/s, ETA 00:40"
        if "Transferred:" in line and "ETA" in line:
            try:
                parts = line.split(",")
                done = parts[0].replace("Transferred:", "").strip().split("/")[0].strip()
                total = parts[0].split("/")[1].strip()
                percent = parts[1].strip().replace("%", "")
                speed = parts[2].strip()
                eta = parts[3].replace("ETA", "").strip()

                done_bytes = human_to_bytes(done)
                total_bytes = human_to_bytes(total)

                await progress_message(
                    f"☁️ **Uploading to Mega.nz:** **`{filename}`**",
                    sts,
                    c_time,
                    done_bytes,
                    total_bytes,
                    speed,
                    eta
                )
            except Exception as e:
                print("Parse error:", e)

    # Stream lines from rclone
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(line.strip())
        await update_upload_progress(line)

    proc.wait()

    # Step 6: Get Mega Storage Info (via --json)
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

        # Draw storage bar
        full_blocks = used_pct // 10
        empty_blocks = 10 - full_blocks
        bar = "█" * full_blocks + "░" * empty_blocks

    except Exception as e:
        total = used = free = "Unknown"
        used_pct = 0
        bar = "░" * 10

    # Step 7: Final Message with Storage Info and Delete Button
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

    await sts.edit(final_text, reply_markup=btn)

    # Step 8: Cleanup
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
