from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries
from bot.filters import IsAdmin
from bot.keyboards.admin import get_user_manage_keyboard
from config import settings

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
C = settings.CURRENCY_SYMBOL


class UserSearchStates(StatesGroup):
    searching = State()


class BalanceAdjustStates(StatesGroup):
    entering_amount = State()


@router.message(F.text == "👥 Users")
async def list_users(message: Message, session: AsyncSession) -> None:
    total = await UserQueries.get_total_count(session)
    today = await UserQueries.get_today_registrations(session)
    users = await UserQueries.get_all(session, limit=10)

    lines = [
        f"👥 <b>ব্যবহারকারী তালিকা</b>\n",
        f"মোট: <b>{total}</b> | আজ: <b>+{today}</b>\n",
        "সাম্প্রতিক ১০ জন:",
    ]
    for u in users:
        blocked_str = " 🚫" if u.is_blocked else ""
        username_str = f"@{u.username}" if u.username else "—"
        lines.append(
            f"• <code>{u.telegram_id}</code> {u.full_name}{blocked_str}"
            f" — {C}{u.balance:,.0f}"
        )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 ব্যবহারকারী খুঁজুন", callback_data="admin_search_user"))

    await message.answer(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_search_user")
async def search_user_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserSearchStates.searching)
    await callback.message.answer(
        "🔍 <b>ব্যবহারকারী খুঁজুন</b>\n\nটেলিগ্রাম ID বা @ইউজারনেম পাঠান:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserSearchStates.searching)
async def search_user(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    query = message.text.strip().lstrip("@")

    user = None
    try:
        telegram_id = int(query)
        user = await UserQueries.get_by_telegram_id(session, telegram_id)
    except ValueError:
        all_users = await UserQueries.get_all(session, limit=100000)
        user = next((u for u in all_users if u.username and u.username.lower() == query.lower()), None)

    if not user:
        await message.answer("❌ ব্যবহারকারী পাওয়া যায়নি।")
        return

    await _send_user_profile(message, session, user)


async def _send_user_profile(message, session, user):
    referrals = await UserQueries.get_referrals(session, user.id)
    username_str = f"@{user.username}" if user.username else "—"
    status_str = "🚫 ব্লক" if user.is_blocked else "✅ সক্রিয়"

    text = (
        f"👤 <b>ব্যবহারকারীর বিবরণ</b>\n\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"📛 নাম: {user.full_name}\n"
        f"🔗 ইউজারনেম: {username_str}\n"
        f"📅 যোগদান: {user.created_at.strftime('%d %b %Y')}\n"
        f"🕐 শেষ সক্রিয়: {user.last_active.strftime('%d %b %Y %H:%M')}\n\n"
        f"💰 ব্যালেন্স: <b>{C}{user.balance:,.0f}</b>\n"
        f"📈 মোট আয়: {C}{user.total_earned:,.0f}\n"
        f"🏧 মোট উত্তোলন: {C}{user.total_withdrawn:,.0f}\n"
        f"👥 রেফারেল: {len(referrals)}\n\n"
        f"অবস্থা: {status_str}"
    )

    await message.answer(
        text,
        reply_markup=get_user_manage_keyboard(user.id, user.is_blocked),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_block:"))
async def block_user(callback: CallbackQuery, session: AsyncSession) -> None:
    user_db_id = int(callback.data.split(":")[1])
    await UserQueries.block_user(session, user_db_id, True)
    user = await UserQueries.get_by_id(session, user_db_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_user_manage_keyboard(user_db_id, True)
    )
    await callback.answer("🚫 ব্লক করা হয়েছে!", show_alert=True)
    if user:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                "🚫 আপনার অ্যাকাউন্ট ব্লক করা হয়েছে। বিস্তারিত জানতে সাপোর্টে যোগাযোগ করুন।",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("admin_unblock:"))
async def unblock_user(callback: CallbackQuery, session: AsyncSession) -> None:
    user_db_id = int(callback.data.split(":")[1])
    await UserQueries.block_user(session, user_db_id, False)
    user = await UserQueries.get_by_id(session, user_db_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_user_manage_keyboard(user_db_id, False)
    )
    await callback.answer("✅ আনব্লক করা হয়েছে!", show_alert=True)
    if user:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                "✅ আপনার অ্যাকাউন্টের ব্লক তুলে নেওয়া হয়েছে।",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("admin_adjust_balance:"))
async def adjust_balance_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_db_id = int(callback.data.split(":")[1])
    await state.set_state(BalanceAdjustStates.entering_amount)
    await state.update_data(user_db_id=user_db_id)
    await callback.message.answer(
        f"💰 <b>ব্যালেন্স পরিবর্তন</b>\n\n"
        f"পরিমাণ লিখুন:\n"
        f"• যোগ করতে: <code>100</code>\n"
        f"• বিয়োগ করতে: <code>-100</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BalanceAdjustStates.entering_amount)
async def do_balance_adjust(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    await state.clear()

    try:
        amount = float(message.text.replace(",", "").strip())
    except ValueError:
        await message.answer("❌ ভুল পরিমাণ। সংখ্যা লিখুন (যেমন: 100 বা -50):")
        return

    user = await UserQueries.get_by_id(session, user_db_id)
    if not user:
        await message.answer("❌ ব্যবহারকারী পাওয়া যায়নি।")
        return

    await UserQueries.update_balance(session, user_db_id, amount)

    sign = "+" if amount >= 0 else ""
    try:
        await message.bot.send_message(
            user.telegram_id,
            f"💰 <b>ব্যালেন্স আপডেট</b>\n\nআপনার ব্যালেন্স <b>{sign}{C}{amount:,.0f}</b> পরিবর্তন হয়েছে।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ <b>ব্যালেন্স আপডেট!</b>\n\n"
        f"👤 ব্যবহারকারী: {user.full_name}\n"
        f"পরিমাণ: <b>{sign}{C}{amount:,.0f}</b>\n"
        f"নতুন ব্যালেন্স: <b>{C}{user.balance + amount:,.0f}</b>",
        parse_mode="HTML",
    )


@router.message(Command("addbalance"))
async def add_balance_command(message: Message, session: AsyncSession) -> None:
    args = message.text.split()
    if len(args) != 3:
        await message.answer("ব্যবহার: /addbalance <telegram_id> <পরিমাণ>")
        return
    try:
        telegram_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ ভুল ইনপুট।")
        return

    user = await UserQueries.get_by_telegram_id(session, telegram_id)
    if not user:
        await message.answer("❌ ব্যবহারকারী পাওয়া যায়নি।")
        return

    await UserQueries.update_balance(session, user.id, amount)
    sign = "+" if amount >= 0 else ""
    try:
        await message.bot.send_message(
            telegram_id,
            f"💰 <b>ব্যালেন্স আপডেট</b>\n\nআপনার ব্যালেন্স {sign}{C}{amount:,.0f} পরিবর্তন হয়েছে।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ ব্যালেন্স আপডেট!\n"
        f"ব্যবহারকারী: {user.full_name}\n"
        f"পরিমাণ: {sign}{C}{amount:,.0f}"
    )
