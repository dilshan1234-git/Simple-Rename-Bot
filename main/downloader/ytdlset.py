# main/downloader/ytdlset.py

import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN

# In-memory setting for mode (you can replace with a database later)
ytdl_mode = {}

def get_mode(user_id):
    return ytdl_mode.get(user_id, "video")

def set_mode(user_id, mode):
    ytdl_mode[user_id] = mode

@Client.on_message(filters.private & filters.command("ytdlset") & filters.user(ADMIN))
async def ytdl_set_command(bot, msg):
    mode = get_mode(msg.from_user.id)
    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")]
    ])

    await msg.reply("⚙️ **Select your method:**", reply_markup=buttons)

@Client.on_callback_query(filters.regex(r'^set_ytdl_'))
async def ytdl_set_callback(bot, query):
    mode = query.data.replace("set_ytdl_", "")
    set_mode(query.from_user.id, mode)

    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")]
    ])

    await query.edit_message_reply_markup(reply_markup=buttons)

# ─── NEW: Move downloader.py to root ──────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("moveyt") & filters.user(ADMIN))
async def move_downloader_to_root(bot, msg):
    source = "/content/Simple-Rename-Bot/main/downloader/downloader.py"
    destination = "/content/Simple-Rename-Bot/downloader.py"

    try:
        shutil.move(source, destination)
        await msg.reply("✅ `downloader.py` has been moved to root directory.")
    except FileNotFoundError:
        await msg.reply("❌ File not found! Already moved or missing.")
    except Exception as e:
        await msg.reply(f"❌ Error while moving: `{e}`")

# ─── NEW: Move downloader.py back to main/downloader ─────────────────────────────
@Client.on_message(filters.private & filters.command("backyt") & filters.user(ADMIN))
async def move_downloader_back(bot, msg):
    source = "/content/Simple-Rename-Bot/downloader.py"
    destination = "/content/Simple-Rename-Bot/main/downloader/downloader.py"

    try:
        shutil.move(source, destination)
        await msg.reply("✅ `downloader.py` has been moved back to its original location.")
    except FileNotFoundError:
        await msg.reply("❌ File not found in root! Already moved or missing.")
    except Exception as e:
        await msg.reply(f"❌ Error while moving back: `{e}`")
# main/downloader/ytdlset.py

import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN

# In-memory setting for mode (you can replace with a database later)
ytdl_mode = {}

def get_mode(user_id):
    return ytdl_mode.get(user_id, "video")

def set_mode(user_id, mode):
    ytdl_mode[user_id] = mode

@Client.on_message(filters.private & filters.command("ytdlset") & filters.user(ADMIN))
async def ytdl_set_command(bot, msg):
    mode = get_mode(msg.from_user.id)
    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")]
    ])

    await msg.reply("⚙️ **Select your method:**", reply_markup=buttons)

@Client.on_callback_query(filters.regex(r'^set_ytdl_'))
async def ytdl_set_callback(bot, query):
    mode = query.data.replace("set_ytdl_", "")
    set_mode(query.from_user.id, mode)

    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")]
    ])

    await query.edit_message_reply_markup(reply_markup=buttons)

# ─── NEW: Move downloader.py to root ──────────────────────────────────────────────
@Client.on_message(filters.private & filters.command("moveyt") & filters.user(ADMIN))
async def move_downloader_to_root(bot, msg):
    source = "/content/Simple-Rename-Bot/main/downloader/downloader.py"
    destination = "/content/Simple-Rename-Bot/downloader.py"

    try:
        shutil.move(source, destination)
        await msg.reply("✅ `downloader.py` has been moved to root directory.")
    except FileNotFoundError:
        await msg.reply("❌ File not found! Already moved or missing.")
    except Exception as e:
        await msg.reply(f"❌ Error while moving: `{e}`")

# ─── NEW: Move downloader.py back to main/downloader ─────────────────────────────
@Client.on_message(filters.private & filters.command("backyt") & filters.user(ADMIN))
async def move_downloader_back(bot, msg):
    source = "/content/Simple-Rename-Bot/downloader.py"
    destination = "/content/Simple-Rename-Bot/main/downloader/downloader.py"

    try:
        shutil.move(source, destination)
        await msg.reply("✅ `downloader.py` has been moved back to its original location.")
    except FileNotFoundError:
        await msg.reply("❌ File not found in root! Already moved or missing.")
    except Exception as e:
        await msg.reply(f"❌ Error while moving back: `{e}`")
