import re
import time
from main.utils import progress_message
from pyrogram.errors import MessageNotModified

# Matches rclone stats lines like:
# 2.625 MiB / 422.221 MiB, 1%, 2.625 MiB/s, ETA 2m39s
PROGRESS_REGEX = re.compile(
    r"([\d.]+)\s*(KiB|MiB|GiB|TiB)\s*/\s*([\d.]+)\s*(KiB|MiB|GiB|TiB),\s*(\d+)%"
)

MULTIPLIERS = {
    "KiB": 1024,
    "MiB": 1024 ** 2,
    "GiB": 1024 ** 3,
    "TiB": 1024 ** 4
}

_last_update = 0
_last_percent = -1  # track last percent sent to Telegram


def to_bytes(value, unit):
    return int(float(value) * MULTIPLIERS[unit])


async def mega_progress(line, text, message, start_time):
    """
    Converts rclone progress lines into Telegram style progress_message()
    same UI as downloading progress.
    """

    global _last_update, _last_percent

    match = PROGRESS_REGEX.search(line)
    if not match:
        return

    current_val = match.group(1)
    current_unit = match.group(2)
    total_val = match.group(3)
    total_unit = match.group(4)
    percent = int(match.group(5))  # round to integer

    # Only update if percent changed
    if percent == _last_percent:
        return
    _last_percent = percent

    current = to_bytes(current_val, current_unit)
    total = to_bytes(total_val, total_unit)

    # Limit edits to once per second
    now = time.time()
    if now - _last_update < 1:
        return
    _last_update = now

    try:
        await progress_message(current, total, text, message, start_time)
    except MessageNotModified:
        pass
    except:
        pass
