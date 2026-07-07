import shutil
import os

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ADMIN


# ─────────────────────────────────────────────
# /movetxt  – move txtdl.py into main/ folder
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("movetxt") & filters.user(ADMIN))
async def movetxt_command(bot: Client, msg: Message):
    src  = "/content/Simple-Rename-Bot/txtdl.py"
    dest = "/content/Simple-Rename-Bot/main/txtdl.py"

    if not os.path.exists(src):
        return await msg.reply_text(
            f"❌ File not found at:\n`{src}`"
        )

    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        await msg.reply_text(
            f"✅ Moved successfully!\n\n"
            f"`{src}`\n➡️ `{dest}`"
        )
    except Exception as e:
        await msg.reply_text(f"❌ Move failed:\n`{e}`")
