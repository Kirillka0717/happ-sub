import json
import os
import re
import time
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Вставь токен своего бота
BOT_TOKEN = "9028698207:AAHuHt32rnGN8ddEF1P7v3FnoN-qWHULrdQ"

# ID администратора
ADMIN_ID = 6912614452

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
BAN_FILE = "banned.json"


# --- РАБОТА С БАЗОЙ БАНОВ ---
def load_banned() -> dict:
    if not os.path.exists(BAN_FILE):
        return {}
    try:
        with open(BAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_banned(data: dict):
    with open(BAN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_banned(user_id: int) -> tuple[bool, str]:
    banned = load_banned()
    user_str = str(user_id)
    if user_str not in banned:
        return False, ""

    until = banned[user_str].get("until")
    if until is None:
        return True, "🚫 Вы заблокированы навсегда в этом боте."

    now = time.time()
    if now < until:
        until_str = datetime.fromtimestamp(until).strftime("%d.%m.%Y %H:%M")
        return True, f"⏳ Вы временно заблокированы в этом боте до {until_str}."
    else:
        del banned[user_str]
        save_banned(banned)
        return False, ""


def make_admin_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    btn_perm = InlineKeyboardButton("🚫 Навсегда", callback_data=f"ban_perm:{target_user_id}")
    btn_hour = InlineKeyboardButton("⏳ На 1 час", callback_data=f"ban_hour:{target_user_id}")
    markup.row(btn_perm, btn_hour)
    return markup


def make_unban_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    btn_unban = InlineKeyboardButton("🟢 Разбанить", callback_data=f"unban:{target_user_id}")
    markup.row(btn_unban)
    return markup


def get_sender_header(message) -> str:
    user = message.from_user
    name = user.first_name + (f" {user.last_name}" if user.last_name else "")
    username = f"(@{user.username})" if user.username else "(нет username)"
    # Скрытый или явный тег с ID для парсинга ответов
    return f"✉️ <b>Сообщение от:</b> {name} {username} [<code>{user.id}</code>]\n\n"


def extract_user_id(reply_message) -> int | None:
    """Извлекает ID пользователя из сообщения, на которое отвечает админ."""
    text_to_search = reply_message.text or reply_message.caption or ""
    # Ищем цифры внутри квадратных скобок [12345678]
    match = re.search(r"\[(?:<code>)?(\d+)(?:<\/code>)?\]", text_to_search)
    if match:
        return int(match.group(1))
    return None


# --- КНОПКИ БАНА / РАЗБАНА ---
@bot.callback_query_handler(func=lambda call: True)
def handle_ban_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "У вас нет прав.", show_alert=True)
        return

    data = call.data
    action, target_id_str = data.split(":")
    target_id = int(target_id_str)
    banned = load_banned()

    if action == "ban_perm":
        banned[str(target_id)] = {"until": None}
        save_banned(banned)
        try:
            bot.send_message(target_id, "🚫 Вы заблокированы навсегда в этом боте.")
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Пользователь забанен навсегда.")
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=make_unban_keyboard(target_id)
        )

    elif action == "ban_hour":
        until_ts = time.time() + 3600
        banned[str(target_id)] = {"until": until_ts}
        save_banned(banned)
        until_str = datetime.fromtimestamp(until_ts).strftime("%H:%M")
        try:
            bot.send_message(target_id, f"⏳ Вы временно заблокированы в боте на 1 час (до {until_str}).")
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Пользователь забанен на 1 час.")
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=make_unban_keyboard(target_id)
        )

    elif action == "unban":
        if str(target_id) in banned:
            del banned[str(target_id)]
            save_banned(banned)

        try:
            bot.send_message(target_id, "✅ Вы были разблокированы в этом боте.")
        except Exception:
            pass

        bot.answer_callback_query(call.id, "Пользователь разблокирован.")
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=make_admin_keyboard(target_id)
        )


# --- ОТВЕТ АДМИНИСТРАТОРА (REPLY) ---
@bot.message_handler(func=lambda msg: msg.from_user.id == ADMIN_ID and msg.reply_to_message is not None)
def handle_admin_reply(message):
    target_id = extract_user_id(message.reply_to_message)
    if not target_id:
        bot.reply_to(message, "⚠️ Не удалось определить ID пользователя из этого сообщения.")
        return

    try:
        # Отправляем копию ответа админа пользователю
        bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.message_id)
        bot.reply_to(message, "✅ Ответ отправлен пользователю!")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка отправки (возможно, пользователь заблокировал бота): {e}")


# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ---
@bot.message_handler(commands=["start"])
def send_welcome(message):
    banned, ban_msg = is_banned(message.from_user.id)
    if banned:
        bot.reply_to(message, ban_msg)
        return
    bot.reply_to(message, "Здравствуйте! Отправьте сюда текст или фото, и мы ответим вам.")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    if message.from_user.id == ADMIN_ID:
        return

    banned, ban_msg = is_banned(message.from_user.id)
    if banned:
        bot.reply_to(message, ban_msg)
        return

    header = get_sender_header(message)
    markup = make_admin_keyboard(message.from_user.id)
    try:
        bot.send_message(ADMIN_ID, f"{header}{message.text}", reply_markup=markup)
        bot.reply_to(message, "Ваше сообщение успешно отправлено!")
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    if message.from_user.id == ADMIN_ID:
        return

    banned, ban_msg = is_banned(message.from_user.id)
    if banned:
        bot.reply_to(message, ban_msg)
        return

    header = get_sender_header(message)
    caption = f"{header}{message.caption}" if message.caption else header
    photo_id = message.photo[-1].file_id
    markup = make_admin_keyboard(message.from_user.id)
    try:
        bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=markup)
        bot.reply_to(message, "Фотография получена и передана!")
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")


@bot.message_handler(content_types=["document", "audio", "voice", "video", "video_note", "sticker"])
def handle_other(message):
    if message.from_user.id == ADMIN_ID:
        return

    banned, ban_msg = is_banned(message.from_user.id)
    if banned:
        bot.reply_to(message, ban_msg)
        return

    header = get_sender_header(message)
    markup = make_admin_keyboard(message.from_user.id)
    try:
        # Для медиа сначала отправляем шапку с кнопками бана
        bot.send_message(ADMIN_ID, header, reply_markup=markup)
        bot.copy_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        bot.reply_to(message, "Сообщение получено и передано!")
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")


if __name__ == "__main__":
    print("Бот успешно запущен...")
    bot.infinity_polling()
