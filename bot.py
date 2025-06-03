from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pytube import YouTube
import os
import threading
from flask import Flask

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = Client("yt_quality_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

video_cache = {}

# Flask app for health checks
health_app = Flask("health")

@health_app.route("/")
def health_check():
    return "Bot is running!", 200

def run_health():
    health_app.run(host="0.0.0.0", port=8080)

# Start Flask health server in a separate daemon thread
threading.Thread(target=run_health, daemon=True).start()

@app.on_message(filters.command("start"))
def start(client, message):
    message.reply(
        "👋 **Welcome to YouTube Downloader Bot!**\n\n"
        "📥 Send a YouTube link and I'll let you choose:\n"
        "🎬 Video quality (from 1080p to 240p)\n"
        "🎧 MP3 audio download\n\n"
        "Let’s go! 🚀"
    )

@app.on_message(filters.text & ~filters.command("start"))
def handle_video(client, message):
    url = message.text.strip()
    if not url.startswith("http"):
        message.reply("❌ Please send a valid YouTube URL.")
        return

    try:
        yt = YouTube(url)
        video_cache[str(message.id)] = yt

        streams = yt.streams.filter(progressive=True, file_extension='mp4')
        resolutions = sorted({s.resolution for s in streams if s.resolution}, reverse=True)

        buttons = [[InlineKeyboardButton(f"📺 {res}", callback_data=f"{res}|{message.id}")] for res in resolutions]
        buttons.append([InlineKeyboardButton("🎵 MP3 (Audio)", callback_data=f"mp3|{message.id}")])
        markup = InlineKeyboardMarkup(buttons)

        message.reply(f"🎬 **{yt.title}**\n\n📽 Choose your quality:", reply_markup=markup)

    except Exception as e:
        message.reply(f"⚠️ Failed to process video:\n`{e}`")

@app.on_callback_query()
def download_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    format_choice, msg_id = data.split("|")

    yt = video_cache.pop(msg_id, None)
    if not yt:
        callback_query.message.edit_text("⚠️ Session expired. Please send the link again.")
        return

    progress_message = callback_query.message
    callback_query.answer("Starting download...")
    callback_query.message.edit_reply_markup(None)

    def on_download_progress(stream, chunk, bytes_remaining):
        total_size = stream.filesize
        bytes_downloaded = total_size - bytes_remaining
        progress_percent = int(bytes_downloaded / total_size * 100)
        try:
            progress_message.edit_text(f"⬇️ Downloading... {progress_percent}%")
        except:
            pass

    yt.register_on_progress_callback(on_download_progress)

    try:
        if format_choice == "mp3":
            stream = yt.streams.filter(only_audio=True).first()
            file_path = stream.download(output_path=DOWNLOAD_FOLDER)
            base, _ = os.path.splitext(file_path)
            mp3_file = base + ".mp3"
            os.rename(file_path, mp3_file)

            def upload_progress(current, total):
                percent = int(current * 100 / total)
                try:
                    progress_message.edit_text(f"⬆️ Uploading audio... {percent}%")
                except:
                    pass

            client.send_audio(callback_query.message.chat.id, audio=mp3_file, title=yt.title, progress=upload_progress)
            os.remove(mp3_file)

        else:
            stream = yt.streams.filter(res=format_choice, progressive=True, file_extension='mp4').first()
            if not stream:
                callback_query.message.edit_text(f"⚠️ {format_choice} not available.")
                return
            file_path = stream.download(output_path=DOWNLOAD_FOLDER)

            def upload_progress(current, total):
                percent = int(current * 100 / total)
                try:
                    progress_message.edit_text(f"⬆️ Uploading video... {percent}%")
                except:
                    pass

            client.send_video(callback_query.message.chat.id, video=file_path, caption=f"✅ {yt.title} ({format_choice})", progress=upload_progress)
            os.remove(file_path)

        progress_message.edit_text("✅ Download complete!")
    except Exception as e:
        progress_message.edit_text(f"❌ Error during download:\n`{e}`")

app.run()
