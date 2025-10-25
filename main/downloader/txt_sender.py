import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------- SETTINGS --------------
SEND_INTERVAL = 10  # seconds between each URL send
RANGE_SIZE = 10     # number of items per range
# --------------------------------------

@Client.on_message(filters.command("txtsend") & filters.reply)
async def txt_send_handler(client, message):
    """Triggered when /txtsend is used as a reply to a TXT file."""
    replied = message.reply_to_message

    if not replied or not replied.document or not replied.document.file_name.endswith(".txt"):
        return await message.reply("❌ Please reply to a valid .txt file containing titles and URLs.")

    # Download TXT file
    file_path = await replied.download()
    titles_urls = []

    # Parse TXT file
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    for i in range(0, len(lines) - 1, 2):
        if lines[i].startswith("title - ") and lines[i + 1].startswith("url - "):
            try:
                title = lines[i].split("'", 1)[1].rsplit("'", 1)[0]
                url = lines[i + 1].split("'", 1)[1].rsplit("'", 1)[0]
                titles_urls.append((title, url))
            except IndexError:
                continue

    total = len(titles_urls)
    if total == 0:
        os.remove(file_path)
        return await message.reply("⚠️ No valid titles and URLs found in this TXT file.")

    # Create range selection buttons
    buttons = []
    for start in range(0, total, RANGE_SIZE):
        end = min(start + RANGE_SIZE, total)
        buttons.append([
            InlineKeyboardButton(
                f"{start + 1} - {end}",
                callback_data=f"send_range|{start}|{end}|{file_path}"
            )
        ])

    # Add process all button
    buttons.append([
        InlineKeyboardButton(f"📦 Process All ({total})", callback_data=f"send_all|{file_path}")
    ])

    await message.reply(
        f"✅ Found <b>{total}</b> URLs in this TXT file.\nSelect a range to process:",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )


@Client.on_callback_query(filters.regex(r"^(send_range|send_all)\|"))
async def process_selected_range(client, callback_query):
    """Handles range selection and silently sends URLs one by one."""
    data = callback_query.data.split("|")
    action = data[0]
    await callback_query.message.delete()  # Delete range message immediately

    # Extract info
    if action == "send_all":
        file_path = data[1]
        start, end = 0, None
    else:
        start = int(data[1])
        end = int(data[2])
        file_path = data[3]

    if not os.path.exists(file_path):
        return

    # Parse TXT file again
    titles_urls = []
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    for i in range(0, len(lines) - 1, 2):
        if lines[i].startswith("title - ") and lines[i + 1].startswith("url - "):
            try:
                title = lines[i].split("'", 1)[1].rsplit("'", 1)[0]
                url = lines[i + 1].split("'", 1)[1].rsplit("'", 1)[0]
                titles_urls.append((title, url))
            except IndexError:
                continue

    # Select range or all
    selected = titles_urls if end is None else titles_urls[start:end]

    # Send URLs silently with delay
    for _, url_pair in enumerate(selected, start=1):
        url = url_pair[1]
        try:
            await client.send_message(callback_query.message.chat.id, url)
            await asyncio.sleep(SEND_INTERVAL)
        except Exception as e:
            print(f"Error sending URL: {e}")
            continue

    # Cleanup TXT file
    if os.path.exists(file_path):
        os.remove(file_path)
