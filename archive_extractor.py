import time
import os
import zipfile
import shutil
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Global variable to store files and user data
user_files = {}

# Paths
ARCHIVE_EXTRACTOR_SRC = "/content/Simple-Rename-Bot/main/archive_extractor.py"
ARCHIVE_EXTRACTOR_DEST = "/content/Simple-Rename-Bot/archive_extractor.py"


async def safe_edit(message: Message, new_text: str, **kwargs) -> Message:
    """
    Safely edit a Telegram message text:
    - If the current text/caption already equals new_text (ignoring surrounding whitespace),
      skip the edit (prevents MESSAGE_NOT_MODIFIED).
    - If edit fails, attempt one forced edit by appending a zero-width space.
    - Always return a Message object (the edited message or original if edit didn't happen).
    """
    if message is None:
        return message
    try:
        # Prefer message.text, fallback to caption for messages that had media
        current = message.text if getattr(message, "text", None) is not None else (message.caption or "")
    except Exception:
        current = ""

    # Normalize whitespace before compare
    if (str(current).strip() == str(new_text).strip()):
        return message

    try:
        edited = await message.edit_text(new_text, **kwargs)
        return edited
    except Exception as e:
        # Try one forced edit with a zero-width space to avoid identical-content error
        try:
            forced = await message.edit_text(new_text + "\u200b", **kwargs)
            return forced
        except Exception as e2:
            # If all edits fail, return the original message object
            print("safe_edit failed:", e, e2)
            return message


@Client.on_message(filters.private & filters.command("moveback") & filters.user(ADMIN))
async def move_back(bot, msg):
    if os.path.exists(ARCHIVE_EXTRACTOR_SRC):
        shutil.move(ARCHIVE_EXTRACTOR_SRC, ARCHIVE_EXTRACTOR_DEST)
        await msg.reply_text(f"📁 `archive_extractor.py` has been moved back to {ARCHIVE_EXTRACTOR_DEST}.")
    else:
        await msg.reply_text("⚠️ The file is not found in the source directory.")


@Client.on_message(filters.private & filters.command("zip") & filters.user(ADMIN))
async def start_archive(bot, msg):
    chat_id = msg.chat.id
    user_files[chat_id] = {
        "files": [],
        "is_collecting": False,
        "awaiting_zip_name": True,
        "number_zip": False,
        "use_colab": False,
        "last_msg_id": None  # to track the last status message
    }
    await msg.reply_text("🔤 **Please send the name you want for the ZIP file.**")


@Client.on_message(filters.private & filters.user(ADMIN) & filters.text)
async def receive_zip_name(bot, msg):
    chat_id = msg.chat.id

    if chat_id in user_files and user_files[chat_id]["awaiting_zip_name"]:
        zip_name = msg.text + ".zip"
        user_files[chat_id]["zip_name"] = zip_name
        user_files[chat_id]["awaiting_zip_name"] = False

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔢 Number Zipping", callback_data="number_zipping"),
             InlineKeyboardButton("🗂️ Normal Zipping", callback_data="normal_zipping")]
        ])

        await msg.reply_text(
            f"📦 **ZIP Name:** `{zip_name}`\nSelect your preferred zipping method:",
            reply_markup=keyboard
        )


@Client.on_callback_query(filters.regex("number_zipping|normal_zipping"))
async def select_zipping_method(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    is_number = query.data == "number_zipping"
    user_files[chat_id]["number_zip"] = is_number

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send files via Telegram", callback_data="use_telegram")],
        [InlineKeyboardButton("📁 Use files from Colab", callback_data="use_colab")]
    ])

    method_text = "🔢 Number zipping selected!" if is_number else "🗂️ Normal zipping selected!"
    await safe_edit(
        query.message,
        f"{method_text}\n\nSelect the source of your files:",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("use_telegram"))
