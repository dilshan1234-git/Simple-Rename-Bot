import time
import os
import zipfile
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Global variable to store files and user data
user_files = {}

# Paths
ARCHIVE_EXTRACTOR_SRC = "/content/Simple-Rename-Bot/main/archive_extractor.py"
ARCHIVE_EXTRACTOR_DEST = "/content/Simple-Rename-Bot/archive_extractor.py"


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
        "use_colab": False
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

    # Ask user whether to use Telegram files or Colab files
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send files via Telegram", callback_data="use_telegram")],
        [InlineKeyboardButton("📁 Use files from Colab", callback_data="use_colab")]
    ])

    method_text = "🔢 Number zipping selected!" if is_number else "🗂️ Normal zipping selected!"
    await query.message.edit_text(
        f"{method_text}\n\nSelect the source of your files:",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("use_telegram"))
async def use_telegram(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["is_collecting"] = True
    user_files[chat_id]["use_colab"] = False

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="done_collecting"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await query.message.edit_text(
        "📤 Now, send the files you want to include in the ZIP via Telegram.\n"
        "When you're done, click **Done**.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("use_colab"))
async def use_colab(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["is_collecting"] = False
    user_files[chat_id]["use_colab"] = True

    # Only include files, ignore folders
    colab_files = [
        os.path.join(DOWNLOAD_LOCATION, f)
        for f in os.listdir(DOWNLOAD_LOCATION)
        if os.path.isfile(os.path.join(DOWNLOAD_LOCATION, f))
           and f.lower().endswith(('.mp4', '.mkv', '.avi', '.mp3', '.wav', '.flac', '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.docx', '.txt', '.zip'))
    ]

    if not colab_files:
        await query.message.edit_text("⚠️ No valid media files found in Colab storage.")
        return

    user_files[chat_id]["files"] = colab_files
    file_list_text = "\n".join([f"`{os.path.basename(f)}`" for f in colab_files])

    # Calculate total size
    total_size = sum(os.path.getsize(f) for f in colab_files)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_zip"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await query.message.edit_text(
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
        await query.message.edit_text("⚠️ No files were sent to create a ZIP.")
        return

    number_zip = user_files[chat_id].get("number_zip", False)
    file_names = []
    total_size = 0

    for idx, f in enumerate(files, start=1):
        if hasattr(f, "document"):
            file_name = f"{idx}.{f.document.file_name}" if number_zip else f.document.file_name
            total_size += f.document.file_size if f.document.file_size else 0
        elif hasattr(f, "video"):
            file_name = f"{idx}.{f.video.file_name}" if number_zip else f.video.file_name
            total_size += f.video.file_size if f.video.file_size else 0
        elif hasattr(f, "audio"):
            file_name = f"{idx}.{f.audio.file_name}" if number_zip else f.audio.file_name
            total_size += f.audio.file_size if f.audio.file_size else 0
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

    await query.message.edit_text(
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

    await query.message.edit_text("📦 **Creating your ZIP...**")

    zip_path = os.path.join(DOWNLOAD_LOCATION, zip_name)
    with zipfile.ZipFile(zip_path, 'w') as archive:
        files = user_files[chat_id]["files"]

        if use_colab:
            # Only write Colab files
            for idx, file_path in enumerate(files, start=1):
                arc_name = f"{idx}.{os.path.basename(file_path)}" if number_zip else os.path.basename(file_path)
                archive.write(file_path, arc_name)
        else:
            # Download files from Telegram
            for idx, media_msg in enumerate(files, start=1):
                c_time = time.time()
                file_name = f"{idx}.{media_msg.document.file_name}" if media_msg.document and number_zip else \
                            f"{idx}.{media_msg.video.file_name}" if media_msg.video and number_zip else \
                            f"{idx}.{media_msg.audio.file_name}" if media_msg.audio and number_zip else \
                            media_msg.document.file_name if media_msg.document else \
                            media_msg.video.file_name if media_msg.video else \
                            media_msg.audio.file_name if media_msg.audio else "Unknown file"
                download_msg = f"**📥Downloading...**\n\n**📂{file_name}**"
                file_path = await media_msg.download(progress=progress_message, progress_args=(download_msg, query.message, c_time))
                archive.write(file_path, file_name)
                os.remove(file_path)

    uploading_message = await query.message.edit_text("🚀 **Uploading started...** 📤")
    c_time = time.time()
    await bot.send_document(
        chat_id,
        document=zip_path,
        caption=f"Here is your ZIP file: `{zip_name}`",
        progress=progress_message,
        progress_args=(f"📤Uploading ZIP...\n\n**📦 {zip_name}**", query.message, c_time)
    )
    await uploading_message.delete()
    os.remove(zip_path)
    del user_files[chat_id]


@Client.on_callback_query(filters.regex("cancel_collecting"))
async def cancel_collecting(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    if chat_id in user_files:
        del user_files[chat_id]
    await query.message.edit_text("❌ **File collection cancelled.**")
