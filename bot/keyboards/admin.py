from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_admin_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📊 Bot Stats"),
        KeyboardButton(text="👥 Users"),
    )
    builder.row(
        KeyboardButton(text="📋 Manage Tasks"),
        KeyboardButton(text="💸 Withdrawals"),
    )
    builder.row(
        KeyboardButton(text="💳 Deposits"),
        KeyboardButton(text="📢 Channels"),
    )
    builder.row(
        KeyboardButton(text="🎫 Support Tickets"),
        KeyboardButton(text="📣 Broadcast"),
    )
    builder.row(
        KeyboardButton(text="💰 Referral Settings"),
    )
    builder.row(KeyboardButton(text="🔙 Exit Admin"))
    return builder.as_markup(resize_keyboard=True)


def get_task_actions(task_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "❌ বন্ধ করুন" if is_active else "✅ চালু করুন"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_task:{task_id}:{int(not is_active)}"),
        InlineKeyboardButton(text="✏️ দাম পরিবর্তন", callback_data=f"admin_edit_price:{task_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑 মুছুন", callback_data=f"admin_delete_task:{task_id}"),
    )
    return builder.as_markup()


def get_task_delete_confirm(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ হ্যাঁ, মুছুন", callback_data=f"admin_confirm_delete:{task_id}"),
        InlineKeyboardButton(text="❌ না", callback_data="admin_cancel_delete"),
    )
    return builder.as_markup()


def get_task_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 সাবস্ক্রাইব", callback_data="tasktype:subscribe"),
        InlineKeyboardButton(text="❤️ লাইক", callback_data="tasktype:like"),
    )
    builder.row(
        InlineKeyboardButton(text="🔁 রিপোস্ট", callback_data="tasktype:repost"),
        InlineKeyboardButton(text="⭐ কাস্টম", callback_data="tasktype:custom"),
    )
    return builder.as_markup()


def get_user_task_review(user_task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ অনুমোদন", callback_data=f"approve_task:{user_task_id}"),
        InlineKeyboardButton(text="❌ বাতিল", callback_data=f"reject_task:{user_task_id}"),
    )
    return builder.as_markup()


def get_ticket_actions(ticket_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💬 উত্তর ও বন্ধ করুন", callback_data=f"reply_ticket:{ticket_id}"),
        InlineKeyboardButton(text="🔒 বন্ধ করুন", callback_data=f"close_ticket:{ticket_id}"),
    )
    return builder.as_markup()


def get_withdrawal_actions(tx_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ অনুমোদন", callback_data=f"approve_withdrawal:{tx_id}"),
        InlineKeyboardButton(text="❌ বাতিল", callback_data=f"reject_withdrawal:{tx_id}"),
    )
    return builder.as_markup()


def get_deposit_actions(tx_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ অনুমোদন", callback_data=f"approve_deposit:{tx_id}"),
        InlineKeyboardButton(text="❌ বাতিল", callback_data=f"reject_deposit:{tx_id}"),
    )
    return builder.as_markup()


def get_channel_remove_keyboard(channels) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.row(InlineKeyboardButton(
            text=f"🗑 মুছুন: {ch.channel_name}",
            callback_data=f"remove_channel:{ch.id}"
        ))
    return builder.as_markup()


def get_user_manage_keyboard(user_db_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_blocked:
        builder.row(InlineKeyboardButton(text="✅ আনব্লক করুন", callback_data=f"admin_unblock:{user_db_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 ব্লক করুন", callback_data=f"admin_block:{user_db_id}"))
    builder.row(InlineKeyboardButton(text="💰 ব্যালেন্স পরিবর্তন", callback_data=f"admin_adjust_balance:{user_db_id}"))
    return builder.as_markup()
