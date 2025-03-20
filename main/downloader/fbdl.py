import time
import os
import requests
from pyrogram import Client, filters
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes
from bs4 import BeautifulSoup

@Client.on_message(filters.private & filters.command("fbdl") & filters.user(ADMIN) & filters.reply)
async def fb_download_images(bot, msg):
    # Check if the replied message contains a valid link
    reply = msg.reply_to_message
    if not reply or not reply.text or not reply.text.startswith("http"):
        return await msg.reply_text("❌ Please reply to a valid Facebook post link with the /fbdl command.")

    post_url = reply.text
    sts = await msg.reply_text("🔄 Processing... Please wait.")

    try:
        # Fetch image URLs from the Facebook post
        response = requests.get(post_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        images = soup.find_all('img')
        image_urls = [img['src'] for img in images if 'src' in img.attrs]

        if not image_urls:
            return await sts.edit_text("❌ No images found in the post.")

        # Download images
        await sts.edit_text(f"📥 Downloading {len(image_urls)} images...")
        downloaded_images = []
        for i, url in enumerate(image_urls, start=1):
            try:
                response = requests.get(url)
                image_path = os.path.join(DOWNLOAD_LOCATION, f"image_{i}.jpg")
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                downloaded_images.append(image_path)
                await sts.edit_text(f"📥 Downloading image {i} of {len(image_urls)}...")
            except Exception as e:
                print(f"Error downloading image {i}: {e}")

        # Upload images to Telegram
        await sts.edit_text("📤 Uploading images...")
        for i, image_path in enumerate(downloaded_images, start=1):
            try:
                c_time = time.time()
                await bot.send_photo(
                    msg.chat.id,
                    photo=image_path,
                    caption=f"Image {i}",
                    progress=progress_message,
                    progress_args=(f"Uploading image {i} of {len(downloaded_images)}...", sts, c_time)
                )
                os.remove(image_path)  # Delete the local file after uploading
            except Exception as e:
                print(f"Error uploading image {i}: {e}")

        await sts.edit_text("✅ All images have been uploaded successfully!")
    except Exception as e:
        await sts.edit_text(f"❌ An error occurred: {e}")
    finally:
        await sts.delete()
