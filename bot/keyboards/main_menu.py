from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="💰 ব্যালেন্স"),
        KeyboardButton(text="📋 কাজ দেখুন"),
    )
    builder.row(
        KeyboardButton(text="📊 আমার কাজ"),
        KeyboardButton(text="📦 আমার অর্ডার"),
    )
    builder.row(
        KeyboardButton(text="✏️ কাজ তৈরি করুন"),
        KeyboardButton(text="🤝 রেফারেল"),
    )
    builder.row(
        KeyboardButton(text="💳 ডিপোজিট"),
        KeyboardButton(text="🏧 উইথড্র"),
    )
    builder.row(
        KeyboardButton(text="📜 ইতিহাস"),
        KeyboardButton(text="🆘 সাপোর্ট"),
    )
    if is_admin:
        builder.row(KeyboardButton(text="⚙️ অ্যাডমিন প্যানেল"))
    return builder.as_markup(resize_keyboard=True)


def get_main_menu_for(telegram_id: int) -> ReplyKeyboardMarkup:
    """Helper — checks admin status internally so callers don't need to import settings."""
    from config import settings
    return get_main_menu(is_admin=telegram_id in settings.admin_ids)


def get_back_button() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🔙 মেনুতে ফিরুন"))
    return builder.as_markup(resize_keyboard=True)


def get_profile_inline(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 আমার পরিসংখ্যান", callback_data=f"profile_stats:{user_id}"))
    builder.row(InlineKeyboardButton(text="📜 লেনদেনের ইতিহাস", callback_data=f"tx_history:{user_id}"))
    return builder.as_markup()
