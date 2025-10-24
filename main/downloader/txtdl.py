import os
import re
import asyncio
import aiofiles
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import DOWNLOAD_LOCATION, ADMIN
from main.downloader.downloader import youtube_link_handler

BATCH_SIZE = 10  # Number of URLs per batch

# /txtdl command
@Client.on_message(filters.private & filters.command("txtdl") & filters.user(ADMIN))
async def txt_dl(bot: Client, msg: Message):
    """Reply to a .txt file with /txtdl to process URLs in batches."""
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("❌ Reply to a .txt file containing YouTube URLs.")
        return

    doc = msg.reply_to_message.document
    if not doc.file_name.endswith(".txt"):
        await msg.reply_text("❌ File must be a .txt file.")
        return

    # Download the txt file
    file_path = os.path.join(DOWNLOAD_LOCATION, doc.file_name)
    await bot.download_media(doc, file_path)

    # Read URLs and titles
    urls = []
    titles = []
    async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
        content = await f.read()
        # Regex to match your format
        matches = re.findall(r"title\s*-\s*'(.*?)'\s*\|\s*.*?\nurl\s*-\s*'(https?://.*?)'", content, re.DOTALL)
        for title, url in matches:
            titles.append(title.strip())
            urls.append(url.strip())

    total = len(urls)
    if total == 0:
        await msg.reply_text("❌ No valid URLs found in the file.")
        return

    # Build range buttons
    buttons = []
    for i in range(0, total, BATCH_SIZE):
        start = i + 1
        end = min(i + BATCH_SIZE, total)
        buttons.append([InlineKeyboardButton(f"{start} - {end}", callback_data=f"txt_{start-1}_{end-1}")])
    buttons.append([InlineKeyboardButton(f"All ({total})", callback_data=f"txt_0_{total-1}")])
    markup = InlineKeyboardMarkup(buttons)

    await msg.reply_text(
        f"✅ Found {total} URLs in the .txt file.\nSelect a range to process:",
        reply_markup=markup
    )

    # Save URLs in memory for callback
    bot.txt_urls_cache = urls

    # Cleanup txt file
    if os.path.exists(file_path):
        os.remove(file_path)


# Callback handler for range selection
@Client.on_callback_query(filters.regex(r'^txt_\d+_\d+'))
async def txt_range_handler(bot: Client, query):
    data = query.data.split("_")
    start_idx = int(data[1])
    end_idx = int(data[2])

    urls = getattr(bot, "txt_urls_cache", [])
    if not urls:
        await query.message.edit_text("❌ URL cache expired. Please resend the /txtdl command.")
        return

    batch_urls = urls[start_idx:end_idx+1]
    await query.message.edit_text(f"🔄 Processing URLs {start_idx+1} to {end_idx+1} ({len(batch_urls)} URLs)...")

    for url in batch_urls:
        fake_msg = Message(**{k: getattr(query.message, k) for k in query.message.__slots__})
        fake_msg.text = url
        await youtube_link_handler(bot, fake_msg)
        await asyncio.sleep(1)  # small delay between URLs

    await query.message.edit_text(f"✅ Finished processing URLs {start_idx+1} to {end_idx+1}.")
