import os, time, subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Step 1: /megaup command handler
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
    
    # Button for Info
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📊 Info", callback_data="mega_info")]]
    )
    
    sts = await msg.reply_text(
        f"📥 **Downloading:** **`{filename}`**\n\n🔁 Please wait...",
        reply_markup=buttons
    )

    # Step 2: Download from Telegram
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, filename),
        progress=progress_message,
        progress_args=(f"📥 **Downloading:** **`{filename}`**", sts, c_time)
    )

    filesize = humanbytes(og_media.file_size)

    # Step 3: Load Mega credentials
    login_path = os.path.join(os.path.dirname(__file__), "mega_login.txt")
    try:
        with open(login_path, "r") as f:
            creds = f.read().strip()
        email, password = creds.split(":", 1)
    except Exception as e:
        return await sts.edit(f"❌ Failed to load mega_login.txt: {e}")

    # Step 4: Create rclone config
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    obscured_pass = os.popen(f"rclone obscure \"{password.strip()}\"").read().strip()
    if not obscured_pass:
        return await sts.edit("❌ Failed to obscure Mega password.")
    with open(rclone_config_path + "rclone.conf", "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 5: Upload to Mega with progress
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--stats=2s", "--stats-one-line", "--log-level", "INFO"
    ]
    env = os.environ.copy()
    env["RCLONE_CONFIG"] = os.path.join(rclone_config_path, "rclone.conf")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )

    last_update = time.time()
    progress_line = ""

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if "Transferred:" in line:
            progress_line = line.strip()
            if time.time() - last_update > 2:
                try:
                    await sts.edit(
                        f"☁️ **Uploading:** **`{filename}`**\n\n`{progress_line}`\n\n💽 Size: {filesize}"
                    )
                except:
                    pass
                last_update = time.time()

    proc.wait()

    # Step 6: Final status
    if proc.returncode == 0:
        await sts.edit(f"✅ **Upload complete to Mega.nz**\n\n📁 File: `{filename}`\n💽 Size: {filesize}")
    else:
        await sts.edit("❌ Upload failed. Please check your credentials or try again later.")

    # Cleanup
    try:
        os.remove(downloaded_path)
    except:
        pass


# Step 7: Handle Info button
@Client.on_callback_query(filters.regex("mega_info"))
async def mega_info_callback(bot: Client, query: CallbackQuery):
    await query.answer()  # close the button spinner

    # Correct path where rclone.conf was written
    rclone_config_path = "/root/.config/rclone/"
    rclone_config_file = os.path.join(rclone_config_path, "rclone.conf")

    if not os.path.exists(rclone_config_file):
        return await query.message.reply_text("❌ Mega config not found. Upload something first using /megaup.")

    try:
        # Set RCLONE_CONFIG so rclone can find the config
        env = os.environ.copy()
        env["RCLONE_CONFIG"] = rclone_config_file

        result = subprocess.check_output(
            ["rclone", "about", "mega:"],
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )

        await query.message.reply_text(f"📊 **Cloud Info (Mega.nz):**\n\n`{result.strip()}`")

    except subprocess.CalledProcessError as e:
        await query.message.reply_text(f"❌ Failed to fetch Mega info:\n\n`{e.output.strip()}`")
