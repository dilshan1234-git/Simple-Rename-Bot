import time
import os
import re
import zipfile

import yt_dlp
from pyrogram import Client, filters, enums
from pyrogram.types import Message

from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


# ─────────────────────────────────────────────
# State: track pending zip-name replies
# ─────────────────────────────────────────────
_pending_zip: dict[int, list[str]] = {}   # user_id → list of downloaded file paths


# ─────────────────────────────────────────────
# /txtdl  – reply to a .txt file
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("txtdl") & filters.user(ADMIN))
async def txtdl_command(bot: Client, msg: Message):
    reply = msg.reply_to_message
    if not reply or not reply.document:
        return await msg.reply_text(
            "❌ Please reply to a **.txt** file with /txtdl"
        )

    doc = reply.document
    if not doc.file_name.lower().endswith(".txt"):
        return await msg.reply_text(
            "❌ The replied file must be a **.txt** file."
        )

    # ── Download the txt ──────────────────────
    sts = await msg.reply_text("📥 Reading your TXT file…")
    txt_path = await reply.download(file_name=os.path.join(DOWNLOAD_LOCATION, doc.file_name))

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()
    os.remove(txt_path)

    urls = re.findall(r"url\s*-\s*'([^']+)'", content)
    if not urls:
        return await sts.edit("❌ No URLs found in the TXT file.\nExpected format:  `url - 'https://...'`")

    total = len(urls)
    await sts.edit(f"🎬 Found **{total} video(s)**. Starting downloads…")

    # ── Download loop ─────────────────────────
    downloaded_files: list[str] = []
    failed: list[str] = []

    for index, url in enumerate(urls, start=1):
        # Tell the user which video is being fetched
        try:
            await sts.edit(
                f"⬇️ Downloading **{index}/{total}**…\n"
                f"`{url}`"
            )
        except Exception:
            pass  # flood wait – just continue

        out_dir = os.path.join(DOWNLOAD_LOCATION, "txtdl_tmp")
        os.makedirs(out_dir, exist_ok=True)

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
            "quiet": False,       # progress shows in Colab log
            "no_warnings": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Resolve the actual filename yt-dlp wrote
                fname = ydl.prepare_filename(info)
                # yt-dlp may change extension after merge
                for ext in (".mp4", ".mkv", ".webm"):
                    candidate = os.path.splitext(fname)[0] + ext
                    if os.path.exists(candidate):
                        fname = candidate
                        break
                downloaded_files.append(fname)
        except Exception as e:
            print(f"[txtdl] ERROR on {url}: {e}")
            failed.append(url)

    # ── Summary ───────────────────────────────
    filenames_text = "\n".join(
        f"  ✅ {os.path.basename(p)}" for p in downloaded_files
    )
    fail_text = (
        ("\n\n❌ **Failed:**\n" + "\n".join(f"  • `{u}`" for u in failed))
        if failed else ""
    )

    if not downloaded_files:
        return await sts.edit(
            f"❌ All downloads failed.{fail_text}"
        )

    await sts.edit(
        f"✅ **{len(downloaded_files)}/{total} videos downloaded!**\n\n"
        f"{filenames_text}"
        f"{fail_text}\n\n"
        f"📦 Please send the **ZIP filename** (without .zip) to package & upload."
    )

    # Store paths so the next message (zip name) can pick them up
    _pending_zip[msg.from_user.id] = downloaded_files


# ─────────────────────────────────────────────
# Catch the zip-name reply
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def txtdl_zip_name(bot: Client, msg: Message):
    user_id = msg.from_user.id
    if user_id not in _pending_zip:
        return  # not our business

    # Ignore bot commands
    if msg.text.startswith("/"):
        return

    zip_name = msg.text.strip().replace(" ", "_")
    if not zip_name:
        return await msg.reply_text("❌ Invalid name. Send a plain filename (no spaces, no extension).")

    downloaded_files = _pending_zip.pop(user_id)
    zip_filename = f"{zip_name}.zip"
    zip_path = os.path.join(DOWNLOAD_LOCATION, zip_filename)

    sts = await msg.reply_text(f"📦 Creating **{zip_filename}**…")

    # ── Build ZIP ─────────────────────────────
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in downloaded_files:
                if os.path.exists(fp):
                    zf.write(fp, os.path.basename(fp))
    except Exception as e:
        return await sts.edit(f"❌ ZIP creation failed:\n`{e}`")

    zip_size = humanbytes(os.path.getsize(zip_path))

    # ── Upload ZIP (same style as rename.py) ──
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

    # ── Cleanup ───────────────────────────────
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
