import os, time, subprocess, json, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputDocumentFileLocation
from config import DOWNLOAD_LOCATION, ADMIN
from main.utils import progress_message, humanbytes

async def optimized_download(client, message, file_path, sts):
    """
    Optimized parallel chunk download for maximum speed
    Downloads file in parallel chunks using Pyrogram's raw API
    """
    try:
        media = message.document or message.video or message.audio
        if not media:
            return None
        
        file_size = media.file_size
        
        # Get file details using get_messages to access raw attributes
        file_msg = await client.get_messages(message.chat.id, message.id)
        
        # Determine media type and get raw media object
        if file_msg.document:
            raw_media = file_msg.media.document
        elif file_msg.video:
            raw_media = file_msg.media.document
        elif file_msg.audio:
            raw_media = file_msg.media.document
        else:
            return None
        
        file_id = raw_media.id
        access_hash = raw_media.access_hash
        file_ref = raw_media.file_reference
        
        print(f"🚀 Starting optimized parallel download...")
        
        # Chunk settings for parallel download
        chunk_size = 1024 * 1024  # 1MB chunks
        concurrent_chunks = 8  # Download 8 chunks simultaneously
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Create file location
        location = InputDocumentFileLocation(
            id=int(file_id),
            access_hash=access_hash,
            file_reference=file_ref,
            thumb_size=""
        )
        
        # Download chunks in parallel
        downloaded_size = 0
        start_time = time.time()
        last_update = start_time
        
        with open(file_path, 'wb') as f:
            offset = 0
            while offset < file_size:
                # Prepare chunk download tasks
                tasks = []
                chunk_offsets = []
                
                for i in range(concurrent_chunks):
                    current_offset = offset + (i * chunk_size)
                    if current_offset >= file_size:
                        break
                    
                    chunk_offsets.append(current_offset)
                    
                    # Create download task for each chunk
                    task = client.invoke(
                        GetFile(
                            location=location,
                            offset=current_offset,
                            limit=min(chunk_size, file_size - current_offset)
                        )
                    )
                    tasks.append(task)
                
                # Download all chunks in parallel
                if tasks:
                    chunks = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Write chunks in correct order
                    for i, chunk in enumerate(chunks):
                        if isinstance(chunk, Exception):
                            print(f"⚠️ Chunk download failed: {chunk}")
                            return None
                        
                        f.seek(chunk_offsets[i])
                        f.write(chunk.bytes)
                        downloaded_size += len(chunk.bytes)
                    
                    # Update progress
                    if time.time() - last_update > 2:
                        try:
                            percent = (downloaded_size / file_size) * 100
                            elapsed = time.time() - start_time
                            speed = downloaded_size / elapsed if elapsed > 0 else 0
                            eta = (file_size - downloaded_size) / speed if speed > 0 else 0
                            
                            await sts.edit(
                                f"📥 **Downloading (8x Parallel):** **`{os.path.basename(file_path)}`**\n\n"
                                f"📊 **Progress:** {percent:.1f}%\n"
                                f"⚡ **Speed:** {humanbytes(int(speed))}/s\n"
                                f"⏱️ **ETA:** {int(eta)}s"
                            )
                            last_update = time.time()
                        except:
                            pass
                
                offset += concurrent_chunks * chunk_size
        
        print(f"✅ Optimized download completed!")
        return file_path
        
    except Exception as e:
        print(f"⚠️ Optimized download failed: {e}")
        import traceback
        traceback.print_exc()
        return None

