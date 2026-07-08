import asyncio
import time
import os
import re
import zipfile
import shutil

import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


# ─────────────────────────────────────────────
# Shared safe_edit (same pattern as zip script)
# ─────────────────────────────────────────────
async def safe_edit(message: Message, new_text: str, **kwargs) -> Message:
    if message is None:
        return message
    try:
        current = message.text if getattr(message, "text", None) is not None else (message.caption or "")
    except Exception:
        current = ""
    if str(current).strip() == str(new_text).strip():
        return message
    try:
        return await message.edit_text(new_text, **kwargs)
    except Exception:
        try:
            return await message.edit_text(new_text + "\u200b", **kwargs)
        except Exception as e2:
            print("safe_edit failed:", e2)
            return message


# ─────────────────────────────────────────────
# State
# ─────────────────────────────────────────────
# user_id → {
#   "urls": [...],
#   "downloaded_files": [...],
#   "awaiting_zip_name": bool,
#   "sts": Message,
# }
_txtdl_state: dict[int, dict] = {}


# ─────────────────────────────────────────────
# /backtxt  – move this file back to root
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("backtxt") & filters.user(ADMIN))
async def backtxt_command(bot: Client, msg: Message):
    src  = "/content/Simple-Rename-Bot/main/txtdl.py"
    dest = "/content/Simple-Rename-Bot/txtdl.py"

    if not os.path.exists(src):
        return await msg.reply_text(f"❌ File not found at:\n`{src}`")
    try:
        shutil.move(src, dest)
        await msg.reply_text(
            f"✅ Moved successfully!\n\n`{src}`\n➡️ `{dest}`"
        )
    except Exception as e:
        await msg.reply_text(f"❌ Move failed:\n`{e}`")


