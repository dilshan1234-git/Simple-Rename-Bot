import os
import re
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, ADMIN
from main.downloader import downloader  # Make sure process_url is defined in downloader.py


# /txtdl command
@Client.on_message(filters.private & filters.command("txtdl") & filters.user(ADMIN))
async def txtdl(bot, msg):
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("❌ Please reply to a .txt file containing URLs.")
        return

    file = msg.reply_to_message.document
    if not file.file_name.lower().endswith(".txt"):
        await msg.reply_text("❌ The file must be a .txt file.")
        return

    file_path = os.path.join(DOWNLOAD_LOCATION, file.file_name)
    await bot.download_media(file, file_path)

    # Count valid URLs
    async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
        content = await f.read()
        entries = content.strip().split("\n\n")
        urls = []
        for entry in entries:
            url_match = re.search(r"url\s*-\s*'(https?://.*?)'", entry)
            if url_match:
                urls.append(url_match.group(1).strip())

    if not urls:
        await msg.reply_text("❌ No valid URLs found in the file.")
        return

    # Create range selection buttons
    step = 5  # number of URLs per range
    buttons = []
    for i in range(0, len(urls), step):
        start = i
        end = min(i + step, len(urls))
        buttons.append([InlineKeyboardButton(f"{start+1}-{end}", callback_data=f"txt_{start}_{end}_{file.file_name}")])

    # Add "Process All" button
    buttons.append([InlineKeyboardButton("⚡ Process All", callback_data=f"txt_0_{len(urls)}_{file.file_name}")])
    markup = InlineKeyboardMarkup(buttons)

    await msg.reply_text(
        f"📄 File processed. Total valid URLs: {len(urls)}\n\n"
        "🔹 Select the range of URLs to process:",
        reply_markup=markup
    )


# -----------------------
# Callback handler for range selection / process all
# -----------------------
@Client.on_callback_query(filters.regex(r'^txt_\d+_\d+_'))
async def txt_range_callback(bot, query):
    data = query.data.split('_')
    start, end, file_name = int(data[1]), int(data[2]), '_'.join(data[3:])
    file_path = os.path.join(DOWNLOAD_LOCATION, file_name)

    # Read URLs and titles again
    urls = []
    titles = []
    async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
        content = await f.read()
        entries = content.strip().split("\n\n")
        for entry in entries:
            title_match = re.search(r"title\s*-\s*'(.*?)'", entry)
            url_match = re.search(r"url\s*-\s*'(https?://.*?)'", entry)
            if title_match and url_match:
                titles.append(title_match.group(1).strip())
                urls.append(url_match.group(1).strip())

    if not urls:
        await query.message.edit_text("❌ No valid URLs found.")
        return

    # Slice the selected range
    selected_urls = urls[start:end]
    selected_titles = titles[start:end]

    # Pass each URL & title to downloader.py to handle like normal
    for title, url in zip(selected_titles, selected_urls):
        try:
            await downloader.process_url(bot, query.message.chat.id, url, title)
        except Exception as e:
            await bot.send_message(query.message.chat.id, f"❌ Error processing URL:\n{url}\n{str(e)}")

    await query.answer(f"✅ Processing URLs {start+1}-{end}")
    await query.message.delete()
