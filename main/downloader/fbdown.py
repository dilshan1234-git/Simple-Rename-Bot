import os
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from config import DOWNLOAD_LOCATION, ADMIN


# Function to download images from a Facebook post
def download_fb_images(post_url):
    response = requests.get(post_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    images = soup.find_all('img')
    image_urls = [img['src'] for img in images if 'src' in img.attrs]
    return image_urls

@app.on_message(filters.command("fbdl") & filters.user(ADMIN))
async def fb_download_images(bot, msg):
    await msg.reply_text("📤 Please send the Facebook post link to download images.")
    link = await bot.wait_for_message(msg.chat.id)
    if not link.text.startswith("http"):
        return await msg.reply_text("❌ Invalid link. Please send a valid Facebook post link.")
    
    processing_msg = await msg.reply_text("🔄 Processing... Please wait.")
    image_urls = download_fb_images(link.text)
    if not image_urls:
        return await processing_msg.edit_text("❌ No images found in the post.")
    
    download_msg = await processing_msg.edit_text(f"📥 Downloading {len(image_urls)} images...")
    downloaded_images = []
    for i, url in enumerate(image_urls, start=1):
        response = requests.get(url)
        image_path = os.path.join(DOWNLOAD_LOCATION, f"image_{i}.jpg")
        with open(image_path, 'wb') as f:
            f.write(response.content)
        downloaded_images.append(image_path)
        await download_msg.edit_text(f"📥 Downloading image {i} of {len(image_urls)}...")
    
    upload_msg = await download_msg.edit_text("📤 Uploading images...")
    for i, image_path in enumerate(downloaded_images, start=1):
        await bot.send_photo(msg.chat.id, photo=image_path, caption=f"Image {i}")
        os.remove(image_path)
        await upload_msg.edit_text(f"📤 Uploading image {i} of {len(downloaded_images)}...")
    
    await upload_msg.edit_text("✅ All images have been uploaded successfully!")