# ─────────────────────────────────────────────
# /txtdl  – reply to a .txt file
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("txtdl") & filters.user(ADMIN))
async def txtdl_command(bot: Client, msg: Message):
    reply = msg.reply_to_message
    if not reply or not reply.document:
        return await msg.reply_text("❌ Please reply to a **.txt** file with /txtdl")

    doc = reply.document
    if not doc.file_name.lower().endswith(".txt"):
        return await msg.reply_text("❌ The replied file must be a **.txt** file.")

    sts = await msg.reply_text("📥 Reading your TXT file…")
    txt_path = await reply.download(file_name=os.path.join(DOWNLOAD_LOCATION, doc.file_name))

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()
    os.remove(txt_path)

    urls = re.findall(r"url\s*-\s*'([^']+)'", content)
    if not urls:
        return await safe_edit(
            sts,
            "❌ No URLs found in the TXT file.\nExpected format: `url - 'https://...'`"
        )

    total = len(urls)
    await safe_edit(sts, f"🎬 Found **{total} video(s)**. Starting downloads…")

    # ── Download loop ──────────────────────────────
    MAX_RETRIES = 5
    downloaded_files: list[str] = []
    out_dir = os.path.join(DOWNLOAD_LOCATION, "txtdl_tmp")
    os.makedirs(out_dir, exist_ok=True)

    for index, url in enumerate(urls, start=1):

        ydl_opts = {
            "format": (
                "bestvideo[vcodec^=avc1][height<=720]+bestaudio[acodec^=mp4a]/"
                "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                "best[ext=mp4]"
            ),
            "merge_output_format": "mp4",
            "paths": {"home": out_dir},
            "outtmpl": f"{index:03d}_%(title)s.%(ext)s",
            "continuedl": True,
            "noplaylist": True,
            "quiet": False,
            "no_warnings": False,
        }

        fname      = None
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            status_line = (
                f"⬇️ Downloading **{index}/{total}**…\n"
                f"`{url}`"
            )
            if attempt > 1:
                status_line += f"\n🔄 Retry **{attempt - 1}/{MAX_RETRIES - 1}**…"

            await safe_edit(sts, status_line)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info           = ydl.extract_info(url, download=True)
                    candidate_base = ydl.prepare_filename(info)
                    for ext in (".mp4", ".mkv", ".webm"):
                        candidate = os.path.splitext(candidate_base)[0] + ext
                        if os.path.exists(candidate):
                            fname = candidate
                            break
                break  # success

            except Exception as e:
                last_error = e
                print(f"[txtdl] attempt {attempt}/{MAX_RETRIES} failed for {url}: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(3)

        # ── Outcome ───────────────────────────────
        if fname:
            downloaded_files.append(fname)
        else:
            # Clean up and cancel
            for fp in downloaded_files:
                try:
                    if os.path.exists(fp):
                        os.remove(fp)
                except Exception:
                    pass
            try:
                if os.path.isdir(out_dir) and not os.listdir(out_dir):
                    os.rmdir(out_dir)
            except Exception:
                pass

            return await safe_edit(
                sts,
                f"❌ **Cannot download this video** (failed after {MAX_RETRIES} retries):\n"
                f"`{url}`\n\n"
                f"⛔ **Process cancelled.**\n"
                f"Already downloaded **{len(downloaded_files)}/{total}** video(s) have been removed.\n\n"
                f"**Last error:**\n`{last_error}`"
            )

    # ── All done – ask for ZIP name via inline button ──
    filenames_text = "\n".join(f"  ✅ {os.path.basename(p)}" for p in downloaded_files)

    _txtdl_state[msg.from_user.id] = {
        "downloaded_files": downloaded_files,
        "awaiting_zip_name": False,
        "sts": sts,
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Create ZIP", callback_data="txtdl_create_zip")],
        [InlineKeyboardButton("❌ Cancel",      callback_data="txtdl_cancel")],
    ])

    await safe_edit(
        sts,
        f"✅ **All {len(downloaded_files)}/{total} videos downloaded!**\n\n"
        f"{filenames_text}\n\n"
        f"Press **Create ZIP** then send the ZIP filename.",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────
# Inline: Create ZIP pressed
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex("txtdl_create_zip"))
async def txtdl_create_zip_cb(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in _txtdl_state:
        return await query.answer("Session expired. Run /txtdl again.", show_alert=True)

    _txtdl_state[user_id]["awaiting_zip_name"] = True

    await safe_edit(query.message, "🔤 **Please send the ZIP filename** (without .zip).")
    await query.answer()


# ─────────────────────────────────────────────
# Inline: Cancel pressed
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex("txtdl_cancel"))
async def txtdl_cancel_cb(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    state   = _txtdl_state.pop(user_id, {})

    for fp in state.get("downloaded_files", []):
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass

    await safe_edit(query.message, "❌ **Cancelled.** Downloaded files have been removed.")
    await query.answer()


# ─────────────────────────────────────────────
# Text handler: receive ZIP name
# Only fires when awaiting_zip_name is True
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def txtdl_zip_name(bot: Client, msg: Message):
    user_id = msg.from_user.id

    # Only handle if we're waiting for a zip name from this user
    state = _txtdl_state.get(user_id)
    if not state or not state.get("awaiting_zip_name"):
        return

    # Don't intercept other commands
    if msg.text.startswith("/"):
        return

    zip_name = msg.text.strip().replace(" ", "_")
    if not zip_name:
        return await msg.reply_text("❌ Invalid name. Please send a plain filename.")

    # Lock so further texts don't re-trigger
    state["awaiting_zip_name"] = False

    downloaded_files = state["downloaded_files"]
    sts              = state["sts"]
    zip_filename     = f"{zip_name}.zip"
    zip_path         = os.path.join(DOWNLOAD_LOCATION, zip_filename)

    # ── Build ZIP ─────────────────────────────
    await safe_edit(sts, f"📦 Creating **{zip_filename}**…")

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in downloaded_files:
                if os.path.exists(fp):
                    zf.write(fp, os.path.basename(fp))
    except Exception as e:
        _txtdl_state.pop(user_id, None)
        return await safe_edit(sts, f"❌ ZIP creation failed:\n`{e}`")

    zip_size = humanbytes(os.path.getsize(zip_path))

    # ── Upload ZIP ────────────────────────────
    await safe_edit(
        sts,
        f"🚀 Uploading started….. 📤 Thanks To All Who Supported ❤\n"
        f"📦 **{zip_filename}** | 💽 {zip_size}"
    )
    c_time = time.time()

    try:
        await bot.send_document(
            msg.chat.id,
            document=zip_path,
            caption=(
                f"📦 **{zip_filename}**\n\n"
                f"💽 Size: {zip_size}\n"
                f"🎬 Videos: {len(downloaded_files)}"
            ),
            progress=progress_message,
            progress_args=(
                f"📤 Uploading ZIP…\n\n**📦 {zip_filename}**",
                sts,
                c_time,
            ),
        )
    except Exception as e:
        _txtdl_state.pop(user_id, None)
        return await safe_edit(sts, f"❌ Upload failed:\n`{e}`")

    # ── Cleanup ───────────────────────────────
    _txtdl_state.pop(user_id, None)

    try:
        os.remove(zip_path)
    except Exception:
        pass
    for fp in downloaded_files:
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
    try:
        tmp_dir = os.path.join(DOWNLOAD_LOCATION, "txtdl_tmp")
        if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
            os.rmdir(tmp_dir)
    except Exception:
        pass

    await sts.delete()
