import os
import time
import shutil
import asyncio
import zipfile

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


GENSUB_FOLDER = os.path.join(
    DOWNLOAD_LOCATION,
    "gensub"
)

os.makedirs(GENSUB_FOLDER, exist_ok=True)


# Stores pending confirmations
pending_gensub = {}


# ============================================================
# HELPERS
# ============================================================

def format_timestamp(seconds):

    milliseconds = int(
        (seconds - int(seconds)) * 1000
    )

    hours = int(seconds // 3600)

    minutes = int(
        (seconds % 3600) // 60
    )

    seconds = int(seconds % 60)

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{seconds:02},"
        f"{milliseconds:03}"
    )


def get_video_files(folder):

    extensions = (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".webm",
        ".m4v"
    )

    return sorted(
        [
            file
            for file in os.listdir(folder)
            if os.path.isfile(
                os.path.join(folder, file)
            )
            and file.lower().endswith(extensions)
        ]
    )


def generate_subtitle(video_path, srt_path):

    from faster_whisper import WhisperModel

    model = WhisperModel(
        "small",
        device="cuda",
        compute_type="float16"
    )

    segments, info = model.transcribe(
        video_path,
        task="translate",
        beam_size=5
    )

    with open(
        srt_path,
        "w",
        encoding="utf-8"
    ) as file:

        for number, segment in enumerate(
            segments,
            start=1
        ):

            start = format_timestamp(
                segment.start
            )

            end = format_timestamp(
                segment.end
            )

            text = segment.text.strip()

            file.write(
                f"{number}\n"
            )

            file.write(
                f"{start} --> {end}\n"
            )

            file.write(
                f"{text}\n\n"
            )


# ============================================================
# /GENSUB
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("gensub")
    & filters.user(ADMIN)
)
async def gensub_file(bot, msg):

    reply = msg.reply_to_message

    if not reply:

        return await msg.reply_text(
            "⚠️ **Please reply to a ZIP file.**\n\n"
            "Example:\n"
            "`Reply to ZIP → /gensub`"
        )

    media = reply.document

    if not media:

        return await msg.reply_text(
            "⚠️ **Please reply to a ZIP file.**"
        )

    zip_name = media.file_name or "Unknown.zip"

    if not zip_name.lower().endswith(".zip"):

        return await msg.reply_text(
            "⚠️ **Please reply to a ZIP file.**"
        )

    size = humanbytes(media.file_size)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data="gensub_yes"
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="gensub_no"
                )
            ]
        ]
    )

    text = (
        f"<b>📦 {zip_name}</b>\n\n"
        f"💾 <b>Size:</b> {size}\n"
        f"📂 <b>Files:</b> Checking after download\n\n"
        "🇮🇳 Hindi → 🇬🇧 English\n"
        "📝 Generate SRT subtitles\n\n"
        "Do you want to continue?"
    )

    confirmation = await msg.reply_text(
        text,
        reply_markup=keyboard
    )

    pending_gensub[confirmation.id] = {
        "reply": reply,
        "zip_name": zip_name,
        "file_size": media.file_size
    }


# ============================================================
# CANCEL
# ============================================================

@Client.on_callback_query(
    filters.regex("^gensub_no$")
)
async def gensub_cancel(bot, query):

    await query.answer("Cancelled")

    pending_gensub.pop(
        query.message.id,
        None
    )

    await query.message.edit_text(
        "❌ <b>Process Cancelled</b>\n\n"
        "Nothing was downloaded or processed."
    )


# ============================================================
# CONFIRM
# ============================================================

