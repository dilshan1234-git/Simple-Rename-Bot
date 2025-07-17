import os, time, subprocess, re
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
    
    sts = await msg.reply_text(f"📥 **Downloading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 1: Download from Telegram
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

    # Step 4: Upload to Mega with progress
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--stats=2s", "--stats-one-line", "--log-level", "INFO"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    last_update = time.time()
    progress_line = ""

    while True:
        line = proc.stdout.readline()
        if not line:
            break

        # Look for rclone progress lines like:
        # Transferred:   	    45.678 MiB / 200.123 MiB, 23%, 3.456 MiB/s, ETA 00:45
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

    # Step 5: Final status
    if proc.returncode == 0:
        await sts.edit(f"✅ **Upload complete to Mega.nz**\n\n📁 File: `{filename}`\n💽 Size: {filesize}")
    else:
        await sts.edit("❌ Upload failed. Please check your credentials or try again later.")

    # Cleanup
    try:
        os.remove(downloaded_path)
    except:
        pass