async def use_telegram(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["is_collecting"] = True
    user_files[chat_id]["use_colab"] = False
    user_files[chat_id]["files"] = []

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="done_collecting"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    msg = await safe_edit(
        query.message,
        "📤 Now, send the files you want to include in the ZIP via Telegram.\n"
        "When you're done, click **Done**.",
        reply_markup=keyboard
    )
    # Ensure we store a message id when safe_edit returned a Message
    try:
        user_files[chat_id]["last_msg_id"] = msg.id if msg else None
    except Exception:
        user_files[chat_id]["last_msg_id"] = None


# Handle received media files for Telegram zipping
@Client.on_message(filters.private & filters.user(ADMIN) & (filters.document | filters.audio | filters.video | filters.photo))
async def collect_files(bot, msg):
    chat_id = msg.chat.id
    if chat_id not in user_files or not user_files[chat_id].get("is_collecting"):
        return

    # Add received file to list
    user_files[chat_id]["files"].append(msg)

    # Delete previous status message
    if user_files[chat_id].get("last_msg_id"):
        try:
            await bot.delete_messages(chat_id, user_files[chat_id]["last_msg_id"])
        except Exception:
            pass

    # Prepare file list text and total size
    files = user_files[chat_id]["files"]
    number_zip = user_files[chat_id]["number_zip"]
    file_list_text = []
    total_size = 0
    for idx, f in enumerate(files, start=1):
        # Use hasattr checks to be resilient to different message types
        if getattr(f, "document", None):
            name = f"{idx}.{f.document.file_name}" if number_zip else f.document.file_name
            total_size += f.document.file_size if getattr(f.document, "file_size", None) else 0
        elif getattr(f, "video", None):
            name = f"{idx}.{f.video.file_name}" if number_zip else f.video.file_name
            total_size += f.video.file_size if getattr(f.video, "file_size", None) else 0
        elif getattr(f, "audio", None):
            name = f"{idx}.{f.audio.file_name}" if number_zip else f.audio.file_name
            total_size += f.audio.file_size if getattr(f.audio, "file_size", None) else 0
        elif getattr(f, "photo", None):
            name = f"{idx}.photo.jpg" if number_zip else "photo.jpg"
            total_size += f.photo.file_size if getattr(f.photo, "file_size", None) else 0
        else:
            name = f"{idx}.Unknown"
        file_list_text.append(f"`{name}`")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_zip"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    msg2 = await msg.reply_text(
        "📥 **Received files:**\n\n" +
        "\n".join(file_list_text) +
        f"\n\n**Total Size:** `{humanbytes(total_size)}`" +
        f"\n**ZIP Name:** `{user_files[chat_id]['zip_name']}`\n\nClick **Confirm** to proceed or **Cancel** to stop.",
        reply_markup=keyboard
    )

    user_files[chat_id]["last_msg_id"] = msg2.id


