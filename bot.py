from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import os
import threading
import asyncio
import uuid
from flask import Flask
from yt_dlp import YoutubeDL

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = Client("yt_dlp_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Flask app for Render health check
health_app = Flask("health")
@health_app.route("/")
def health_check():
    return "Bot is alive!", 200

def run_health():
    health_app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_health, daemon=True).start()

video_cache = {}  # Store URL by message ID


@app.on_message(filters.command("start"))
def start(client, message):
    message.reply(
        "👋 **Welcome to YouTube Downloader Bot!**\n\n"
        "📥 Send a YouTube link to download:\n"
        "🎬 Video (up to 1080p)\n"
        "🎧 Audio (MP3)\n\n"
        "Let’s get started! 🚀"
    )


@app.on_message(filters.text & ~filters.command("start"))
def handle_link(client, message):
    url = message.text.strip()
    if not url.startswith("http"):
        message.reply("❌ Please send a valid YouTube link.")
        return

    video_cache[str(message.id)] = url

    buttons = [
        [InlineKeyboardButton("📺 720p", callback_data=f"720p|{message.id}")],
        [InlineKeyboardButton("📺 480p", callback_data=f"480p|{message.id}")],
        [InlineKeyboardButton("📺 360p", callback_data=f"360p|{message.id}")],
        [InlineKeyboardButton("🎵 MP3 (Audio)", callback_data=f"mp3|{message.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    message.reply("🎞 **Choose quality**:", reply_markup=reply_markup)


@app.on_callback_query()
def download_handler(client, callback_query: CallbackQuery):
    quality, msg_id = callback_query.data.split("|")
    url = video_cache.pop(msg_id, None)

    if not url:
        callback_query.message.edit_text("⚠️ Session expired. Please resend the link.")
        return

    callback_query.answer("Downloading started...")

    unique_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_FOLDER, f"{unique_id}.%(ext)s")

    ydl_opts = {}

    if quality == "mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        ydl_opts = {
            'format': f'bestvideo[height<={quality[:-1]}]+bestaudio/best',
            'outtmpl': output_path,
            'merge_output_format': 'mp4'
        }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if quality == "mp3":
                file_path = os.path.splitext(file_path)[0] + ".mp3"

        caption = f"✅ Download complete: {info.get('title', 'Your file')}"
        if quality == "mp3":
            client.send_audio(callback_query.message.chat.id, audio=file_path, title=info.get('title'))
        else:
            client.send_video(callback_query.message.chat.id, video=file_path, caption=caption)

        os.remove(file_path)
        callback_query.message.edit_text("✅ Sent successfully!")

    except Exception as e:
        callback_query.message.edit_text(f"❌ Failed to download:\n`{e}`")
        print("[ERROR]", e)

app.run()
