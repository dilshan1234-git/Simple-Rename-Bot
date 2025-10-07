import os, time, subprocess, json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN, BOT_TOKEN
from main.utils import progress_message, humanbytes

async def aria2_download(file_url, file_path, filename):
    """
    Download file using aria2c with 16 parallel connections
    """
    try:
        cmd = [
            "aria2c",
            file_url,
            "-o", filename,
            "-d", DOWNLOAD_LOCATION,
            "-x", "16",
            "-s", "16",
            "-k", "1M",
            "--file-allocation=none",
            "--max-connection-per-server=16",
            "--console-log-level=error"
        ]
        
        proc = subprocess.run(cmd, capture_output=True, text=True)
        
        if proc.returncode == 0:
            return file_path
        else:
            return None
            
    except Exception as e:
        return None

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
    os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_LOCATION, filename)
    
    # Try aria2c download for small files first (Bot API limit: 20MB)
    downloaded_path = None
    if og_media.file_size <= 20 * 1024 * 1024:  # 20MB
        try:
            file_obj = await bot.get_file(media.file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_obj.file_path}"
            downloaded_path = await aria2_download(file_url, file_path, filename)
        except:
            pass
    
    # Fallback to standard download
    if not downloaded_path:
        c_time = time.time()
        downloaded_path = await reply.download(
            file_name=file_path,
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

    # Step 4: Show Uploading Status in Bot (Static)
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 5: Upload to Mega and stream output to Colab logs
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--progress", "--stats-one-line",
        "--stats=1s", "--log-level", "INFO", "--config", os.path.join(rclone_config_path, "rclone.conf")
    ]

    print(f"🔄 Uploading '{filename}' to Mega.nz...\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Print rclone progress in Colab logs
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(line.strip())

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
