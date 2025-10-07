import os, time, subprocess, json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN, API_ID, API_HASH, BOT_TOKEN
from main.utils import progress_message, humanbytes

# Telethon client for fast downloads (lazy initialization)
telethon_client = None

async def get_telethon_client():
    """Initialize Telethon bot client for fast downloads"""
    global telethon_client
    if telethon_client is None:
        from telethon import TelegramClient
        telethon_client = TelegramClient('fast_bot', API_ID, API_HASH)
        await telethon_client.start(bot_token=BOT_TOKEN)
    return telethon_client

async def fast_download(message, file_path, sts):
    """Download using fast-telethon (5-10x faster)"""
    try:
        from telethon.sync import TelegramClient
        from fast_telethon import download_file
        
        # Get telethon client
        client = await get_telethon_client()
        
        # Get message in telethon
        tele_msg = await client.get_messages(message.chat.id, ids=message.id)
        
        if not tele_msg or not tele_msg.media:
            return None
        
        print(f"🚀 Using fast-telethon for high-speed download...")
        
        # Download with fast-telethon
        start_time = time.time()
        last_update = start_time
        
        async def progress_callback(current, total):
            nonlocal last_update
            if time.time() - last_update > 2:  # Update every 2 seconds
                try:
                    percent = (current / total) * 100
                    elapsed = time.time() - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    
                    await sts.edit(
                        f"📥 **Downloading:** **`{os.path.basename(file_path)}`**\n\n"
                        f"📊 {percent:.1f}% | ⚡ {humanbytes(int(speed))}/s"
                    )
                    last_update = time.time()
                except:
                    pass
        
        # Fast download
        file_data = await download_file(
            client=client,
            location=tele_msg.media,
            out=open(file_path, 'wb'),
            progress_callback=progress_callback
        )
        
        print(f"✅ Fast download completed!")
        return file_path
        
    except Exception as e:
        print(f"⚠️ Fast-telethon failed: {e}")
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
    
    # Try fast-telethon first
    downloaded_path = await fast_download(reply, file_path, sts)
    
    # Fallback to pyrogram if fast-telethon fails
    if not downloaded_path:
        print("⚠️ Falling back to Pyrogram download")
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