@Client.on_callback_query(
    filters.regex("^gensub_yes$")
)
async def gensub_confirm(bot, query):

    await query.answer()

    data = pending_gensub.pop(
        query.message.id,
        None
    )

    if not data:

        return await query.message.edit_text(
            "❌ <b>Request expired.</b>"
        )

    reply = data["reply"]

    zip_name = data["zip_name"]

    safe_name = os.path.splitext(
        zip_name
    )[0]

    work_dir = os.path.join(
        GENSUB_FOLDER,
        safe_name
    )

    os.makedirs(
        work_dir,
        exist_ok=True
    )

    zip_path = os.path.join(
        work_dir,
        zip_name
    )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    await query.message.edit_text(
        "🗑️ <b>Removing current information...</b>"
    )

    await asyncio.sleep(1)

    await query.message.edit_text(
        f"📥 <b>Downloading ZIP</b>\n\n"
        f"📦 <b>{zip_name}</b>"
    )

    c_time = time.time()

    await reply.download(
        file_name=zip_path,
        progress=progress_message,
        progress_args=(
            f"📥 Downloading • {zip_name}",
            query.message,
            c_time
        )
    )

    # ========================================================
    # DOWNLOAD COMPLETE
    # ========================================================

    with zipfile.ZipFile(
        zip_path,
        "r"
    ) as zip_file:

        file_names = zip_file.namelist()

    await query.message.edit_text(
        f"✅ <b>Download Completed</b>\n\n"
        f"📦 <b>{zip_name}</b>\n"
        f"💾 <b>Size:</b> "
        f"{humanbytes(os.path.getsize(zip_path))}\n"
        f"📂 <b>Files:</b> {len(file_names)}"
    )

    # ========================================================
    # EXTRACT
    # ========================================================

    await asyncio.sleep(2)

    await query.message.edit_text(
        f"📂 <b>Preparing files...</b>\n\n"
        f"📦 {zip_name}"
    )

    with zipfile.ZipFile(
        zip_path,
        "r"
    ) as zip_file:

        zip_file.extractall(work_dir)

    videos = get_video_files(work_dir)

    if not videos:

        return await query.message.edit_text(
            "❌ <b>No supported video files found.</b>"
        )

    await query.message.edit_text(
        f"🎬 <b>Starting subtitle generation...</b>\n\n"
        f"📂 {len(videos)} video files found\n"
        f"🇮🇳 Hindi → 🇬🇧 English"
    )

    await asyncio.sleep(10)

    # ========================================================
    # PROCESS FILES
    # ========================================================

    processed = []

    for index, video_name in enumerate(
        videos,
        start=1
    ):

        video_path = os.path.join(
            work_dir,
            video_name
        )

        title = os.path.splitext(
            video_name
        )[0]

        srt_path = os.path.join(
            work_dir,
            f"{title}.srt"
        )

        await query.message.edit_text(
            f"🎙️ <b>Generating subtitles</b>\n\n"
            f"📂 <b>File:</b> {video_name}\n\n"
            f"📊 <b>Progress:</b> "
            f"{index}/{len(videos)}\n\n"
            f"🇮🇳 Hindi → 🇬🇧 English\n"
            f"⏳ Processing..."
        )

        # Whisper is CPU/GPU heavy.
        # Run it outside the async event loop.
        await asyncio.to_thread(
            generate_subtitle,
            video_path,
            srt_path
        )

        processed.append(
            video_name
        )

        # ====================================================
        # SUBTITLE CREATED
        # ====================================================

        await query.message.edit_text(
            f"📝 <b>Subtitle Generated</b>\n\n"
            f"🎬 <b>{video_name}</b>\n"
            f"📄 <b>{title}.srt</b>\n\n"
            f"✅ <b>Processed:</b> "
            f"{len(processed)}/{len(videos)}"
        )

        # ====================================================
        # UPLOAD SRT
        # ====================================================

        await asyncio.sleep(1)

        upload_message = await query.message.edit_text(
            f"📤 <b>Uploading Subtitle</b>\n\n"
            f"📄 <b>{title}.srt</b>"
        )

        c_time = time.time()

        await bot.send_document(
            query.message.chat.id,
            document=srt_path,
            file_name=f"{title}.srt",
            progress=progress_message,
            progress_args=(
                f"📤 Uploading • {title}.srt",
                upload_message,
                c_time
            )
        )

        # Delete upload progress message
        try:
            await upload_message.delete()
        except:
            pass

        # ====================================================
        # PROCESSED INFORMATION
        # ====================================================

        processed_text = "\n".join(
            f"✅ {name}"
            for name in processed
        )

        await query.message.edit_text(
            f"🎉 <b>Subtitle Sent</b>\n\n"
            f"📄 <b>{title}.srt</b>\n\n"
            f"📊 <b>Processed:</b> "
            f"{len(processed)}/{len(videos)}\n\n"
            f"<b>Completed Files:</b>\n"
            f"{processed_text}"
        )

        # ====================================================
        # WAIT 30 SECONDS BEFORE NEXT FILE
        # ====================================================

        if index < len(videos):

            for remaining in range(
                30,
                0,
                -1
            ):

                await query.message.edit_text(
                    f"⏳ <b>Next Subtitle Generation</b>\n\n"
                    f"✅ <b>Processed:</b> "
                    f"{len(processed)}/{len(videos)}\n\n"
                    f"<b>Completed Files:</b>\n"
                    f"{processed_text}\n\n"
                    f"🚀 Starting next file in "
                    f"<b>{remaining}s</b>..."
                )

                await asyncio.sleep(1)

    # ========================================================
    # ALL COMPLETE
    # ========================================================

    processed_text = "\n".join(
        f"✅ {name}"
        for name in processed
    )

    await query.message.edit_text(
        f"🎊 <b>All Files Processed!</b>\n\n"
        f"📂 <b>Total:</b> {len(processed)}\n"
        f"📝 <b>Subtitles generated:</b> "
        f"{len(processed)}\n\n"
        f"<b>Processed Files:</b>\n"
        f"{processed_text}\n\n"
        f"✨ <b>Everything is complete!</b>"
    )

    # ========================================================
    # CLEANUP
    # ========================================================

    try:
        shutil.rmtree(work_dir)
    except Exception as e:
        print(
            f"GENSUB cleanup error: {e}"
        )
