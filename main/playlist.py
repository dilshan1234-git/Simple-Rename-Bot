import yt_dlp
from pyrogram import Client, filters

# Extracts video URLs from YouTube playlists


def extract_playlist(playlist_url):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        playlist_info = ydl.extract_info(playlist_url, download=False)
        return playlist_info


@Client.on_message(filters.private & filters.command("playlist"))
async def extract_playlist_url(bot, msg):
    reply = msg.reply_to_message
    playlist_url = None

    # Check if the user replied to a message containing a URL
    if reply and reply.text:
        playlist_url = reply.text.strip()

    # Check if a URL is provided with the command
    elif len(msg.command) > 1:
        playlist_url = msg.text.split(" ", 1)[1].strip()

    # If no URL is provided, send a message prompting the user
    if not playlist_url:
        return await msg.reply_text("Please reply to a message containing a YouTube playlist URL or provide the URL with the /playlist command.")

    sts = await msg.reply_text("🔄 Processing your playlist URL...📥")

    try:
        playlist_info = extract_playlist(playlist_url)
        if not playlist_info.get("entries"):
            return await sts.edit("❌ No videos found in the playlist.")

        playlist_name = playlist_info.get("title", "Untitled Playlist")
        video_entries = playlist_info["entries"]

        video_list = []
        for i, entry in enumerate(video_entries, start=1):
            video_title = entry.get("title", "Untitled Video")
            video_url = entry.get("url", "")
            # Monospace for the URL
            video_list.append(
                f"{i}. 🎬 **{video_title}**\n\n📎URL = `{video_url}`")

        # Split the video list into chunks of 20 and send them as separate
        # messages
        chunk_size = 20
        for idx in range(0, len(video_list), chunk_size):
            chunk = video_list[idx:idx + chunk_size]
            message = f"📃 Playlist: **{playlist_name}**\n\n" + \
                "\n\n".join(chunk)
            # No parse_mode specified
            await bot.send_message(msg.chat.id, message)

        # Final message showing all URLs processed
        await msg.reply_text(f"✅ All URLs processed! {len(video_entries)} videos found.")
    except Exception as e:
        await sts.edit(f"❌ Error: {e}")
