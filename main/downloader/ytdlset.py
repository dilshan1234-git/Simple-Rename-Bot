from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN

# In-memory settings (replace with database in production)
user_settings = {}

def get_settings(user_id):
    return user_settings.get(user_id, {"mode": "video", "auto_download": False})

def set_mode(user_id, mode):
    settings = get_settings(user_id)
    settings["mode"] = mode
    user_settings[user_id] = settings

def toggle_auto_download(user_id):
    settings = get_settings(user_id)
    settings["auto_download"] = not settings["auto_download"]
    user_settings[user_id] = settings

@Client.on_message(filters.private & filters.command("ytdlset") & filters.user(ADMIN))
async def ytdl_set_command(bot, msg):
    user_id = msg.from_user.id
    settings = get_settings(user_id)

    mode = settings["mode"]
    auto_download = settings["auto_download"]

    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""
    auto_tick = "✅" if auto_download else "❌"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")],
        [InlineKeyboardButton(f"Auto Download : {auto_tick}", callback_data="toggle_auto_download")]
    ])

    await msg.reply("⚙️ **Select your method:**", reply_markup=buttons)

@Client.on_callback_query(filters.regex(r'^set_ytdl_'))
async def ytdl_set_callback(bot, query):
    user_id = query.from_user.id
    action = query.data.replace("set_ytdl_", "")

    if action in ["video", "playlist"]:
        set_mode(user_id, action)
    elif action == "toggle_auto_download":
        toggle_auto_download(user_id)

    # Update button states
    settings = get_settings(user_id)
    mode = settings["mode"]
    auto_download = settings["auto_download"]

    video_tick = "✅" if mode == "video" else ""
    playlist_tick = "✅" if mode == "playlist" else ""
    auto_tick = "✅" if auto_download else "❌"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{video_tick} Video URL", callback_data="set_ytdl_video")],
        [InlineKeyboardButton(f"{playlist_tick} Playlist URL", callback_data="set_ytdl_playlist")],
        [InlineKeyboardButton(f"Auto Download : {auto_tick}", callback_data="toggle_auto_download")]
    ])

    await query.edit_message_reply_markup(reply_markup=buttons)
