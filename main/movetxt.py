import shutil
import os
import sys
import importlib

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ADMIN


# ─────────────────────────────────────────────
# /movetxt  – move txtdl.py into main/ folder
#             then restart the bot to load it
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("movetxt") & filters.user(ADMIN))
async def movetxt_command(bot: Client, msg: Message):
    src  = "/content/Simple-Rename-Bot/txtdl.py"
    dest = "/content/Simple-Rename-Bot/main/txtdl.py"

    if not os.path.exists(src):
        return await msg.reply_text(f"❌ File not found at:\n`{src}`")

    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
    except Exception as e:
        return await msg.reply_text(f"❌ Move failed:\n`{e}`")

    await msg.reply_text(
        f"✅ Moved!\n\n`{src}`\n➡️ `{dest}`\n\n"
        f"🔄 Restarting bot to activate `/txtdl`…"
    )

    # Restart the bot process so Pyrogram re-scans main/ and loads txtdl.py
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ─────────────────────────────────────────────
# /backtxt  – move txtdl.py back to root
#             then restart
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("backtxt") & filters.user(ADMIN))
async def backtxt_command(bot: Client, msg: Message):
    src  = "/content/Simple-Rename-Bot/main/downloader/txtdl.py"
    dest = "/content/Simple-Rename-Bot/txtdl.py"

    if not os.path.exists(src):
        return await msg.reply_text(f"❌ File not found at:\n`{src}`")

    try:
        shutil.move(src, dest)
    except Exception as e:
        return await msg.reply_text(f"❌ Move failed:\n`{e}`")

    await msg.reply_text(
        f"✅ Moved back!\n\n`{src}`\n➡️ `{dest}`\n\n"
        f"🔄 Restarting bot to deactivate `/txtdl`…"
    )

    os.execv(sys.executable, [sys.executable] + sys.argv)