@Client.on_message(filters.private & filters.command("megaup") & filters.user(ADMIN))
async def mega_uploader(bot, msg):
    reply = msg.reply_to_message
    if not reply:
        return await msg.reply_text("📌 Please reply to a file (video, audio, doc) to upload to Mega.nz.")
    
    media = reply.document or reply.video or reply.audio
    if not media:
        return await msg.reply_text("❌ Unsupported file type.")

    og_media = getattr(reply, reply.media.value)
    filename = og_media.file_name or "uploaded_file"
    
    # Initial download message
    sts = await msg.reply_text(f"📥 **Downloading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 1: Download file from Telegram
    os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_LOCATION, filename)
    
    # Try optimized parallel download first
    downloaded_path = await optimized_download(bot, reply, file_path, sts)
    
    # Fallback to standard pyrogram download
    if not downloaded_path:
        print("⚠️ Falling back to standard Pyrogram download")
        c_time = time.time()
        downloaded_path = await reply.download(
            file_name=file_path,
            progress=progress_message,
            progress_args=(f"📥 **Downloading:** **`{filename}`**", sts, c_time)
        )

    filesize = humanbytes(og_media.file_size)

    # Step 2: Load Mega credentials
    login_path = os.path.join(os.path.dirname(__file__), "mega_login.txt")
    try:
        with open(login_path, "r") as f:
            creds = f.read().strip()
        email, password = creds.split(":", 1)
    except Exception as e:
        return await sts.edit(f"❌ Failed to load mega_login.txt: {e}")

    # Step 3: Create rclone config file
    rclone_config_path = "/root/.config/rclone/"
    os.makedirs(rclone_config_path, exist_ok=True)
    obscured_pass = os.popen(f"rclone obscure \"{password.strip()}\"").read().strip()
    with open(os.path.join(rclone_config_path, "rclone.conf"), "w") as f:
        f.write(f"[mega]\ntype = mega\nuser = {email.strip()}\npass = {obscured_pass}\n")

    # Step 4: Show Uploading Status in Bot (Static)
    await sts.edit(f"☁️ **Uploading:** **`{filename}`**\n\n🔁 Please wait...")

    # Step 5: Upload to Mega and stream output to Colab logs
    cmd = [
        "rclone", "copy", downloaded_path, "mega:", "--progress", "--stats-one-line",
        "--stats=1s", "--log-level", "INFO", "--config", os.path.join(rclone_config_path, "rclone.conf")
    ]

    print(f"🔄 Uploading '{filename}' to Mega.nz...\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Print rclone progress in Colab logs
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(line.strip())

    proc.wait()

    # Step 6: Get Mega Storage Info (via --json)
    try:
        about_output = os.popen(f"rclone about mega: --json --config {os.path.join(rclone_config_path, 'rclone.conf')}").read()
        stats = json.loads(about_output)

        total_bytes = stats.get("total", 0)
        used_bytes = stats.get("used", 0)
        free_bytes = stats.get("free", 0)

        total = humanbytes(total_bytes)
        used = humanbytes(used_bytes)
        free = humanbytes(free_bytes)

        used_pct = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0

        # Draw storage bar
        full_blocks = used_pct // 10
        empty_blocks = 10 - full_blocks
        bar = "█" * full_blocks + "░" * empty_blocks

    except Exception as e:
        total = used = free = "Unknown"
        used_pct = 0
        bar = "░" * 10

    # Step 7: Final Message with Storage Info and Delete Button
    if proc.returncode == 0:
        final_text = (
            f"✅ **Upload Complete to Mega.nz!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"💽 **Size:** {filesize}\n\n"
            f"📦 **Mega Storage**\n"
            f"Used: `{used}` / Total: `{total}`\n"
            f"{bar} `{used_pct}%` used"
        )
    else:
        final_text = "❌ Upload failed. Please check your credentials or try again later."

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Delete", callback_data="delmegamsg")]
    ])

    await sts.edit(final_text, reply_markup=btn)

    # Step 8: Cleanup
    try:
        os.remove(downloaded_path)
    except:
        pass


@Client.on_callback_query(filters.regex("delmegamsg"))
async def delete_megamsg(bot, query: CallbackQuery):
    try:
        await query.message.delete()
    except:
        pass
    await query.answer("🗑️ Message deleted", show_alert=False)
