# mega_uploader.py

import os
from pyrogram import Client, filters
from pyrogram.types import Message
from mega.mega import Mega  # Importing from the local patched mega.py

# Load credentials from config or environment
from config import MEGA_EMAIL, MEGA_PASSWORD  # Make sure these are set in your config.py or .env

@Client.on_message(filters.command("mega") & filters.reply)
async def upload_to_mega(client: Client, message: Message):
    reply = message.reply_to_message

    if not (reply.document or reply.video or reply.audio):
        await message.reply("❗ Please reply to a file (document/video/audio) to upload to Mega.nz.")
        return

    status = await message.reply("📥 Downloading the file...")

    try:
        # Step 1: Download file
        file_path = await reply.download()
        await status.edit_text("🔐 Logging into Mega.nz...")

        # Step 2: Login to Mega
        mega = Mega()
        m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)

        await status.edit_text("🚀 Uploading to Mega.nz...")
        uploaded = m.upload(file_path)
        link = m.get_upload_link(uploaded)

        await status.edit_text(f"✅ File uploaded to Mega.nz\n📤 [Click to open]({link})", disable_web_page_preview=True)

    except Exception as e:
        await status.edit_text(f"❌ Failed to upload:\n`{str(e)}`")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
