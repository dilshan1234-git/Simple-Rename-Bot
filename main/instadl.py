import os, time
from pyrogram import Client, filters
from config import ADMIN, DOWNLOAD_LOCATION, INSTA_SESSIONID
from main.utils import humanbytes, progress_message
import instaloader
from instaloader import Profile
import re


@Client.on_message(filters.private & filters.command("instadl") & filters.user(ADMIN))
async def insta_story_downloader(bot, msg):
    reply = msg.reply_to_message
    if not reply or not reply.text:
        return await msg.reply("❌ Please reply to a message containing an Instagram profile URL.")

    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", reply.text)
    if not match:
        return await msg.reply("❌ Invalid Instagram URL. Make sure it contains the username.")

    username = match.group(1)
    sts = await msg.reply(f"🔍 Fetching stories from `{username}`...")

    L = instaloader.Instaloader(dirname_pattern=DOWNLOAD_LOCATION, download_video_thumbnails=False, save_metadata=False)
    L.sessionid = INSTA_SESSIONID

    try:
        profile = Profile.from_username(L.context, username)
        stories = L.get_stories(userids=[profile.userid])
    except Exception as e:
        return await sts.edit(f"❌ Failed to fetch stories: `{e}`")

    total = 0
    for story in stories:
        for item in story.get_items():
            total += 1
            filename = os.path.join(DOWNLOAD_LOCATION, item.mediaid)
            try:
                c_time = time.time()
                L.download_storyitem(item, target=item.mediaid)
                files = [f for f in os.listdir(DOWNLOAD_LOCATION) if f.startswith(str(item.mediaid))]
                for f in files:
                    path = os.path.join(DOWNLOAD_LOCATION, f)
                    size = humanbytes(os.path.getsize(path))
                    caption = f"👤 {username}\n📦 {size}"
                    if f.endswith(".mp4"):
                        duration = int(item.video_duration)
                        await bot.send_video(
                            chat_id=msg.chat.id,
                            video=path,
                            caption=caption,
                            duration=duration,
                            progress=progress_message,
                            progress_args=("📤 Uploading story...", sts, c_time),
                        )
                    else:
                        await bot.send_photo(
                            chat_id=msg.chat.id,
                            photo=path,
                            caption=caption,
                            progress=progress_message,
                            progress_args=("📤 Uploading story...", sts, c_time),
                        )
                    os.remove(path)
            except Exception as e:
                await bot.send_message(msg.chat.id, f"⚠️ Failed: `{e}`")

    if total == 0:
        return await sts.edit("ℹ️ No stories available for this user.")
    await sts.edit(f"✅ Downloaded and uploaded {total} stories from **{username}**.")
