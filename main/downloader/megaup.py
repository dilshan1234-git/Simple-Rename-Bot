import os, time, subprocess
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

    # Step 3: Create rclone config
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    obscured_pass = os.popen(f"rclone obscure \"{password.strip()}\"").read().strip()
    with open(rclone_config_path + "rclone.conf", "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Upload to Mega
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--progress", "--stats-one-line",
        "--stats=1s", "--log-level", "INFO"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    last_edit = time.time()

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if time.time() - last_edit > 3:
            try:
                await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n`{line.strip()}`\n\n💽 Size: {filesize}")
            except:
                pass
            last_edit = time.time()

    proc.wait()

    # Step 5: Get Mega Storage Info
    df_output = os.popen("rclone about mega: --config /root/.config/rclone/rclone.conf").read()
    total, used, free, used_pct = "Unknown", "Unknown", "Unknown", 0
    for line in df_output.splitlines():
        if "Total:" in line:
            total = line.split(":")[1].strip()
        elif "Used:" in line:
            used = line.split(":")[1].strip()
        elif "Free:" in line:
            free = line.split(":")[1].strip()

    # Try to calculate used percentage
    try:
        total_bytes = int(os.popen("rclone about mega: --bytes --config /root/.config/rclone/rclone.conf | grep Total | awk '{print $2}'").read().strip())
        used_bytes = int(os.popen("rclone about mega: --bytes --config /root/.config/rclone/rclone.conf | grep Used | awk '{print $2}'").read().strip())
        used_pct = int((used_bytes / total_bytes) * 100)
    except:
        used_pct = 0

    # Draw storage bar
    full_blocks = used_pct // 10
    empty_blocks = 10 - full_blocks
    bar = "█" * full_blocks + "░" * empty_blocks

    # Final Message with Delete Button
    final_text = (
        f"✅ **Upload Complete to Mega.nz!**\n\n"
        f"📁 **File:** `{filename}`\n"
        f"💽 **Size:** {filesize}\n\n"
        f"📦 **Mega Storage**\n"
        f"Used: `{used}` / Total: `{total}`\n"
        f"{bar} `{used_pct}%` used"
    )

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Delete", callback_data="delmegamsg")]
    ])

    await sts.edit(final_text, reply_markup=btn)

    # Cleanup
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
