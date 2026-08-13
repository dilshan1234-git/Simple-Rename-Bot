import os
import time
import uuid
import shutil
import zipfile
import asyncio
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes


# ============================================================
# SETTINGS
# ============================================================

GENSUB_ROOT = os.path.join(
    DOWNLOAD_LOCATION,
    "gensub_tmp"
)

os.makedirs(GENSUB_ROOT, exist_ok=True)


# ============================================================
# PENDING CONFIRMATIONS
# ============================================================

_pending_gensub = {}


# ============================================================
# WHISPER MODEL
# Loaded only once and reused for every episode
# ============================================================

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def get_whisper_model():

    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    async with _whisper_lock:

        if _whisper_model is not None:
            return _whisper_model

        def load_model():

            from faster_whisper import WhisperModel

            try:
                import torch

                if torch.cuda.is_available():

                    print(
                        "[GENSUB] NVIDIA GPU detected:",
                        torch.cuda.get_device_name(0)
                    )

                    return WhisperModel(
                        "small",
                        device="cuda",
                        compute_type="float16"
                    )

            except Exception as e:

                print(
                    f"[GENSUB] GPU detection failed: {e}"
                )

            print(
                "[GENSUB] Using CPU for Faster-Whisper."
            )

            return WhisperModel(
                "small",
                device="cpu",
                compute_type="int8"
            )

        _whisper_model = await asyncio.to_thread(
            load_model
        )

    return _whisper_model


# ============================================================
# SAFE MESSAGE EDIT
# Same idea as your txtdl.py
# ============================================================

async def _edit(sts, text):

    try:
        await sts.edit(text)

    except Exception as e:

        print(
            f"[GENSUB] Message edit error: {e}"
        )


# ============================================================
# SAFE FILE NAME
# ============================================================

def safe_filename(filename):

    filename = os.path.basename(
        filename or "file"
    )

    invalid = '<>:"/\\|?*'

    for char in invalid:
        filename = filename.replace(
            char,
            "_"
        )

    return filename.strip() or "file"


# ============================================================
# VIDEO EXTENSIONS
# ============================================================

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".m4v",
    ".flv",
    ".ts"
}


# ============================================================
# FIND VIDEOS
# ============================================================

def get_video_files(folder):

    videos = []

    for root, dirs, files in os.walk(folder):

        for filename in files:

            path = os.path.join(
                root,
                filename
            )

            if Path(filename).suffix.lower() in VIDEO_EXTENSIONS:

                videos.append(path)

    return sorted(
        videos,
        key=lambda x: os.path.basename(x).lower()
    )


# ============================================================
# SAFE ZIP EXTRACTION
# ============================================================

