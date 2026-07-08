import time
import os
import re
import zipfile
import asyncio

import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message

from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


# ─────────────────────────────────────────────
# State: track pending zip-name replies
# ─────────────────────────────────────────────
_pending_zip = {}   # user_id → list of downloaded file paths


# ─────────────────────────────────────────────
# /backtxt  – move this file back to root
# ─────────────────────────────────────────────
import shutil

@Client.on_message(filters.private & filters.command("backtxt") & filters.user(ADMIN))
async def backtxt_command(bot, msg):
    src  = "/content/Simple-Rename-Bot/main/downloader/txtdl.py"
    dest = "/content/Simple-Rename-Bot/txtdl.py"
    if not os.path.exists(src):
        return await msg.reply_text(f"❌ File not found at:\n`{src}`")
    try:
        shutil.move(src, dest)
        await msg.reply_text(f"✅ Moved!\n\n`{src}`\n➡️ `{dest}`")
    except Exception as e:
        await msg.reply_text(f"❌ Move failed:\n`{e}`")


# ─────────────────────────────────────────────
# /txtdl  – reply to a .txt file
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("txtdl") & filters.user(ADMIN))
async def txtdl_command(bot, msg):
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
        return await sts.edit("❌ No URLs found in the TXT file.\nExpected format: `url - 'https://...'`")

    total = len(urls)
    await sts.edit(f"🎬 Found **{total} video(s)**. Starting downloads…")

    # ── Download loop ─────────────────────────
    MAX_RETRIES = 5
    downloaded_files = []
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

        fname = None
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            status_line = f"⬇️ Downloading **{index}/{total}**…\n`{url}`"
            if attempt > 1:
                status_line += f"\n🔄 Retry **{attempt - 1}/{MAX_RETRIES - 1}**…"
            try:
                await sts.edit(status_line)
            except Exception:
                pass

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
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

        if fname:
            downloaded_files.append(fname)
        else:
            # All retries exhausted → cancel
            for fp in downloaded_files:
                try:
                    os.remove(fp)
                except Exception:
                    pass
            try:
                if os.path.isdir(out_dir) and not os.listdir(out_dir):
                    os.rmdir(out_dir)
            except Exception:
                pass
            return await sts.edit(
                f"❌ **Cannot download this video** (failed after {MAX_RETRIES} retries):\n"
                f"`{url}`\n\n"
                f"⛔ **Process cancelled.**\n"
                f"Already downloaded **{len(downloaded_files)}/{total}** video(s) have been removed.\n\n"
                f"**Last error:**\n`{last_error}`"
            )

    # ── All done ──────────────────────────────
    filenames_text = "\n".join(f"  ✅ {os.path.basename(p)}" for p in downloaded_files)

    await sts.edit(
        f"✅ **{len(downloaded_files)}/{total} videos downloaded!**\n\n"
        f"{filenames_text}\n\n"
        f"📦 Please send the **ZIP filename** (without .zip) to package & upload."
    )

    _pending_zip[msg.from_user.id] = downloaded_files


# ─────────────────────────────────────────────
# Catch the zip-name reply
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def txtdl_zip_name(bot, msg):
    user_id = msg.from_user.id
    if user_id not in _pending_zip:
        return

    if msg.text.startswith("/"):
        return

    zip_name = msg.text.strip().replace(" ", "_")
    if not zip_name:
        return await msg.reply_text("❌ Invalid name. Send a plain filename (no spaces, no extension).")

    downloaded_files = _pending_zip.pop(user_id)
    zip_filename = f"{zip_name}.zip"
    zip_path = os.path.join(DOWNLOAD_LOCATION, zip_filename)

    sts = await msg.reply_text(f"📦 Creating **{zip_filename}**…")

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in downloaded_files:
                if os.path.exists(fp):
                    zf.write(fp, os.path.basename(fp))
    except Exception as e:
        return await sts.edit(f"❌ ZIP creation failed:\n`{e}`")

    zip_size = humanbytes(os.path.getsize(zip_path))

    await sts.edit(
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
                "Upload Started….. Thanks To All Who Supported ❤",
                sts,
                c_time,
            ),
        )
    except Exception as e:
        return await sts.edit(f"❌ Upload failed:\n`{e}`")

    try:
        os.remove(zip_path)
        for fp in downloaded_files:
            if os.path.exists(fp):
                os.remove(fp)
        tmp_dir = os.path.join(DOWNLOAD_LOCATION, "txtdl_tmp")
        if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
            os.rmdir(tmp_dir)
    except Exception as e:
        print(f"[txtdl] cleanup error: {e}")

    await sts.delete()
