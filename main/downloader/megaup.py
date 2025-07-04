import os, time, subprocess
from pyrogram import Client, filters
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
    sts = await msg.reply_text("📥 Downloading file to local storage...")

    # Step 1: Download file from Telegram
    c_time = time.time()
    downloaded_path = await reply.download(
        file_name=os.path.join(DOWNLOAD_LOCATION, filename),
        progress=progress_message,
        progress_args=("Downloading from Telegram...", sts, c_time)
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
    with open(rclone_config_path + "rclone.conf", "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Upload to Mega with progress
    await sts.edit("🚀 Uploading to Mega.nz...")
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
    lines_buffer = ""

    # Stream live progress to Telegram message
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        lines_buffer += line
        if time.time() - last_edit > 3:
            try:
                await sts.edit(f"☁️ Uploading...\n\n`{line.strip()}`\n\n📁 File: `{filename}`\n💽 Size: {filesize}")
            except:
                pass
            last_edit = time.time()

    proc.wait()

    # Step 5: Confirm and clean up
    if proc.returncode == 0:
        await sts.edit(f"✅ Upload complete to Mega.nz\n\n📁 File: `{filename}`\n💽 Size: {filesize}")
    else:
        await sts.edit("❌ Upload failed. Please check your credentials or try again later.")

    try:
        os.remove(downloaded_path)
    except:
        pass