def safe_extract_zip(zip_path, extract_to):

    extract_to = os.path.abspath(
        extract_to
    )

    extracted_count = 0

    with zipfile.ZipFile(
        zip_path,
        "r"
    ) as zip_file:

        for member in zip_file.infolist():

            member_name = member.filename

            if not member_name:
                continue

            # Convert ZIP separators
            member_name = member_name.replace(
                "\\",
                "/"
            )

            # Prevent absolute paths
            if member_name.startswith("/"):

                raise ValueError(
                    "Unsafe ZIP path detected."
                )

            target = os.path.abspath(
                os.path.join(
                    extract_to,
                    member_name
                )
            )

            # Prevent ../ traversal
            if (
                target != extract_to
                and not target.startswith(
                    extract_to + os.sep
                )
            ):

                raise ValueError(
                    "Unsafe ZIP path detected."
                )

            if member.is_dir():
                os.makedirs(
                    target,
                    exist_ok=True
                )
                continue

            os.makedirs(
                os.path.dirname(target),
                exist_ok=True
            )

            with zip_file.open(
                member,
                "r"
            ) as source:

                with open(
                    target,
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            extracted_count += 1

    return extracted_count


# ============================================================
# SRT TIMESTAMP
# ============================================================

def format_timestamp(seconds):

    milliseconds = int(
        (seconds - int(seconds)) * 1000
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (seconds % 3600) // 60
    )

    seconds = int(
        seconds % 60
    )

    return (
        f"{hours:02}:"
        f"{minutes:02}:"
        f"{seconds:02},"
        f"{milliseconds:03}"
    )


# ============================================================
# GENERATE SUBTITLE
#
# Runs in a background thread so Whisper doesn't block
# the Pyrogram event loop.
# ============================================================

def generate_subtitle_sync(
    model,
    video_path,
    srt_path,
    progress_callback=None
):

    segments, info = model.transcribe(
        video_path,
        task="translate",
        beam_size=5
    )

    segment_count = 0

    last_update = 0

    with open(
        srt_path,
        "w",
        encoding="utf-8"
    ) as file:

        for segment in segments:

            segment_count += 1

            start = format_timestamp(
                segment.start
            )

            end = format_timestamp(
                segment.end
            )

            text = segment.text.strip()

            file.write(
                f"{segment_count}\n"
            )

            file.write(
                f"{start} --> {end}\n"
            )

            file.write(
                f"{text}\n\n"
            )

            # Don't call Telegram for every segment.
            # Throttle updates.
            now = time.time()

            if (
                progress_callback
                and now - last_update >= 2
            ):

                last_update = now

                progress_callback(
                    segment.end,
                    segment_count
                )

    return {
        "language": info.language,
        "segments": segment_count
    }


# ============================================================
# GENERATION PROGRESS BRIDGE
# ============================================================

async def generate_subtitle(
    model,
    video_path,
    srt_path,
    status_message,
    current_index,
    total_files,
    filename
):

    loop = asyncio.get_running_loop()

    last_update = {
        "time": 0
    }

    def progress_callback(
        current_seconds,
        segment_count
    ):

        now = time.time()

        # Throttle Telegram updates
        if now - last_update["time"] < 2:
            return

        last_update["time"] = now

        minutes = int(
            current_seconds // 60
        )

        seconds = int(
            current_seconds % 60
        )

        text = (
            f"🎙️ <b>Generating Subtitles</b>\n\n"
            f"🎬 <b>File:</b>\n"
            f"<code>{filename}</code>\n\n"
            f"📊 <b>File:</b> "
            f"{current_index}/{total_files}\n"
            f"⏱️ <b>Subtitle position:</b> "
            f"{minutes:02}:{seconds:02}\n"
            f"📝 <b>Segments:</b> "
            f"{segment_count}\n\n"
            f"🇮🇳 Hindi → 🇬🇧 English\n"
            f"⚙️ <b>Whisper is processing...</b>"
        )

        asyncio.run_coroutine_threadsafe(
            _edit(
                status_message,
                text
            ),
            loop
        )

    result = await asyncio.to_thread(
        generate_subtitle_sync,
        model,
        video_path,
        srt_path,
        progress_callback
    )

    return result


# ============================================================
# COUNTDOWN
# ============================================================

async def countdown(
    sts,
    processed,
    total,
    next_filename,
    seconds
):

    processed_text = "\n".join(
        f"  ├─ ✅ {name}"
        for name in processed
    )

    if not processed_text:
        processed_text = "  └─ None"

    for remaining in range(
        seconds,
        0,
        -1
    ):

        text = (
            f"⏳ <b>Preparing Next Subtitle</b>\n\n"
            f"📊 <b>Progress:</b> "
            f"{len(processed)}/{total}\n\n"
            f"📋 <b>Completed Files</b>\n"
            f"{processed_text}\n\n"
            f"🎬 <b>Next:</b>\n"
            f"<code>{next_filename}</code>\n\n"
            f"🚀 Starting in "
            f"<b>{remaining}s</b>..."
        )

        await _edit(
            sts,
            text
        )

        await asyncio.sleep(1)


# ============================================================
# /GENSUB
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("gensub")
    & filters.user(ADMIN)
)
async def gensub_command(
    bot,
    msg
):

    reply = msg.reply_to_message

    # --------------------------------------------------------
    # Must reply to something
    # --------------------------------------------------------

    if not reply:

        return await msg.reply_text(
            "❌ <b>Please reply to a ZIP file.</b>\n\n"
            "📦 Reply to your ZIP and send:\n"
            "<code>/gensub</code>"
        )

    # --------------------------------------------------------
    # Must be a document
    # --------------------------------------------------------

    if not reply.document:

        return await msg.reply_text(
            "❌ <b>That is not a ZIP file.</b>\n\n"
            "📦 Please reply to a ZIP document."
        )

    document = reply.document

    zip_name = document.file_name or ""

    # --------------------------------------------------------
    # Check extension
    # --------------------------------------------------------

    if not zip_name.lower().endswith(".zip"):

        return await msg.reply_text(
            "❌ <b>Invalid file.</b>\n\n"
            "📦 The replied file must be a "
            "<b>.zip</b> file."
        )

    # --------------------------------------------------------
    # File information
    # --------------------------------------------------------

    zip_name = safe_filename(
        zip_name
    )

    zip_size = humanbytes(
        document.file_size or 0
    )

    # --------------------------------------------------------
    # Unique request ID
    # --------------------------------------------------------

    token = uuid.uuid4().hex[:12]

    _pending_gensub[token] = {
        "reply_chat_id": reply.chat.id,
        "reply_message_id": reply.id,
        "zip_name": zip_name,
        "file_size": document.file_size or 0
    }

    # --------------------------------------------------------
    # Confirmation
    #
    # IMPORTANT:
    # ZIP internal file count is impossible to know before
    # downloading the ZIP.
    # --------------------------------------------------------

    text = (
        f"📦 <b>{zip_name}</b>\n\n"
        f"💾 <b>ZIP Size:</b> {zip_size}\n"
        f"📂 <b>Files:</b> Will be checked after download\n\n"
        f"🇮🇳 <b>Source:</b> Hindi\n"
        f"🇬🇧 <b>Output:</b> English subtitles\n"
        f"📝 <b>Format:</b> SRT\n\n"
        f"⚡ <b>Ready to start?</b>"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data=(
                        f"gensub_confirm:{token}"
                    )
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data=(
                        f"gensub_cancel:{token}"
                    )
                )
            ]
        ]
    )

    await msg.reply_text(
        text,
        reply_markup=keyboard
    )


