import os
import time
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pytube import YouTube
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize Pyrogram client
app = Client("your_renamer_bot")

# /ytdl command handler
@app.on_message(filters.private & filters.command("ytdl") & filters.user(ADMIN))
async def youtube_download(bot, msg):
    chat_id = msg.chat.id
    logging.info(f"Received /ytdl command from chat_id: {chat_id}")
    await msg.reply_text("🔄 Please send your YouTube video link to download.")

# Handler for receiving the YouTube video link
@app.on_message(filters.private & filters.text & filters.user(ADMIN))
async def receive_youtube_link(bot, msg: Message):
    chat_id = msg.chat.id
    link = msg.text.strip()
    logging.info(f"Received YouTube link: {link} from chat_id: {chat_id}")
    try:
        yt = YouTube(link)
        title = yt.title
        views = yt.views
        likes = yt.likes
        filesize = yt.streams.get_highest_resolution().filesize

        caption = f"🎥 YouTube Video\n\n📺 Title: {title}\n👀 Views: {views}\n👍 Likes: {likes}\n💽 Size: {humanbytes(filesize)}"

        await msg.reply_photo(
            photo=yt.thumbnail_url,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Download", callback_data=f"download_{link}")]
            ])
        )
        logging.info(f"Sent video details for: {link}")
    except Exception as e:
        logging.error(f"Error processing YouTube link: {e}")
        await msg.reply_text(f"❌ Error: {e}")

# Callback query handler for download process
@app.on_callback_query(filters.regex(r"download_") & filters.user(ADMIN))
async def initiate_download(bot, query: CallbackQuery):
    chat_id = query.message.chat.id
    link = query.data.split("_", 1)[1]
    logging.info(f"Initiating download for link: {link} from chat_id: {chat_id}")
    try:
        yt = YouTube(link)
        stream = yt.streams.get_highest_resolution()
        await query.message.reply_text("🔄 Downloading video...")
        sts = await query.message.reply_text("📥 Downloading...")
        c_time = time.time()
        try:
            downloaded = stream.download(output_path=DOWNLOAD_LOCATION)
            filesize = humanbytes(os.path.getsize(downloaded))
            await sts.edit("🚀 Uploading video... 📤")
            c_time = time.time()
            await bot.send_video(
                chat_id,
                video=downloaded,
                thumb=yt.thumbnail_url,
                caption=f"🎥 YouTube Video\n\n📺 Title: {yt.title}\n👀 Views: {yt.views}\n👍 Likes: {yt.likes}\n💽 Size: {filesize}",
                progress=progress_message,
                progress_args=("🚀 Uploading video...", sts, c_time)
            )
        except Exception as e:
            logging.error(f"Error during download/upload: {e}")
            await sts.edit(f"❌ Error during download/upload: {e}")
        finally:
            os.remove(downloaded)
            await sts.delete()
    except Exception as e:
        logging.error(f"Error initiating download: {e}")
        await query.message.reply_text(f"❌ Error: {e}")
