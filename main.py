import os
import sys
import time
import logging
import threading
import urllib.parse

from flask import Flask, send_from_directory, abort
import telebot
from telebot import types

from config import BOT_TOKEN, DOWNLOAD_DIR, FLASK_PORT, BASE_URL, MESSAGES
from downloader import (
    download_video,
    download_audio,
    make_progress_hook,
    build_progress_bar,
    format_speed,
    format_size,
    format_eta,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error(MESSAGES["error_no_token"])
    sys.exit(1)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

user_modes: dict[int, str] = {}

UPDATE_INTERVAL = 3


@app.route("/")
def index():
    return "OK", 200


@app.route("/downloads/<path:filename>")
def serve_file(filename):
    safe_dir = os.path.abspath(DOWNLOAD_DIR)
    file_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, filename))
    if not file_path.startswith(safe_dir):
        abort(403)
    return send_from_directory(safe_dir, filename, as_attachment=True)


def make_download_url(filepath: str) -> str:
    filename = os.path.basename(filepath)
    encoded = urllib.parse.quote(filename)
    return f"{BASE_URL}/downloads/{encoded}"


def make_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎬 تحميل فيديو", "🎵 تحميل صوت")
    markup.row("❓ مساعدة")
    return markup


def build_progress_message(percent: float, downloaded, total, speed, eta) -> str:
    bar = build_progress_bar(percent)
    lines = [
        f"⏳ جاري التحميل...",
        f"{bar} {percent:.1f}%",
        f"",
        f"⚡ السرعة: {format_speed(speed)}",
        f"⏱ الوقت المتبقي: {format_eta(eta)}",
        f"📥 المحمّل: {format_size(downloaded)} / {format_size(total)}",
    ]
    return "\n".join(lines)


def create_telegram_progress_hook(chat_id: int, message_id: int):
    last_update = [0.0]
    last_text = [""]

    def on_progress(percent, downloaded, total, speed, eta):
        now = time.time()
        if now - last_update[0] < UPDATE_INTERVAL:
            return
        text = build_progress_message(percent, downloaded, total, speed, eta)
        if text == last_text[0]:
            return
        try:
            bot.edit_message_text(text, chat_id, message_id)
            last_text[0] = text
            last_update[0] = now
        except Exception:
            pass

    return make_progress_hook(on_progress)


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    user_modes.pop(message.chat.id, None)
    bot.send_message(message.chat.id, MESSAGES["start"], reply_markup=make_main_keyboard())


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    bot.send_message(message.chat.id, MESSAGES["help"])


@bot.message_handler(func=lambda m: m.text == "❓ مساعدة")
def btn_help(message: types.Message):
    bot.send_message(message.chat.id, MESSAGES["help"])


@bot.message_handler(func=lambda m: m.text == "🎬 تحميل فيديو")
def btn_video(message: types.Message):
    user_modes[message.chat.id] = "video"
    bot.send_message(message.chat.id, MESSAGES["send_link"])


@bot.message_handler(func=lambda m: m.text == "🎵 تحميل صوت")
def btn_audio(message: types.Message):
    user_modes[message.chat.id] = "audio"
    bot.send_message(message.chat.id, MESSAGES["send_link"])


def process_download(url: str, chat_id: int, mode: str, status_msg_id: int):
    progress_hook = create_telegram_progress_hook(chat_id, status_msg_id)
    filepath = None
    try:
        if mode == "audio":
            filepath = download_audio(url, progress_hook=progress_hook)
        else:
            filepath = download_video(url, progress_hook=progress_hook)

        if not filepath:
            bot.edit_message_text(MESSAGES["error_general"], chat_id, status_msg_id)
            return

        download_url = make_download_url(filepath)
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        filename = os.path.basename(filepath)

        text = (
            f"{MESSAGES['done']}\n\n"
            f"📁 الملف: {filename}\n"
            f"📦 الحجم: {size_mb:.1f} MB\n\n"
            f"🔗 {download_url}"
        )
        bot.edit_message_text(text, chat_id, status_msg_id)

    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        error_text = MESSAGES["error_general"]
        if "Unsupported URL" in str(e) or "No video formats" in str(e):
            error_text = MESSAGES["error_invalid"]
        try:
            bot.edit_message_text(error_text, chat_id, status_msg_id)
        except Exception:
            bot.send_message(chat_id, error_text)
    finally:
        user_modes.pop(chat_id, None)


@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_url(message: types.Message):
    url = message.text.strip()
    chat_id = message.chat.id
    mode = user_modes.get(chat_id, "video")

    status_msg = bot.send_message(chat_id, "⏳ جاري التحميل...")
    t = threading.Thread(
        target=process_download,
        args=(url, chat_id, mode, status_msg.message_id),
        daemon=True,
    )
    t.start()


@bot.message_handler(func=lambda m: True)
def handle_other(message: types.Message):
    bot.send_message(
        message.chat.id,
        "أرسل رابط الفيديو مباشرة أو اضغط على أحد الأزرار أدناه.",
        reply_markup=make_main_keyboard(),
    )


def run_bot():
    logger.info("Clearing any existing webhook...")
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        logger.warning(f"Could not remove webhook: {e}")
    logger.info("Telegram bot polling started.")
    bot.infinity_polling(logger_level=logging.INFO, allowed_updates=["message"])


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    logger.info(f"Flask server running at {BASE_URL}")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