@Client.on_callback_query(filters.regex("use_colab"))
async def use_colab(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["is_collecting"] = False
    user_files[chat_id]["use_colab"] = True

    # List files in the DOWNLOAD_LOCATION with allowed extensions
    colab_files = [
        os.path.join(DOWNLOAD_LOCATION, f)
        for f in os.listdir(DOWNLOAD_LOCATION)
        if os.path.isfile(os.path.join(DOWNLOAD_LOCATION, f))
           and f.lower().endswith(('.mp4', '.mkv', '.avi', '.mp3', '.wav', '.flac', '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.docx', '.txt', '.zip'))
    ]

    if not colab_files:
        await safe_edit(query.message, "⚠️ No valid media files found in Colab storage.")
        return

    user_files[chat_id]["files"] = colab_files
    file_list_text = "\n".join([f"`{os.path.basename(f)}`" for f in colab_files])
    total_size = sum(os.path.getsize(f) for f in colab_files)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_zip"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await safe_edit(
        query.message,
        "📁 **The following files will be added to the ZIP from Colab:**\n\n" +
        file_list_text +
        f"\n\n**Total Size:** `{humanbytes(total_size)}`" +
        f"\n**ZIP Name:** `{user_files[chat_id]['zip_name']}`\n\nClick **Confirm** to proceed or **Cancel** to stop.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("done_collecting"))
async def done_collecting(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    files = user_files.get(chat_id, {}).get("files", [])
    zip_name = user_files.get(chat_id, {}).get("zip_name", "output.zip")

    if not files:
        await safe_edit(query.message, "⚠️ No files were sent to create a ZIP.")
        return

    number_zip = user_files[chat_id].get("number_zip", False)
    file_names = []
    total_size = 0

    for idx, f in enumerate(files, start=1):
        if hasattr(f, "document"):
            file_name = f"{idx}.{f.document.file_name}" if number_zip else f.document.file_name
            total_size += f.document.file_size if getattr(f.document, "file_size", None) else 0
        elif hasattr(f, "video"):
            file_name = f"{idx}.{f.video.file_name}" if number_zip else f.video.file_name
            total_size += f.video.file_size if getattr(f.video, "file_size", None) else 0
        elif hasattr(f, "audio"):
            file_name = f"{idx}.{f.audio.file_name}" if number_zip else f.audio.file_name
            total_size += f.audio.file_size if getattr(f.audio, "file_size", None) else 0
        else:  # Colab files
            file_name = os.path.basename(f)
            if number_zip:
                file_name = f"{idx}.{file_name}"
            total_size += os.path.getsize(f)
        file_names.append(file_name)

    file_list_text = "\n".join([f"`{name}`" for name in file_names])
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_zip"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await safe_edit(
        query.message,
        "📦 **The following files will be added to the ZIP:**\n\n" +
        file_list_text +
        f"\n\n**Total Size:** `{humanbytes(total_size)}`" +
        f"\n**ZIP Name:** `{zip_name}`\n\nClick **Confirm** to proceed or **Cancel** to stop.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("confirm_zip"))
async def confirm_zip(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    zip_name = user_files.get(chat_id, {}).get("zip_name", "output.zip")
    number_zip = user_files.get(chat_id, {}).get("number_zip", False)
    use_colab = user_files.get(chat_id, {}).get("use_colab", False)

    # Inform user ZIP creation started
    await safe_edit(query.message, "📦 **Creating your ZIP...**")

    zip_path = os.path.join(DOWNLOAD_LOCATION, zip_name)
    with zipfile.ZipFile(zip_path, 'w') as archive:
        files = user_files[chat_id]["files"]

        if use_colab:
            for idx, file_path in enumerate(files, start=1):
                arc_name = f"{idx}.{os.path.basename(file_path)}" if number_zip else os.path.basename(file_path)
                archive.write(file_path, arc_name)
        else:
            for idx, media_msg in enumerate(files, start=1):
                c_time = time.time()
                file_name = f"{idx}.{media_msg.document.file_name}" if getattr(media_msg, "document", None) and number_zip else \
                            f"{idx}.{media_msg.video.file_name}" if getattr(media_msg, "video", None) and number_zip else \
                            f"{idx}.{media_msg.audio.file_name}" if getattr(media_msg, "audio", None) and number_zip else \
                            (media_msg.document.file_name if getattr(media_msg, "document", None) else
                             media_msg.video.file_name if getattr(media_msg, "video", None) else
                             media_msg.audio.file_name if getattr(media_msg, "audio", None) else "Unknown file")
                download_msg = f"**📥Downloading...**\n\n**📂{file_name}**"
                file_path = await media_msg.download(progress=progress_message, progress_args=(download_msg, query.message, c_time))
                archive.write(file_path, file_name)
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    # Indicate upload started (safe_edit prevents MESSAGE_NOT_MODIFIED)
    uploading_message = await safe_edit(query.message, "🚀 **Uploading started...** 📤")
    c_time = time.time()

    # Use send_document to upload ZIP with progress callback
    await bot.send_document(
        chat_id,
        document=zip_path,
        caption=f"Here is your ZIP file: `{zip_name}`",
        progress=progress_message,
        progress_args=(f"📤Uploading ZIP...\n\n**📦 {zip_name}**", query.message, c_time)
    )

    # Attempt to delete the status message if it is not the original (best-effort)
    try:
        # If safe_edit returned a different message object (edited), delete it.
        # If it returned the same message (no edit occurred), skip deleting to avoid removing user's message.
        if uploading_message and uploading_message.id != query.message.id:
            await uploading_message.delete()
    except Exception:
        # If deletion fails, ignore — we don't want the bot to crash for cleanup failures
        pass

    try:
        os.remove(zip_path)
    except Exception:
        pass

    # Cleanup stored user data
    if chat_id in user_files:
        del user_files[chat_id]


@Client.on_callback_query(filters.regex("cancel_collecting"))
async def cancel_collecting(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    if chat_id in user_files:
        del user_files[chat_id]
    await safe_edit(query.message, "❌ **File collection cancelled.**")
