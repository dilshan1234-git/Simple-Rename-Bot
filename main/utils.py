from pyrogram.types import *
import math
import os
import time

# Updated progress bar style
PROGRESS_BAR = (
    "\n╭━━━━❰ ᴘʀᴏɢʀᴇss ʙᴀʀ ❱━━━━━━━━━━➣\n"
    "┃\n"
    "┣ ⪼ [{bar}] {a}%\n"
    "┃\n"
    "┣ ⪼ 🗃️ **Sɪᴢᴇ: {b} | {c}**\n"
    "┃\n"
    "┣ ⪼ ⚡ **Dᴏɴᴇ: {a}%**\n"
    "┃\n"
    "┣ ⪼ 🚀 **Sᴩᴇᴇᴅ: {d}/s**\n"
    "┃\n"
    "┣ ⪼ ⏰️ **Eᴛᴀ: {f}**\n"
    "╰━━━━━━━━━━━━━━━➣"
)

# Function to generate a gradient-style progress bar


def generate_progress_bar(percentage, length=20):
    filled_length = int(length * percentage // 100)
    bar = ''.join(
        ['▓' if i < filled_length else '░' for i in range(length)]
    )
    return bar


# Store last update time per message to prevent spam
message_update_times = {}


async def progress_message(current, total, ud_type, message, start):
    now = time.time()
    diff = now - start

    # Get message identifier for tracking
    msg_id = f"{message.chat.id}_{message.id}" if hasattr(
        message, 'id') else str(
        id(message))

    # More frequent updates - every 1 second instead of 10
    if msg_id in message_update_times:
        time_since_last = now - message_update_times[msg_id]
        if time_since_last < 1.0 and current != total:  # Update every 1 second
            return

    message_update_times[msg_id] = now

    # Avoid division by zero
    if diff <= 0:
        diff = 0.1

    percentage = current * 100 / total if total > 0 else 0
    speed = current / diff

    # More accurate ETA calculation
    if speed > 0:
        remaining_bytes = total - current
        eta_seconds = remaining_bytes / speed
        estimated_total_time = TimeFormatter(int(eta_seconds * 1000))
    else:
        estimated_total_time = "Calculating..."

    # Elapsed time
    elapsed_time = TimeFormatter(int(diff * 1000))

    # Generate progress bar
    bar = generate_progress_bar(percentage)

    # Format the progress message
    tmp = PROGRESS_BAR.format(
        bar=bar,
        a=round(percentage, 1),  # More precision for faster updates
        b=humanbytes(current),
        c=humanbytes(total),
        d=humanbytes(speed),
        f=estimated_total_time if estimated_total_time != '' else "0 s"
    )

    try:
        # Cancel button
        chance = [[InlineKeyboardButton("🚫 Cancel", callback_data="del")]]

        # Try to update the message
        full_text = "{}\n{}".format(ud_type, tmp)

        if hasattr(message, 'edit'):
            await message.edit(text=full_text, reply_markup=InlineKeyboardMarkup(chance))
        elif hasattr(message, 'edit_text'):
            await message.edit_text(full_text, reply_markup=InlineKeyboardMarkup(chance))
        elif hasattr(message, 'edit_caption'):
            await message.edit_caption(caption=full_text, reply_markup=InlineKeyboardMarkup(chance))

    except Exception as e:
        # Handle rate limiting more gracefully
        if "Too Many Requests" in str(e) or "FLOOD_WAIT" in str(e):
            # Increase update interval for this message
            message_update_times[msg_id] = now + 2  # Wait 2 extra seconds
        pass


def humanbytes(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])


def TimeFormatter(milliseconds: int) -> str:
    if milliseconds <= 0:
        return "0s"

    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    # More readable format for shorter times
    if days:
        return f"{days}d {hours}h {minutes}m"
    elif hours:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"
