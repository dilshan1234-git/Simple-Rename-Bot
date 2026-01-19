import re
from main.utils import progress_message

# rclone example line:
# Transferred:   	   1.234 GiB / 5.000 GiB, 25%, 3.2 MiB/s, ETA 21m10s
PROGRESS_REGEX = re.compile(
    r"Transferred:\s+.*?([\d.]+)\s*([KMGTP]iB)\s*/\s*([\d.]+)\s*([KMGTP]iB),\s*(\d+)%"
)

MULTIPLIERS = {
    "KiB": 1024,
    "MiB": 1024 ** 2,
    "GiB": 1024 ** 3,
    "TiB": 1024 ** 4
}


def to_bytes(value, unit):
    return int(float(value) * MULTIPLIERS[unit])


async def mega_progress(line, text, message, start_time):
    """
    Convert rclone upload progress into the same style as Telegram download progress
    using progress_message(current, total, text, message, start_time)
    """
    match = PROGRESS_REGEX.search(line)
    if not match:
        return

    current_val = match.group(1)
    current_unit = match.group(2)
    total_val = match.group(3)
    total_unit = match.group(4)

    current = to_bytes(current_val, current_unit)
    total = to_bytes(total_val, total_unit)

    await progress_message(current, total, text, message, start_time)
