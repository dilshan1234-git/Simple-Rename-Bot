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
    with open(rclone_config_path + "rclone.conf", "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Upload to Mega with real-time progress
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    cmd = [
        "rclone", "copyto", downloaded_path, f"mega:{filename}",
        "--progress", "--stats-one-line", "--stats=1s"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    start_time = time.time()
    latest_update = ""

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if "Transferred:" in line:
            # Example: Transferred: 15.323 MiB / 100.123 MiB, 15%, 1.23 MiB/s, ETA 1m10s
            latest_update = line.strip()
            try:
                await sts.edit(
                    f"☁️ **Uploading:** **`{filename}`**\n\n`{latest_update}`\n\n💽 Size: {filesize}"
                )
            except:
                pass

    proc.wait()
