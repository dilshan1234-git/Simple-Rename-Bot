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


@Client.on_message(filters.private &
                   filters.command("moveback") & filters.user(ADMIN))
async def move_back(bot, msg):
    if os.path.exists(ARCHIVE_EXTRACTOR_SRC):
        shutil.move(ARCHIVE_EXTRACTOR_SRC, ARCHIVE_EXTRACTOR_DEST)
        await msg.reply_text(f"📁 `archive_extractor.py` has been moved back to {ARCHIVE_EXTRACTOR_DEST}.")
    else:
        await msg.reply_text("⚠️ The file is not found in the source directory.")


@Client.on_message(filters.private & filters.command("zip")
                   & filters.user(ADMIN))
async def start_archive(bot, msg):
    chat_id = msg.chat.id

    # Initialize the user's session
    user_files[chat_id] = {
        "files": [],
        "is_collecting": False,
        "awaiting_zip_name": True,
        "number_zip": False}

    await msg.reply_text("🔤 **Please send the name you want for the ZIP file.**")


@Client.on_message(filters.private & filters.user(ADMIN) & filters.text)
async def receive_zip_name(bot, msg):
    chat_id = msg.chat.id

    if chat_id in user_files and user_files[chat_id]["awaiting_zip_name"]:
        # Store the ZIP name and prompt for zipping method
        zip_name = msg.text + ".zip"
        user_files[chat_id]["zip_name"] = zip_name
        user_files[chat_id]["awaiting_zip_name"] = False

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔢 Number Zipping", callback_data="number_zipping"),
             InlineKeyboardButton("🗂️ Normal Zipping", callback_data="normal_zipping")]
        ])

        await msg.reply_text(
            f"📦 **ZIP Name:** `{zip_name}`\n"
            "Select your preferred zipping method:",
            reply_markup=keyboard
        )


@Client.on_message(filters.private & filters.user(ADMIN) &
                   (filters.document | filters.video | filters.audio))
async def collect_files(bot, msg):
    chat_id = msg.chat.id

    if chat_id in user_files and user_files[chat_id]["is_collecting"]:
        # Collect files
        user_files[chat_id]["files"].append(msg)
        count = len(user_files[chat_id]["files"])

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done", callback_data="done_collecting"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
        ])

        await msg.reply_text(
            f"📥 **File collected!**\n"
            f"Files collected: {count}\n"
            "Continue sending files or click **Done** when you're finished.",
            reply_markup=keyboard
        )


@Client.on_callback_query(filters.regex("number_zipping"))
async def number_zipping(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["number_zip"] = True
    user_files[chat_id]["is_collecting"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="done_collecting"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await query.message.edit_text(
        "🔢 **Number zipping selected!**\n"
        "Now, send the files you want to include in the ZIP.\n"
        "When you're done, click the **Done** button.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("normal_zipping"))
async def normal_zipping(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_files[chat_id]["is_collecting"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="done_collecting"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await query.message.edit_text(
        "🗂️ **Normal zipping selected!**\n"
        "Now, send the files you want to include in the ZIP.\n"
        "When you're done, click the **Done** button.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("done_collecting"))
async def done_collecting(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    files = user_files.get(chat_id, {}).get("files", [])
    zip_name = user_files.get(chat_id, {}).get("zip_name", "output.zip")
    number_zip = user_files.get(chat_id, {}).get("number_zip", False)

    if not files:
        await query.message.edit_text("⚠️ No files were sent to create a ZIP.")
        return

    # Handling file names with numbering if number_zip is selected
    file_names = []
    for idx, f in enumerate(files, start=1):
        if f.document:
            file_name = f"{idx}.{f.document.file_name}" if number_zip else f.document.file_name
            file_names.append(file_name)
        elif f.video:
            file_name = f"{idx}.{f.video.file_name}" if number_zip else f.video.file_name
            file_names.append(file_name)
        elif f.audio:
            file_name = f"{idx}.{f.audio.file_name}" if number_zip else f.audio.file_name
            file_names.append(file_name)

    file_list_text = "\n".join([f"`{name}`" for name in file_names])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_zip"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_collecting")]
    ])

    await query.message.edit_text(
        "📦 **The following files will be added to the ZIP:**\n\n" +
        file_list_text +
        f"\n\n**ZIP Name:** `{zip_name}`\n\nClick **Confirm** to proceed or **Cancel** to stop.",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex("confirm_zip"))
async def confirm_zip(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    zip_name = user_files.get(chat_id, {}).get("zip_name", "output.zip")
    number_zip = user_files.get(chat_id, {}).get("number_zip", False)

    await query.message.edit_text("📥 **Downloading your files...**")

    zip_path = os.path.join(DOWNLOAD_LOCATION, zip_name)
    with zipfile.ZipFile(zip_path, 'w') as archive:
        for idx, media_msg in enumerate(user_files[chat_id]["files"], start=1):
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

    await query.message.edit_text("✅ **Files downloaded. Creating your ZIP...**")

    uploading_message = await query.message.edit_text("🚀 **Uploading started...** 📤")

    c_time = time.time()
    sent_msg = await bot.send_document(
        chat_id,
        document=zip_path,
        caption=f"Here is your ZIP file: `{zip_name}`",
        progress=progress_message,
        progress_args=(f"📤Uploading ZIP...Thanks To All Who Supported ❤️\n\n**📦 {zip_name}**", query.message, c_time)
    )

    # Remove the progress message after uploading the ZIP
    await uploading_message.delete()

    os.remove(zip_path)
    del user_files[chat_id]


@Client.on_callback_query(filters.regex("cancel_collecting"))
async def cancel_collecting(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    del user_files[chat_id]
    await query.message.edit_text("❌ **File collection cancelled.**")
