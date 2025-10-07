from pyrogram import Client
from config import *
import os

class Bot(Client):
    if not os.path.isdir(DOWNLOAD_LOCATION):
        os.makedirs(DOWNLOAD_LOCATION)
    
    def __init__(self):
        super().__init__(
            name="simple-renamer",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,  # Increased from 100 for better download performance
            plugins={"root": "main"},
            sleep_threshold=5,  # Reduced from 10 for faster responses
            max_concurrent_transmissions=10  # NEW: Allow more concurrent downloads
        )
    
    async def start(self):
        await super().start()
        me = await self.get_me()
        print(f"{me.first_name} | @{me.username} 𝚂𝚃𝙰𝚁𝚃𝙴𝙳...⚡️")
    
    async def stop(self, *args):
        await super().stop()
        print("Bot Restarting........")

bot = Bot()
bot.run()
