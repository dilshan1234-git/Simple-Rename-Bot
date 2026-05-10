from os import environ

API_ID = int(environ.get("API_ID", "14631157"))
API_HASH = environ.get("API_HASH", "aa7c2b3be68a7488abdb9de6ce78d311")
BOT_TOKEN = environ.get(
    "BOT_TOKEN",
    "7341561892:AAE99sFum5IVj0ugv9XpIeMgBa5QjbzfbU8")
TG_MAX_FILE_SIZE = 2097152000  # 2GB for Telegram
CHUNK_SIZE = 1024 * 1024  # 1MB
PROCESS_MAX_TIMEOUT = 300  # 5 minutes
CAPTION = "{file_name}\n\n💽 size: {file_size}\n🕒 duration: {duration} seconds"
ADMIN = int(environ.get("ADMIN", "5380833276"))
CAPTION = environ.get("CAPTION", "video")
# Replace with your actual Telegraph image URL
TELEGRAPH_IMAGE_URL = "https://envs.sh/q2k.jpg"
VID_TRIMMER_URL = "https://envs.sh/qNI.jpg"

# for thumbnail ( back end is MrMKN brain 😉)
DOWNLOAD_LOCATION = "./DOWNLOADS"
START_IMAGE_URL = "https://envs.sh/klj.jpg"

# config.py

MEGA_EMAIL = "dinethinfinity123@gmail.com"
MEGA_PASSWORD = "mega1234"
