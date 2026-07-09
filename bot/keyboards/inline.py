from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─── Task Category / Subcategory Data ────────────────────────────────────────
# Each task entry: (display_name, minimum_reward_in_BDT)

TASK_CATEGORIES: dict[str, dict] = {
    "fb": {
        "name": "🔵 Facebook",
        "tasks": [
            ("Post Like",                2),
            ("Post Comment",             2),
            ("Post Share",               2),
            ("Like + Comment",           3),
            ("Like + Share",             3),
            ("Like + Comment + Share",   6),
            ("Page Follow",              2),
            ("Profile Follow",           2),
            ("Group Join",               2),
            ("Reel Like",                2),
            ("Reel Comment",             2),
            ("Reel Share",               3),
        ],
    },
    "yt": {
        "name": "🔴 YouTube",
        "tasks": [
            ("Subscribe",                    2),
            ("Like",                         2),
            ("Comment",                      2),
            ("Share",                        2),
            ("Like + Comment",               3),
            ("Like + Comment + Subscribe",   6),
            ("Watch 1-2 Min",                2),
            ("Watch 1-5 Min",                3),
            ("Watch 1-10 Min",               6),
            ("Watch 1-20 Min",              15),
            ("Watch + Subscribe",            7),
            ("Watch + Like",                 3),
            ("Watch + Comment",              3),
            ("Watch + Like + Subscribe",    10),
        ],
    },
    "tt": {
        "name": "⚫ TikTok",
        "tasks": [
            ("Video Like",               2),
            ("Follow",                   3),
            ("Comment",                  2),
            ("Share",                    2),
            ("Like + Follow",            5),
            ("Like + Comment",           3),
            ("Like + Comment + Follow",  7),
            ("Watch Video",              1),
            ("Watch + Like",             2),
            ("Watch + Follow",           3),
        ],
    },
    "tg": {
        "name": "🟦 Telegram",
        "tasks": [
            ("Channel Join",  2),
            ("Group Join",    2),
            ("Reaction",      1),
            ("Post View",     1),
        ],
    },
    "web": {
        "name": "🌐 Website",
        "tasks": [
            ("Website Visit",   3),
            ("Registration",    3),
            ("Survey",         10),
            ("App Install",     5),
            ("App Review",      2),
        ],
    },
}

PROOF_TYPES: dict[str, str] = {
    "screenshot": "📸 স্ক্রিনশট",
    "text":       "📝 টেক্সট / লিংক",
    "video":      "🎥 ভিডিও প্রমাণ",
    "any":        "✅ যেকোনো প্রমাণ",
}


def get_task_min_reward(category_key: str, subcategory_index: int) -> int:
    """Return the minimum reward (BDT) for a given subcategory."""
    tasks = TASK_CATEGORIES.get(category_key, {}).get("tasks", [])
    if subcategory_index < len(tasks):
        return tasks[subcategory_index][1]
    return 1


# ─── Category Keyboard ────────────────────────────────────────────────────────

def get_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, data in TASK_CATEGORIES.items():
        builder.row(InlineKeyboardButton(text=data["name"], callback_data=f"cat:{key}"))
    builder.row(InlineKeyboardButton(text="❌ বাতিল", callback_data="task_cancel"))
    return builder.as_markup()


# ─── Subcategory Keyboard ─────────────────────────────────────────────────────

def get_subcategory_keyboard(category_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    tasks = TASK_CATEGORIES[category_key]["tasks"]

    row_buf: list[InlineKeyboardButton] = []
    for idx, (task_name, _min) in enumerate(tasks):
        btn = InlineKeyboardButton(text=task_name, callback_data=f"sub:{idx}")
        row_buf.append(btn)
        if len(row_buf) == 2:
            builder.row(*row_buf)
            row_buf = []
    if row_buf:
        builder.row(*row_buf)

    builder.row(InlineKeyboardButton(text="🔙 পেছনে", callback_data="back_to_categories"))
    builder.row(InlineKeyboardButton(text="❌ বাতিল",  callback_data="task_cancel"))
    return builder.as_markup()


# ─── Proof Type Keyboard ──────────────────────────────────────────────────────

def get_proof_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in PROOF_TYPES.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"proof:{key}"))
    builder.row(InlineKeyboardButton(text="❌ বাতিল", callback_data="task_cancel"))
    return builder.as_markup()


# ─── Summary / Confirm Keyboard ───────────────────────────────────────────────

def get_task_summary_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ কাজ তৈরি করুন", callback_data="task_confirm"),
        InlineKeyboardButton(text="❌ বাতিল",          callback_data="task_cancel"),
    )
    return builder.as_markup()


# ─── Generic Keyboards ────────────────────────────────────────────────────────

def get_advertiser_review_keyboard(user_task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ অনুমোদন করুন", callback_data=f"adv_approve:{user_task_id}"),
        InlineKeyboardButton(text="❌ বাতিল করুন",   callback_data=f"adv_reject:{user_task_id}"),
    )
    return builder.as_markup()


def get_cancel_keyboard(callback_data: str = "cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ বাতিল করুন", callback_data=callback_data))
    return builder.as_markup()


def get_confirm_keyboard(confirm_data: str, cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ নিশ্চিত করুন", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ বাতিল",        callback_data=cancel_data),
    )
    return builder.as_markup()


def get_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ কাজ জমা দিন", callback_data=f"submit_task:{task_id}"))
    return builder.as_markup()


def get_deposit_methods() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💚 নগদ — Personal",           callback_data="deposit:nagad"))
    builder.row(InlineKeyboardButton(text="🟡 Binance (BEP20 — USDT)",   callback_data="deposit:binance"))
    builder.row(InlineKeyboardButton(text="❌ বাতিল করুন",               callback_data="cancel"))
    return builder.as_markup()


def get_withdraw_methods() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📱 বিকাশ (bKash) — Personal", callback_data="withdraw:bkash"))
    builder.row(InlineKeyboardButton(text="💚 নগদ (Nagad) — Personal",   callback_data="withdraw:nagad"))
    builder.row(InlineKeyboardButton(text="❌ বাতিল করুন",               callback_data="cancel"))
    return builder.as_markup()
