import os
import time
from pyrogram import Client, filters
from config import ADMIN
from main.utils import humanbytes
import telegraph

# Create Telegraph account
telegraph_client = telegraph.Telegraph()
telegraph_client.create_account(short_name="InfoBot")


@Client.on_message(filters.private & filters.command("info") & filters.user(ADMIN))
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

    # Build info sections
    def format_info(key, value, spacing=40):
        key_space = ' ' * (spacing - len(key))
        return f"{key}{key_space}: {value}\n"

    general_info, video_info, audio_info = "", "", ""

    # General info (Telegram metadata)
    general_info += format_info("File Name", file_name)
    general_info += format_info("File Size", humanbytes(file_size))
    general_info += format_info("Mime Type", getattr(media, "mime_type", "N/A"))

    if getattr(media, "date", None):
        general_info += format_info("Upload Date", media.date.strftime("%Y-%m-%d %H:%M:%S"))

    # Video info
    if reply.video:
        video_info += format_info("Duration", f"{reply.video.duration}s")
        video_info += format_info("Width", reply.video.width)
        video_info += format_info("Height", reply.video.height)
        video_info += format_info("Supports Streaming", reply.video.supports_streaming)

    # Audio info
    if reply.audio:
        audio_info += format_info("Duration", f"{reply.audio.duration}s")
        audio_info += format_info("Performer", getattr(reply.audio, "performer", "N/A"))
        audio_info += format_info("Title", getattr(reply.audio, "title", "N/A"))
        audio_info += format_info("Mime Type", getattr(reply.audio, "mime_type", "N/A"))

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
