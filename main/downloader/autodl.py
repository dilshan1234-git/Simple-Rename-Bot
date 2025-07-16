import os
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from main.downloader.ytdlset import get_settings
from main.downloader.downloader import process_single_video, yt_callback_handler, auto_download_queues
from config import ADMIN

@Client.on_message(filters.private & filters.text & filters.user)
async def handle_auto_download_commands(bot, msg):
    user_id = msg.from_user.id
    text = msg.text.strip()

    # Only handle Done/Cancel buttons when auto-download is enabled
    settings = get_settings(user_id)
    if not settings.get("auto_download"):
        return

    if text == "✅ Done":
        queue = auto_download_queues.get(user_id)
        if not queue:
            return await msg.reply("ℹ️ Queue is empty.", reply_markup=ReplyKeyboardRemove())

        await msg.reply(
            f"🚀 Starting download of {len(queue)} video(s)...",
            reply_markup=ReplyKeyboardRemove()
        )

        for url in queue:
            try:
                # Process like user sent it manually
                fake_msg = msg
                fake_msg.text = url
                fake_msg.from_user = msg.from_user
                fake_msg.chat = msg.chat
                video_info_msg = await process_single_video(bot, fake_msg, url)

                # Find the 720p resolution button
                buttons = video_info_msg.reply_markup.inline_keyboard
                target_cb = None
                for row in buttons:
                    for btn in row:
                        if "720p" in btn.text and btn.callback_data.startswith("yt_"):
                            target_cb = btn.callback_data
                            break
                    if target_cb:
                        break

                if not target_cb:
                    await bot.send_message(msg.chat.id, "⚠️ 720p resolution not found, skipping...")
                    continue

                # Create a dummy callback query to simulate a button press
                class DummyMessage:
                    def __init__(self, chat_id, message_id, caption):
                        self.chat = type("obj", (), {"id": chat_id})
                        self.id = message_id
                        self.caption = caption

                class DummyUser:
                    def __init__(self, user_id):
                        self.id = user_id

                class DummyQuery:
                    def __init__(self, cb_data, chat_id, message_id, caption):
                        self.data = cb_data
                        self.from_user = DummyUser(user_id)
                        self.message = DummyMessage(chat_id, message_id, caption)

                dummy_query = DummyQuery(
                    cb_data=target_cb,
                    chat_id=msg.chat.id,
                    message_id=video_info_msg.id,
                    caption=video_info_msg.caption
                )

                await yt_callback_handler(bot, dummy_query)

            except Exception as e:
                await bot.send_message(msg.chat.id, f"❌ Error while processing:\n`{e}`")

        auto_download_queues[user_id] = []  # Clear queue after done

    elif text == "❌ Cancel":
        auto_download_queues[user_id] = []
        await msg.reply("❌ Auto download queue cleared.", reply_markup=ReplyKeyboardRemove())
