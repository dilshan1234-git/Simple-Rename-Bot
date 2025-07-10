import os, re, time, json
import httpx
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION
from main.utils import humanbytes, progress_message

# Instagram's known app ID exposed by clients
IG_APP_ID = "936619743392459"

@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def instadl_public(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.text:
        return await msg.reply("❌ Please reply to a message containing an Instagram profile URL.")
    
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", reply.text)
    if not m:
        return await msg.reply("❌ Invalid Instagram profile URL.")
    username = m.group(1)
    sts = await msg.reply(f"🔍 Fetching public stories for `{username}`...")

    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/115.0 Safari/537.36",
        "x-ig-app-id": IG_APP_ID,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(url, headers=headers)
        except Exception as e:
            return await sts.edit(f"❌ Request error: {e}")
        if resp.status_code != 200:
            return await sts.edit(f"❌ HTTP {resp.status_code}: unable to fetch profile info.")
        data = resp.json()
    
    user = data.get("data", {}).get("user")
    if not user:
        return await sts.edit("ℹ️ No such public user or blocked content.")
    
    reel_media = user.get("reel", {}).get("reel_media", [])
    if not reel_media:
        return await sts.edit("ℹ️ No active public stories found.")

    total = 0
    for item in reel_media:
        total += 1
        media_url = item.get("video_versions", [{}])[0].get("url") or \
                    item.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
        if not media_url:
            continue

        ext = ".mp4" if "video" in media_url else ".jpg"
        filename = os.path.join(DOWNLOAD_LOCATION, f"{username}_{item.get('id')}{ext}")
        ctime = time.time()
        try:
            r = await client.get(media_url, timeout=60.0)
            with open(filename, "wb") as f:
                f.write(r.content)

            size = humanbytes(os.path.getsize(filename))
            caption = f"👤 {username}\n📦 {size}"

            if ext == ".mp4":
                duration = item.get("video_duration", 0)
                await bot.send_video(msg.chat.id, filename, caption=caption,
                                     duration=int(duration),
                                     progress=progress_message,
                                     progress_args=("📤 Uploading story...", sts, ctime))
            else:
                await bot.send_photo(msg.chat.id, filename, caption=caption,
                                     progress=progress_message,
                                     progress_args=("📤 Uploading story...", sts, ctime))
            os.remove(filename)
        except Exception as e:
            await bot.send_message(msg.chat.id, f"⚠️ Failed to process story: `{e}`")

    await sts.edit(f"✅ Uploaded {total} public stories from **{username}**.")
