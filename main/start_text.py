from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN, START_IMAGE_URL


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(bot, msg):
    if msg.from_user.id == ADMIN:
        await start(bot, msg, cb=False)
    else:
        txt = "This is a personal use bot 🙏. Do you want your own bot? 👇 Click the source code to deploy"
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🤖 SOURCE CODE", url="https://github.com/MrMKN/Simple-Rename-Bot")
        ], [
            InlineKeyboardButton("🖥️ How To Deploy", url="https://youtu.be/oc847WvOUaI"),
            InlineKeyboardButton("ℹ️ Informations", callback_data="informations")
        ]])
        await msg.reply_text(text=txt, reply_markup=btn, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex("informations"))
async def informations(bot, msg):
    txt = ("<b>🤖 ᴍy ɴᴀᴍᴇ : Dilrenamer\n"
           "🖥️ Dᴇᴠᴇʟᴏᴩᴇʀ : Dilshan\n"
           "👨‍💻 Owner : Private Bots\n"
           "✏️ Lᴀɴɢᴜᴀɢᴇ: Pyᴛʜᴏɴ\n"
           "📊 Bᴜɪʟᴅ Vᴇʀꜱɪᴏɴ: Pʀɪᴠᴀᴛᴇ Bᴏᴛs\n\n"
           "<b>Thanks To All Who Supported ❤</b>")
    button = [[
        InlineKeyboardButton("🚫 Close", callback_data="del"),
        InlineKeyboardButton("⬅️ Back", callback_data="start")
    ]]
    await msg.message.edit(text=txt, reply_markup=InlineKeyboardMarkup(button), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex("start"))
async def start(bot, msg, cb=True):
    txt = f"Hi {msg.from_user.mention}, I am a simple rename bot for personal usage.\nThis bot is made by <b><a href='https://github.com/MrMKN'>MrMKN</a></b>"
    button = [[
        InlineKeyboardButton("🤖 Bot Updates", url="https://t.me/mkn_bots_updates")
    ], [
        InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        InlineKeyboardButton("📡 About", callback_data="about")
    ], [
        InlineKeyboardButton("ℹ️ Informations", callback_data="informations")
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
    txt = (
        f"<b>Bot Name: {me.mention}\n"
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
    except BaseException:
        return
