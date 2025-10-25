import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------- SETTINGS --------------
SEND_INTERVAL = 10   # seconds between each URL send
RANGE_SIZE = 10      # number of items per range
# --------------------------------------

TEMP_FILES = {}  # temporary in-memory store for file paths


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

    # Assign short ID for this file
    file_id = str(len(TEMP_FILES) + 1)
    TEMP_FILES[file_id] = file_path

    # Create range selection buttons
    buttons = []
    for start in range(0, total, RANGE_SIZE):
        end = min(start + RANGE_SIZE, total)
        buttons.append([
            InlineKeyboardButton(
                f"{start + 1} - {end}",
                callback_data=f"send_range|{start}|{end}|{file_id}"
            )
        ])

    # Add "Process All" button
    buttons.append([
        InlineKeyboardButton(f"📦 Process All ({total})", callback_data=f"send_all|{file_id}")
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
    await callback_query.message.delete()  # Delete selection message

    file_id = data[-1]
    file_path = TEMP_FILES.get(file_id)

    if not file_path or not os.path.exists(file_path):
        return

    # Determine range
    if action == "send_all":
        start, end = 0, None
    else:
        start = int(data[1])
        end = int(data[2])

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

    selected = titles_urls if end is None else titles_urls[start:end]

    # Send URLs silently
    for _, url_pair in enumerate(selected, start=1):
        url = url_pair[1]
        try:
            await client.send_message(callback_query.message.chat.id, url)
            await asyncio.sleep(SEND_INTERVAL)
        except Exception as e:
            print(f"Error sending URL: {e}")
            continue

    # Clean up
    if os.path.exists(file_path):
        os.remove(file_path)
    TEMP_FILES.pop(file_id, None)
