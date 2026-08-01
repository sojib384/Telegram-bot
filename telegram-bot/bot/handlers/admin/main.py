from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, update

from database.queries import UserQueries, TaskQueries, TransactionQueries, BotSettingsQueries
from database.models import User, Transaction, TransactionType, TransactionStatus
from bot.filters import IsAdmin
from bot.keyboards.admin import get_admin_menu
from bot.keyboards.main_menu import get_main_menu
from config import settings

router = Router()
router.message.filter(IsAdmin())
C = settings.CURRENCY_SYMBOL


class BroadcastStates(StatesGroup):
    waiting_for_message = State()


class ReferralSettingsStates(StatesGroup):
    choosing_field  = State()
    entering_value  = State()


@router.message(Command("admin"))
@router.message(F.text == "⚙️ অ্যাডমিন প্যানেল")
async def admin_panel(message: Message) -> None:
    await message.answer(
        f"⚙️ <b>অ্যাডমিন প্যানেল</b>\n\nস্বাগতম, {message.from_user.full_name}!\nকী করতে চান?",
        reply_markup=get_admin_menu(),
        parse_mode="HTML",
    )


@router.message(F.text == "🔙 Exit Admin")
async def exit_admin(message: Message) -> None:
    await message.answer(
        "🏠 মূল মেনুতে ফিরে যাচ্ছি।",
        reply_markup=get_main_menu(is_admin=True),
    )


@router.message(F.text == "📊 Bot Stats")
async def bot_stats(message: Message, session: AsyncSession) -> None:
    total_users = await UserQueries.get_total_count(session)
    today_users = await UserQueries.get_today_registrations(session)

    blocked_result = await session.execute(
        select(func.count()).select_from(User).where(User.is_blocked == True)
    )
    blocked_users = blocked_result.scalar_one()

    total_tasks = await TaskQueries.get_total_tasks_count(session)
    active_tasks = await TaskQueries.get_active_tasks_count(session)
    pending_submissions = await TaskQueries.get_pending_submissions_count(session)

    total_deposited = await TransactionQueries.get_total_deposited(session)
    total_withdrawn = await TransactionQueries.get_total_withdrawn(session)
    pending_deposits = await TransactionQueries.get_pending_deposits_count(session)
    pending_withdrawals = await TransactionQueries.get_pending_withdrawals_count(session)

    text = (
        f"📊 <b>বট ড্যাশবোর্ড</b>\n\n"
        f"👥 <b>ব্যবহারকারী</b>\n"
        f"   মোট: <b>{total_users}</b> | আজ: <b>+{today_users}</b> | ব্লক: {blocked_users}\n\n"
        f"📋 <b>কাজ</b>\n"
        f"   মোট: <b>{total_tasks}</b> | সক্রিয়: <b>{active_tasks}</b>\n"
        f"   পর্যালোচনাধীন জমা: <b>{pending_submissions}</b>\n\n"
        f"💰 <b>আর্থিক</b>\n"
        f"   মোট জমা: <b>{C}{total_deposited:,.0f}</b> | অপেক্ষমাণ: {pending_deposits}\n"
        f"   মোট উত্তোলন: <b>{C}{total_withdrawn:,.0f}</b> | অপেক্ষমাণ: {pending_withdrawals}"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💰 Referral Settings")
async def referral_settings_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    commission = await BotSettingsQueries.get_float(session, "referral_withdrawal_commission")

    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ কমিশন % পরিবর্তন", callback_data="ref_set:commission"),
    )

    await message.answer(
        f"💰 <b>রেফারেল সেটিংস</b>\n\n"
        f"❌ যোগদানে কোনো বোনাস নেই\n"
        f"💸 উত্তোলন কমিশন: <b>{int(commission * 100)}%</b>\n\n"
        f"(রেফার করা ব্যক্তি উত্তোলন করলে এই % আপনি পাবেন)\n\n"
        f"পরিবর্তন করতে নিচের বোতাম চাপুন:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("ref_set:"))
async def ref_set_callback(callback, state: FSMContext) -> None:
    field = callback.data.split(":")[1]
    await state.set_state(ReferralSettingsStates.entering_value)
    await state.update_data(field=field)

    await callback.message.answer(
        "💸 <b>উত্তোলন কমিশন</b>\n\n"
        "নতুন কমিশন শতাংশ লিখুন (0–100):\n"
        "উদাহরণ: <code>10</code> (মানে ১০%)",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ReferralSettingsStates.entering_value)
async def ref_set_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()

    try:
        raw = float((message.text or "").strip())
        if raw < 0 or raw > 100:
            raise ValueError
    except ValueError:
        await message.answer("❌ ০ থেকে ১০০ এর মধ্যে সংখ্যা দিন।", reply_markup=get_admin_menu())
        return

    pct_decimal = raw / 100
    await BotSettingsQueries.set(session, "referral_withdrawal_commission", str(pct_decimal))
    await message.answer(
        f"✅ উত্তোলন কমিশন আপডেট হয়েছে: <b>{int(raw)}%</b>",
        reply_markup=get_admin_menu(), parse_mode="HTML",
    )


@router.message(F.text == "📣 Broadcast")
async def broadcast_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(BroadcastStates.waiting_for_message)
    total = await message.bot.get_me()
    await message.answer(
        "📣 <b>ব্রডকাস্ট বার্তা</b>\n\n"
        "সব ব্যবহারকারীকে পাঠাতে চান এমন বার্তা লিখুন।\n"
        "টেক্সট, ছবি, যেকোনো ফরম্যাট সাপোর্ট করে।\n\n"
        "বাতিল করতে /cancel লিখুন:",
        parse_mode="HTML",
    )


@router.message(BroadcastStates.waiting_for_message)
async def do_broadcast(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ ব্রডকাস্ট বাতিল করা হয়েছে।", reply_markup=get_admin_menu())
        return

    await state.clear()
    users = await UserQueries.get_all(session, limit=100000)

    status_msg = await message.answer(
        f"📣 ব্রডকাস্ট শুরু হচ্ছে... ({len(users)} জন ব্যবহারকারী)",
        parse_mode="HTML",
    )

    sent = 0
    failed = 0
    for user in users:
        if user.is_blocked:
            continue
        try:
            await message.copy_to(user.telegram_id)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📣 <b>ব্রডকাস্ট সম্পন্ন!</b>\n\n"
        f"✅ পাঠানো হয়েছে: <b>{sent}</b>\n"
        f"❌ ব্যর্থ: <b>{failed}</b>",
        parse_mode="HTML",
    )


@router.message(Command("reset_balances"))
async def reset_all_balances(message: Message, session: AsyncSession) -> None:
    """Admin command: reset all user balances, total_earned, total_withdrawn to 0."""
    await message.answer("⏳ সব user-এর ব্যালেন্স ০ করা হচ্ছে...")
    try:
        await session.execute(
            text("UPDATE users SET balance = 0.0, total_earned = 0.0, total_withdrawn = 0.0")
        )
        await session.commit()
        count_result = await session.execute(text("SELECT COUNT(*) FROM users"))
        count = count_result.scalar()
        await message.answer(
            f"✅ <b>সম্পন্ন!</b>\n\n"
            f"মোট <b>{count}</b> জন user-এর ব্যালেন্স ০ করা হয়েছে।",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
