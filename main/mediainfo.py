import os
import time
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION
from pymediainfo import MediaInfo
from main.utils import progress_message, humanbytes
import telegraph

# Create Telegraph account
telegraph_client = telegraph.Telegraph()
telegraph_client.create_account(short_name="InfoBot")


@Client.on_message(filters.private & filters.command("info")
                   & filters.user(ADMIN))
async def generate_mediainfo(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("❌ Please reply to a video, audio, or document file using the /info command.")

    media = reply.document or reply.audio or reply.video
    if not media:
        return await msg.reply_text("❌ The replied message doesn't contain a supported file type.")

    file_name = media.file_name or "Unnamed_File"
    file_size = media.file_size or 0

    # Show initial message
    sts = await msg.reply_text(f"🔄 **Processing your file...**\n\n📁 `{file_name}`")

    # Download file
    try:
        c_time = time.time()
        downloaded_path = await reply.download(
            file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
            progress=progress_message,
            progress_args=("📥 Downloading...", sts, c_time)
        )
    except Exception as e:
        return await sts.edit(f"❌ Failed to download file: {e}")

    if not downloaded_path or not os.path.exists(downloaded_path):
        return await sts.edit("❌ Downloaded file path not found.")

    # Parse media info
    try:
        media_info = MediaInfo.parse(downloaded_path)
    except Exception as e:
        return await sts.edit(f"❌ Failed to parse media info: {e}")

    # Format content
    def format_info(key, value, spacing=40):
        key_space = ' ' * (spacing - len(key))
        return f"{key}{key_space}: {value}\n"

    general_info, video_info, audio_info = "", "", ""

    for track in media_info.tracks:
        if track.track_type == "General":
            general_info += format_info("File Name", file_name)
            general_info += format_info("File Size", humanbytes(file_size))
            for k, v in track.to_data().items():
                if v:  # Avoid empty/null values
                    general_info += format_info(k.replace("_",
                                                " ").capitalize(), v)
        elif track.track_type == "Video":
            for k, v in track.to_data().items():
                if v:
                    video_info += format_info(k.replace("_",
                                              " ").capitalize(), v)
        elif track.track_type == "Audio":
            for k, v in track.to_data().items():
                if v:
                    audio_info += format_info(k.replace("_",
                                              " ").capitalize(), v)

    # Wrap content in HTML
    content = f"""
<h3>📁 General Information</h3>
<pre>{general_info}</pre>

<h3>🎥 Video Information</h3>
<pre>{video_info}</pre>

<h3>🔊 Audio Information</h3>
<pre>{audio_info}</pre>
"""

    # Upload to Telegraph
    try:
        response = telegraph_client.create_page(
            title=file_name,
            html_content=content
        )
        telegraph_url = f"https://telegra.ph/{response['path']}"
    except Exception as e:
        return await sts.edit(f"❌ Telegraph upload failed: {e}")

    # Send result
    await sts.edit(
        f"📄 **File Name:** [{file_name}]({telegraph_url})\n"
        f"💾 **Size:** {humanbytes(file_size)}\n"
        f"📊 **Media Info:** [View on Telegraph]({telegraph_url})\n\n"
        "✅ **Info generated successfully!**",
        disable_web_page_preview=False
    )

    # Clean up
    try:
        os.remove(downloaded_path)
    except Exception as e:
        print(f"⚠️ File cleanup failed: {e}")
