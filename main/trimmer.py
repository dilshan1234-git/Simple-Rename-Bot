import time
import os
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, ADMIN, VID_TRIMMER_URL 
from main.utils import progress_message, humanbytes
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from moviepy.editor import VideoFileClip
from main.downloader.ytdl_text import VID_TRIMMER_TEXT

# Temporary storage for media and trimming durations
trim_data = {}

@Client.on_message(filters.private & filters.command("trim") & filters.user(ADMIN))
async def start_trim_process(bot, msg):
    chat_id = msg.chat.id
    trim_data[chat_id] = {}
    
    # Sending the welcome message with the trimmer logo
    await bot.send_photo(
        chat_id=chat_id,
        photo=VID_TRIMMER_URL,
        caption=VID_TRIMMER_TEXT,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@Client.on_message(filters.private & filters.media & filters.user(ADMIN))
async def receive_media(bot, msg):
    chat_id = msg.chat.id
    if chat_id in trim_data and 'media' not in trim_data[chat_id]:
        media = msg.video or msg.document
        if media:
            trim_data[chat_id]['media'] = media
            file_name = media.file_name
            await msg.reply_text(f"📂 **Media received:** `{file_name}`\n\n**⏳ Please send the trimming durations in the format:** `HH:MM:SS HH:MM:SS` (start_time end_time)")

@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def receive_durations(bot, msg):
    chat_id = msg.chat.id
    if chat_id in trim_data and 'media' in trim_data[chat_id] and 'start_time' not in trim_data[chat_id]:
        durations = msg.text.strip().split()
        if len(durations) == 2:
            start_time_str, end_time_str = durations
            try:
                # Convert time strings to seconds
                start_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time_str.split(":"))))
                end_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time_str.split(":"))))
                
                trim_data[chat_id]['start_time'] = start_time
                trim_data[chat_id]['end_time'] = end_time
                trim_data[chat_id]['start_time_str'] = start_time_str
                trim_data[chat_id]['end_time_str'] = end_time_str

                await msg.reply_text(
                    f"🕒 **Trimming durations received:**\nStart: `{start_time_str}`\nEnd: `{end_time_str}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Confirm ✔️", callback_data="trim_confirm")],
                        [InlineKeyboardButton("Cancel 🚫", callback_data="trim_cancel")]
                    ])
                )
            except ValueError:
                await msg.reply_text("❌ **Invalid time format. Please use:** `HH:MM:SS HH:MM:SS`")
        else:
            await msg.reply_text("❌ **Please provide both start and end times in the format:** `HH:MM:SS HH:MM:SS`")

@Client.on_callback_query(filters.regex("trim_confirm") & filters.user(ADMIN))
async def trim_confirm_callback(bot, query):
    chat_id = query.message.chat.id
    if chat_id in trim_data and 'media' in trim_data[chat_id]:
        media = trim_data[chat_id]['media']
        file_name = media.file_name
        start_time = trim_data[chat_id]['start_time']
        end_time = trim_data[chat_id]['end_time']
        start_time_str = trim_data[chat_id]['start_time_str']
        end_time_str = trim_data[chat_id]['end_time_str']

        sts = await query.message.reply_text("🔄 **Downloading...** 📥")
        c_time = time.time()
        downloaded = await bot.download_media(
            media,
            progress=progress_message,
            progress_args=("📥 **Download Started...**", sts, c_time)
        )
        
        # Extracting thumbnail from the original video
        thumbnail = f"{os.path.splitext(downloaded)[0]}_thumbnail.jpg"
        await bot.download_media(media.thumbs[0].file_id, file_name=thumbnail) if media.thumbs else None

        output_video = f"{os.path.splitext(downloaded)[0]}_trimmed.mp4"

        try:
            # Use moviepy's ffmpeg_extract_subclip for trimming
            ffmpeg_extract_subclip(downloaded, start_time, end_time, targetname=output_video)
        except Exception as e:
            return await sts.edit(f"❌ **Error during trimming:** `{e}`")

        video_clip = VideoFileClip(output_video)
        duration = int(video_clip.duration)
        video_clip.close()

        filesize = humanbytes(os.path.getsize(output_video))
        cap = (f"🎬 **Trimmed Video**\n\n💽 **Size:** `{filesize}`\n"
               f"🕒 **Duration:** `{duration} seconds`\n"
               f"⏰ **Trimmed From:** `{start_time_str}` **to** `{end_time_str}`")

        await sts.edit(f"🚀 **Uploading started...📤**")
        c_time = time.time()
        try:
            await bot.send_video(
                chat_id, video=output_video, caption=cap,
                duration=duration, thumb=thumbnail if os.path.exists(thumbnail) else None, progress=progress_message,
                progress_args=(f"🚀 **Upload Started...📤**\n**Thanks To K-MAC For His Trimming Code❤ 🧑‍💻**\n\n**{os.path.basename(output_video)}**", sts, c_time)
            )
        except Exception as e:
            return await sts.edit(f"❌ **Error:** `{e}`")

        # Cleanup
        try:
            os.remove(downloaded)
            os.remove(output_video)
            if os.path.exists(thumbnail):
                os.remove(thumbnail)
        except:
            pass

        await sts.delete()
        del trim_data[chat_id]

@Client.on_callback_query(filters.regex("trim_cancel") & filters.user(ADMIN))
async def trim_cancel_callback(bot, query):
    chat_id = query.message.chat.id
    if chat_id in trim_data:
        del trim_data[chat_id]
    await query.message.reply_text("❌ **Trimming canceled.**")
    await query.message.delete()
