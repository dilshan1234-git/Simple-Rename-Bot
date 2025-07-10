import os, re, time
import requests
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION
from main.utils import humanbytes, progress_message


@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_public(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.text:
        return await msg.reply("⚠️ Please reply to a message that includes an Instagram profile URL.")

    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", reply.text)
    if not match:
        return await msg.reply("❌ Invalid Instagram profile URL.")
    
    username = match.group(1)
    sts = await msg.reply(f"🔍 Fetching stories for `{username}`...")

    # Use a public third-party scraper (no login)
    api_url = f"https://api.storiesig.info/api/stories/{username}"

    try:
        response = requests.get(api_url)
        data = response.json()
    except Exception as e:
        return await sts.edit(f"❌ API error: {e}")

    if "items" not in data or not data["items"]:
        return await sts.edit("ℹ️ No stories found or account may be private.")

    total = 0
    for item in data["items"]:
        media_url = item.get("video_versions", [{}])[0].get("url") or item.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
        if not media_url:
            continue

        try:
            total += 1
            file_ext = ".mp4" if "video" in item else ".jpg"
            filename = os.path.join(DOWNLOAD_LOCATION, f"{username}_{total}{file_ext}")

            c_time = time.time()
            with requests.get(media_url, stream=True) as r:
                with open(filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            size = humanbytes(os.path.getsize(filename))
            caption = f"👤 {username}\n📦 {size}"

            if filename.endswith(".mp4"):
                await bot.send_video(
                    chat_id=msg.chat.id,
                    video=filename,
                    caption=caption,
                    progress=progress_message,
                    progress_args=("📤 Uploading story...", sts, c_time),
                )
            else:
                await bot.send_photo(
                    chat_id=msg.chat.id,
                    photo=filename,
                    caption=caption,
                    progress=progress_message,
                    progress_args=("📤 Uploading story...", sts, c_time),
                )
            os.remove(filename)
        except Exception as e:
            await bot.send_message(msg.chat.id, f"⚠️ Failed to upload: `{e}`")

    await sts.edit(f"✅ Uploaded {total} public stories from `{username}`.")
