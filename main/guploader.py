from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from pyrogram import Client, filters
from config import DOWNLOAD_LOCATION, ADMIN
import os

# Load the service account JSON file
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Define a dictionary to track user responses
user_responses = {}

# Define an async function for uploading to Google Drive
async def upload_files_to_drive(chat_id, bot, folder_path):
    if not os.path.exists(folder_path):
        await bot.send_message(chat_id, f"❌ The path '{folder_path}' does not exist.")
        return

    # Upload files in the folder
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)

        if os.path.isfile(file_path):
            file_metadata = {'name': file_name}
            media = MediaFileUpload(file_path, resumable=True)

            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            # Send progress and completion message
            await bot.send_message(chat_id, f"✅ Uploaded '{file_name}' to Google Drive (File ID: {file.get('id')}).")

    await bot.send_message(chat_id, "🎉 All files have been uploaded successfully!")

# Define the command handler for uploading to Google Drive
@Client.on_message(filters.private & filters.command("gupload") & filters.user(ADMIN))
async def upload_to_drive_command_handler(bot, msg):
    # Ask user for the folder path in Colab
    await bot.send_message(msg.chat.id, "📁 Send the path of the folder containing the files you want to upload.")
    user_responses[msg.chat.id] = {"question": "Please send the path of the folder containing the files you want to upload."}

# Define a handler for receiving user responses
@Client.on_message(filters.private & filters.text & filters.user(ADMIN))
async def handle_user_response(bot, msg):
    chat_id = msg.chat.id
    if chat_id in user_responses:
        folder_path = msg.text.strip()
        del user_responses[chat_id]  # Remove user response entry

        await upload_files_to_drive(chat_id, bot, folder_path)
