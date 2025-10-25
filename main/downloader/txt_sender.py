import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------- SETTINGS --------------
SEND_INTERVAL = 10  # seconds between each URL send
# --------------------------------------

@Client.on_message(filters.command("txtsend") & filters.reply)
async def txt_send_handler(client, message):
    """Triggered when /txtsend is used as a reply to a TXT file."""
    replied = message.reply_to_message

    if not replied.document or not replied.document.file_name.endswith(".txt"):
        return await message.reply("❌ Please reply to a valid .txt file containing URLs.")

    # Download the txt file
    file_path = await replied.download()
    titles_urls = []

    # Parse the file (same format as your HTML script)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    for i in range(0, len(lines), 2):
        if lines[i].startswith("title - ") and lines[i + 1].startswith("url - "):
            title = lines[i].split("'", 1)[1].rsplit("'", 1)[0]
            url = lines[i + 1].split("'", 1)[1].rsplit("'", 1)[0]
            titles_urls.append((title, url))

    total = len(titles_urls)
    if total == 0:
        return await message.reply("⚠️ No valid URLs found in this TXT file.")

    # Create range buttons (10 items per range)
    buttons = []
    for start in range(0, total, 10):
        end = min(start + 10, total)
        buttons.append([
            InlineKeyboardButton(
                f"{start + 1} - {end}",
                callback_data=f"send_range|{start}|{end}|{file_path}"
            )
        ])

    # Add "Process All" button
    buttons.append([
        InlineKeyboardButton(f"Process All ({total})", callback_data=f"send_all|{file_path}")
    ])

    await message.reply(
        f"📄 Total URLs found: <b>{total}</b>\nSelect a range to process:",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )


@Client.on_callback_query(filters.regex(r"^(send_range|send_all)\|"))
async def process_selected_range(client, callback_query):
    """Handles range selection and sends URLs to the bot with a delay."""
    data = callback_query.data.split("|")
    action = data[0]

    # Delete the message with buttons
    await callback_query.message.delete()

    if action == "send_all":
        file_path = data[1]
        start, end = 0, None
    else:
        start = int(data[1])
        end = int(data[2])
        file_path = data[3]

    # Re-read the file
    titles_urls = []
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    for i in range(0, len(lines), 2):
        if lines[i].startswith("title - ") and lines[i + 1].startswith("url - "):
            title = lines[i].split("'", 1)[1].rsplit("'", 1)[0]
            url = lines[i + 1].split("'", 1)[1].rsplit("'", 1)[0]
            titles_urls.append((title, url))

    if end is None:
        selected = titles_urls
    else:
        selected = titles_urls[start:end]

    await callback_query.answer(f"Processing {len(selected)} URLs...", show_alert=False)

    # Send each URL with 10 sec gap
    for idx, (title, url) in enumerate(selected, start=1):
        await client.send_message(callback_query.message.chat.id, url)
        await asyncio.sleep(SEND_INTERVAL)

    await client.send_message(
        callback_query.message.chat.id,
        f"✅ Done! Sent {len(selected)} URLs successfully."
    )

    # Clean up downloaded file
    if os.path.exists(file_path):
        os.remove(file_path)