# ============================================================
# CANCEL CALLBACK
# ============================================================

@Client.on_callback_query(
    filters.regex(
        r"^gensub_cancel:"
    )
)
async def gensub_cancel(
    bot,
    query
):

    # --------------------------------------------------------
    # Only ADMIN
    # --------------------------------------------------------

    if query.from_user.id != ADMIN:

        return await query.answer(
            "⛔ Not authorized.",
            show_alert=True
        )

    await query.answer(
        "Process cancelled."
    )

    token = query.data.split(
        ":",
        1
    )[1]

    _pending_gensub.pop(
        token,
        None
    )

    await _edit(
        query.message,
        "❌ <b>Process Cancelled</b>\n\n"
        "Nothing was downloaded or processed."
    )


# ============================================================
# CONFIRM CALLBACK
# ============================================================

@Client.on_callback_query(
    filters.regex(
        r"^gensub_confirm:"
    )
)
async def gensub_confirm(
    bot,
    query
):

    # --------------------------------------------------------
    # Only ADMIN
    # --------------------------------------------------------

    if query.from_user.id != ADMIN:

        return await query.answer(
            "⛔ Not authorized.",
            show_alert=True
        )

    await query.answer(
        "Starting subtitle generator..."
    )

    token = query.data.split(
        ":",
        1
    )[1]

    job = _pending_gensub.pop(
        token,
        None
    )

    if not job:

        return await _edit(
            query.message,
            "❌ <b>Request expired.</b>\n\n"
            "Please send <code>/gensub</code> "
            "again."
        )

    sts = query.message

    zip_name = job["zip_name"]

    # --------------------------------------------------------
    # Unique working directory
    # --------------------------------------------------------

    job_id = uuid.uuid4().hex[:12]

    job_dir = os.path.join(
        GENSUB_ROOT,
        job_id
    )

    os.makedirs(
        job_dir,
        exist_ok=True
    )

    zip_path = os.path.join(
        job_dir,
        zip_name
    )

    extract_dir = os.path.join(
        job_dir,
        "files"
    )

    os.makedirs(
        extract_dir,
        exist_ok=True
    )

    try:

        # ====================================================
        # DOWNLOAD
        # ====================================================

        await _edit(
            sts,
            "🗑️ <b>Deleting current information...</b>"
        )

        await asyncio.sleep(
            1
        )

        await _edit(
            sts,
            f"📥 <b>Downloading ZIP</b>\n\n"
            f"📦 <code>{zip_name}</code>"
        )

        c_time = time.time()

        await bot.get_messages(
            job["reply_chat_id"],
            job["reply_message_id"]
        )

        reply_message = await bot.get_messages(
            job["reply_chat_id"],
            job["reply_message_id"]
        )

        await reply_message.download(
            file_name=zip_path,
            progress=progress_message,
            progress_args=(
                f"📥 Downloading • {zip_name}",
                sts,
                c_time
            )
        )

        # ====================================================
        # DOWNLOAD COMPLETE
        # ====================================================

        downloaded_size = humanbytes(
            os.path.getsize(zip_path)
        )

        await _edit(
            sts,
            f"✅ <b>Download Completed</b>\n\n"
            f"📦 <b>{zip_name}</b>\n"
            f"💾 <b>Size:</b> {downloaded_size}"
        )

        # ====================================================
        # EXTRACT
        # ====================================================

        await asyncio.sleep(
            1
        )

        await _edit(
            sts,
            f"📂 <b>Preparing ZIP files...</b>\n\n"
            f"📦 <code>{zip_name}</code>\n"
            f"⚙️ Extracting..."
        )

        safe_extract_zip(
            zip_path,
            extract_dir
        )

        videos = get_video_files(
            extract_dir
        )

        total_files = len(
            videos
        )

        # ====================================================
        # NO VIDEOS
        # ====================================================

        if total_files == 0:

            await _edit(
                sts,
                "❌ <b>No supported video files found.</b>\n\n"
                "Supported formats:\n"
                "• MP4\n"
                "• MKV\n"
                "• AVI\n"
                "• MOV\n"
                "• WEBM\n"
                "• M4V\n"
                "• FLV\n"
                "• TS"
            )

            return

        # ====================================================
        # REAL FILE COUNT
        # ====================================================

        await _edit(
            sts,
            f"✅ <b>Download Completed</b>\n\n"
            f"📦 <b>{zip_name}</b>\n"
            f"💾 <b>Size:</b> {downloaded_size}\n"
            f"📂 <b>Video Files:</b> {total_files}"
        )

        await asyncio.sleep(
            1
        )

        # ====================================================
        # STARTING
        # ====================================================

        await _edit(
            sts,
            f"🎬 <b>Starting Subtitle Generator</b>\n\n"
            f"📂 <b>Files found:</b> {total_files}\n"
            f"🇮🇳 Hindi → 🇬🇧 English\n"
            f"📝 SRT subtitles\n\n"
            f"⏳ First file will start shortly..."
        )

        # Requested 10-second wait
        await asyncio.sleep(
            10
        )

        # ====================================================
        # LOAD MODEL ONCE
        # ====================================================

        await _edit(
            sts,
            "⚙️ <b>Preparing Faster-Whisper...</b>\n\n"
            "🔄 Loading subtitle engine..."
        )

        model = await get_whisper_model()

        # ====================================================
        # PROCESS FILES
        # ====================================================

        processed = []

        for index, video_path in enumerate(
            videos,
            start=1
        ):

            video_name = os.path.basename(
                video_path
            )

            title = os.path.splitext(
                video_name
            )[0]

            srt_path = os.path.join(
                extract_dir,
                f"{title}.srt"
            )

            # =================================================
            # GENERATING
            # =================================================

            await _edit(
                sts,
                f"🎙️ <b>Generating Subtitles</b>\n\n"
                f"🎬 <b>Current File</b>\n"
                f"<code>{video_name}</code>\n\n"
                f"📊 <b>Progress:</b> "
                f"{index}/{total_files}\n"
                f"🇮🇳 Hindi → 🇬🇧 English\n\n"
                f"⚙️ <b>Processing...</b>"
            )

            try:

                result = await generate_subtitle(
                    model=model,
                    video_path=video_path,
                    srt_path=srt_path,
                    status_message=sts,
                    current_index=index,
                    total_files=total_files,
                    filename=video_name
                )

            except Exception as e:

                print(
                    f"[GENSUB] Whisper error "
                    f"for {video_name}: {e}"
                )

                await _edit(
                    sts,
                    f"❌ <b>Subtitle Generation Failed</b>\n\n"
                    f"🎬 <code>{video_name}</code>\n\n"
                    f"⚠️ <b>Error:</b>\n"
                    f"<code>{str(e)[:1000]}</code>\n\n"
                    f"⏭️ Moving to the next file..."
                )

                await asyncio.sleep(
                    3
                )

                continue

            # =================================================
            # SUBTITLE GENERATED
            # =================================================

            processed.append(
                video_name
            )

            await _edit(
                sts,
                f"✅ <b>Subtitle Generated</b>\n\n"
                f"🎬 <b>Video:</b>\n"
                f"<code>{video_name}</code>\n\n"
                f"📝 <b>Subtitle:</b>\n"
                f"<code>{title}.srt</code>\n\n"
                f"📊 <b>Processed:</b> "
                f"{len(processed)}/{total_files}"
            )

            await asyncio.sleep(
                1
            )

            # =================================================
            # UPLOAD
            # =================================================

            upload_sts = sts

            await _edit(
                upload_sts,
                f"📤 <b>Uploading Subtitle</b>\n\n"
                f"📝 <code>{title}.srt</code>\n"
                f"📊 {index}/{total_files}"
            )

            c_time = time.time()

            try:

                await bot.send_document(
                    chat_id=sts.chat.id,
                    document=srt_path,
                    file_name=f"{title}.srt",
                    caption=(
                        f"📝 <b>{title}.srt</b>\n\n"
                        f"🇬🇧 English Subtitle"
                    ),
                    progress=progress_message,
                    progress_args=(
                        f"📤 Uploading • {title}.srt",
                        upload_sts,
                        c_time
                    )
                )

            except Exception as e:

                await _edit(
                    sts,
                    f"❌ <b>Subtitle Upload Failed</b>\n\n"
                    f"📝 <code>{title}.srt</code>\n\n"
                    f"⚠️ <code>{str(e)[:1000]}</code>"
                )

                await asyncio.sleep(
                    3
                )

                continue

            # =================================================
            # COMPLETED FILE LIST
            # =================================================

            processed_text = "\n".join(
                f"  ├─ ✅ {name}"
                for name in processed
            )

            await _edit(
                sts,
                f"🎉 <b>Subtitle Sent Successfully</b>\n\n"
                f"📝 <code>{title}.srt</code>\n\n"
                f"📊 <b>Processed:</b> "
                f"{len(processed)}/{total_files}\n\n"
                f"📋 <b>Completed Files</b>\n"
                f"{processed_text}"
            )

            # =================================================
            # WAIT BEFORE NEXT FILE
            # =================================================

            if index < total_files:

                next_video = os.path.basename(
                    videos[index]
                )

                await countdown(
                    sts=sts,
                    processed=processed,
                    total=total_files,
                    next_filename=next_video,
                    seconds=30
                )

        # ====================================================
        # ALL FILES COMPLETE
        # ====================================================

        if processed:

            processed_text = "\n".join(
                f"  ├─ ✅ {name}"
                for name in processed
            )

            await _edit(
                sts,
                f"🎊 <b>All Files Processed!</b>\n\n"
                f"📦 <b>ZIP:</b>\n"
                f"<code>{zip_name}</code>\n\n"
                f"📊 <b>Completed:</b> "
                f"{len(processed)}/{total_files}\n\n"
                f"📋 <b>Processed Files</b>\n"
                f"{processed_text}\n\n"
                f"✨ <b>Subtitle generation complete!</b>"
            )

        else:

            await _edit(
                sts,
                f"⚠️ <b>Processing Finished</b>\n\n"
                f"❌ No subtitles were successfully generated.\n\n"
                f"📦 <code>{zip_name}</code>"
            )

    except Exception as e:

        print(
            f"[GENSUB] Fatal error: {e}"
        )

        await _edit(
            sts,
            f"❌ <b>Subtitle Process Failed</b>\n\n"
            f"⚠️ <b>Error:</b>\n"
            f"<code>{str(e)[:1500]}</code>"
        )

    finally:

        # ====================================================
        # CLEANUP
        # ====================================================

        try:

            if os.path.isdir(
                job_dir
            ):

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True
                )

        except Exception as e:

            print(
                f"[GENSUB] Cleanup error: {e}"
            )
