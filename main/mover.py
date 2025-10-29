import shutil
import os
from pyrogram import Client, filters
from config import ADMIN
from IPython.display import display, Javascript

# Paths
ARCHIVE_EXTRACTOR_SRC = "/content/Simple-Rename-Bot/archive_extractor.py"
ARCHIVE_EXTRACTOR_DEST = "/content/Simple-Rename-Bot/main/archive_extractor.py"


@Client.on_message(filters.private & filters.command("move")
                   & filters.user(ADMIN))
async def move_archive_extractor(bot, msg):
    # Move archive_extractor.py to the main directory
    if os.path.exists(ARCHIVE_EXTRACTOR_SRC):
        shutil.move(ARCHIVE_EXTRACTOR_SRC, ARCHIVE_EXTRACTOR_DEST)
        await msg.reply_text(f"📁 `archive_extractor.py` has been moved to {ARCHIVE_EXTRACTOR_DEST}.")

        # Stop the current running cell and restart
        await stop_and_rerun()


async def stop_and_rerun():
    # Stop the current cell and trigger a rerun
    display(Javascript('IPython.notebook.kernel.restart();'))

    # Alternatively, you can raise SystemExit to stop the current cell
    # raise SystemExit("Stopping current cell to rerun.")

    # If you're not in Colab, use the following to exit the script:
    # os._exit(0)
