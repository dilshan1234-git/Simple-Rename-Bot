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

    # Step 4: Upload to Mega with real-time progress
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    cmd = [
        "rclone", "copyto", downloaded_path, f"mega:{filename}",
        "--progress", "--stats=1s", "--stats-one-line", "--log-level", "INFO"
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
            if proc.poll() is not None:
                break
            continue

        line = line.strip()

        if "Transferred:" in line:
            # Clean up and extract the stats string
            match = re.search(r"Transferred:\s+(.+)", line)
            if match:
                progress_info = match.group(1)

                # Optional: Remove multiple spaces
                progress_info = re.sub(r'\s+', ' ', progress_info)

                if time.time() - last_edit > 2:
                    try:
                        await sts.edit(
                            f"☁️ **Uploading:** **`{filename}`**\n\n`{progress_info}`"
                        )
                        last_edit = time.time()
                    except:
                        pass

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
