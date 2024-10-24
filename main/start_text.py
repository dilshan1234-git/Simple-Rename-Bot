from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN, START_IMAGE_URL

@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(bot, msg):
    txt = "This is a personal use bot 🙏. Do you want your own bot? 👇 Click the source code to deploy"
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🤖 SOURCE CODE", url="https://github.com/MrMKN/Simple-Rename-Bot")
    ], [
        InlineKeyboardButton("🖥️ How To Deploy", url="https://youtu.be/oc847WvOUaI"),
        InlineKeyboardButton("✨ Bot Features", callback_data="Bot_Features")
    ]])
    sent_msg = await msg.reply_text(text=txt, reply_markup=btn, disable_web_page_preview=True)
    # Store the message_id of the sent message to use in quoting features
    return sent_msg.id  # Corrected to return the message ID

@Client.on_callback_query(filters.regex("Bot_Features"))
async def Bot_Features(bot, msg):
    # Quoting the message by using the message_id
    original_message_id = msg.message.id  # Corrected to msg.message.id

    # Now send the bot features and reference the original message to make it "quoted"
    await bot.send_message(
        chat_id=msg.message.chat.id,
        text="""✨ ━━━━━━━━Bot Features━━━━━━━

📹 Youtube Video And Audio Downloader (/ytdl)
➭ Download YouTube videos in different formats available.
➭ Download YouTube video's audio in the highest format.
➭ Download YouTube video thumbnail.
➭ Get video description.
➭ Uploading progress tracking and Simple UI design.

✂ Advanced Video Trimmer (/trim)
➭ Trim a video with specific duration.
➭ Downloading and uploading progress tracking.
➭ Video and document support.
➭ Simple UI design.

ℹ Generate Mediainfo (/info)
➭ Generate Mediainfo for any file.
➭ All information support.
➭ Telegraph view (not sure anytime).

📂 File Zipper (/zip)
➭ Any kind of file support.
➭ Progress tracking.
➭ Move first before using.

Many more features will be added soon 🌟
""",
        reply_to_message_id=original_message_id,  # Referencing the original message
        parse_mode=enums.ParseMode.MARKDOWN
    )

@Client.on_callback_query(filters.regex("start"))
async def start(bot, msg, cb=True):
    txt = f"Hi {msg.from_user.mention}, I am a simple rename bot for personal usage.\nThis bot is made by <b><a href='https://github.com/MrMKN'>MrMKN</a></b>"
    button = [[
        InlineKeyboardButton("🤖 Bot Updates", url="https://t.me/mkn_bots_updates")
    ], [
        InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        InlineKeyboardButton("📡 About", callback_data="about")
    ], [
        InlineKeyboardButton("✨ Bot Feautures", callback_data="Bot_Features")  # Updated callback_data
    ]]

    if msg.from_user.id == ADMIN:
        await bot.send_photo(chat_id=msg.chat.id, photo=START_IMAGE_URL, caption=txt, reply_markup=InlineKeyboardMarkup(button))
    else:
        if cb:
            await msg.message.edit(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        else:
            await msg.reply_text(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)

# Remaining code unchanged

@Client.on_callback_query(filters.regex("start"))
async def start(bot, msg, cb=True):
    txt = f"Hi {msg.from_user.mention}, I am a simple rename bot for personal usage.\nThis bot is made by <b><a href='https://github.com/MrMKN'>MrMKN</a></b>"
    button = [[
        InlineKeyboardButton("🤖 Bot Updates", url="https://t.me/mkn_bots_updates")
    ], [
        InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        InlineKeyboardButton("📡 About", callback_data="about")
    ], [
        InlineKeyboardButton("✨ Bot Features", callback_data="Bot_Features")
    ]]

    if msg.from_user.id == ADMIN:
        await bot.send_photo(chat_id=msg.chat.id, photo=START_IMAGE_URL, caption=txt, reply_markup=InlineKeyboardMarkup(button))
    else:
        if cb:
            await msg.message.edit(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        else:
            await msg.reply_text(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex("help"))
async def help(bot, msg):
    txt = "Just send a file and /rename <new name> with replied your file\n\n"
    txt += "Send photo to set thumbnail automatically\n"
    txt += "/view to see your thumbnail\n"
    txt += "/del to delete your thumbnail"
    button = [[
        InlineKeyboardButton("🚫 Close", callback_data="del"),
        InlineKeyboardButton("⬅️ Back", callback_data="start")
    ]]
    await msg.message.edit(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True)

@Client.on_callback_query(filters.regex("about"))
async def about(bot, msg):
    me = await bot.get_me()
    Master = f"<a href='https://t.me/Mo_Tech_YT'>MoTech</a> & <a href='https://t.me/venombotupdates'>MhdRzn</a>"
    Source = "<a href='https://github.com/MrMKN/Simple-Rename-Bot'>Click Here</a>"
    txt = (f"<b>Bot Name: {me.mention}\n"
           f"Developer: <a href='https://github.com/MrMKN'>MrMKN</a>\n"
           f"Bot Updates: <a href='https://t.me/mkn_bots_updates'>Mᴋɴ Bᴏᴛᴢ™</a>\n"
           f"My Master's: {Master}\n"
           f"Source Code: {Source}</b>")
    button = [[
        InlineKeyboardButton("🚫 Close", callback_data="del"),
        InlineKeyboardButton("⬅️ Back", callback_data="start")
    ]]
    await msg.message.edit(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex("del"))
async def closed(bot, msg):
    try:
        await msg.message.delete()
    except:
        return
