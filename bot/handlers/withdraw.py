from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, TransactionQueries
from database.models import TransactionType, TransactionStatus
from bot.keyboards.inline import get_withdraw_methods, get_cancel_keyboard
from bot.keyboards.main_menu import get_main_menu_for
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL

METHOD_NAMES = {"bkash": "বিকাশ (bKash)", "nagad": "নগদ (Nagad)"}


class WithdrawStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    entering_details = State()


@router.message(F.text == "🏧 উইথড্র")
async def withdraw_handler(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    min_w = settings.MIN_WITHDRAW
    fee = settings.WITHDRAW_FEE

    if user.balance < min_w:
        await message.answer(
            f"❌ <b>অপর্যাপ্ত ব্যালেন্স</b>\n\n"
            f"আপনার ব্যালেন্স: <b>{C}{user.balance:,.0f}</b>\n"
            f"সর্বনিম্ন উত্তোলন: <b>{C}{min_w:,.0f}</b>\n\n"
            f"আরো কাজ করুন ব্যালেন্স বাড়াতে!",
            parse_mode="HTML",
        )
        return

    await state.set_state(WithdrawStates.choosing_method)
    await message.answer(
        f"🏧 <b>টাকা উত্তোলন</b>\n\n"
        f"পাওয়া যাবে: <b>{C}{user.balance:,.0f}</b>\n"
        f"সর্বনিম্ন: {C}{min_w:,.0f} | ফি: {C}{fee:,.0f}\n\n"
        f"উত্তোলনের পদ্ধতি বেছে নিন:",
        reply_markup=get_withdraw_methods(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("withdraw:"))
async def withdraw_method_selected(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[1]
    method_name = METHOD_NAMES.get(method, method)

    await state.update_data(method=method)
    await state.set_state(WithdrawStates.entering_amount)

    await callback.message.edit_text(
        f"🏧 <b>{method_name} এ উত্তোলন</b>\n\n"
        f"কত টাকা উত্তোলন করতে চান?\n"
        f"(সর্বনিম্ন {C}{settings.MIN_WITHDRAW:,.0f}, ফি {C}{settings.WITHDRAW_FEE:,.0f} কাটা হবে):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(WithdrawStates.entering_amount))
async def withdraw_amount(message: Message, session: AsyncSession, state: FSMContext) -> None:
    min_w = settings.MIN_WITHDRAW
    fee = settings.WITHDRAW_FEE

    try:
        amount = float((message.text or "").replace(",", "").strip())
        if amount < min_w:
            await message.answer(f"❌ সর্বনিম্ন উত্তোলন {C}{min_w:,.0f}। বেশি পরিমাণ দিন:", reply_markup=get_cancel_keyboard())
            return
    except ValueError:
        await message.answer("❌ ভুল পরিমাণ। শুধু সংখ্যা লিখুন:", reply_markup=get_cancel_keyboard())
        return

    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user or user.balance < amount:
        bal = user.balance if user else 0
        await message.answer(f"❌ অপর্যাপ্ত ব্যালেন্স। আপনার ব্যালেন্স: {C}{bal:,.0f}", reply_markup=get_main_menu_for(message.from_user.id))
        await state.clear()
        return

    data = await state.get_data()
    method = data.get("method", "bkash")
    method_name = METHOD_NAMES.get(method, method)
    net = amount - fee

    await state.update_data(amount=amount)
    await state.set_state(WithdrawStates.entering_details)

    prompts = {
        "bkash": "আপনার বিকাশ নম্বর লিখুন (Send Money পাঠানো হবে):",
        "nagad": "আপনার নগদ নম্বর লিখুন (Send Money পাঠানো হবে):",
    }

    await message.answer(
        f"🏧 <b>উত্তোলনের বিবরণ</b>\n\n"
        f"উত্তোলন: <b>{C}{amount:,.0f}</b>\n"
        f"ফি: <b>-{C}{fee:,.0f}</b>\n"
        f"আপনি পাবেন: <b>{C}{net:,.0f}</b>\n"
        f"পদ্ধতি: {method_name}\n\n"
        f"{prompts.get(method, 'নম্বর লিখুন:')}",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(WithdrawStates.entering_details))
async def withdraw_details(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    amount = data.get("amount", 0)
    method = data.get("method", "bkash")
    method_name = METHOD_NAMES.get(method, method)
    fee = settings.WITHDRAW_FEE
    net = amount - fee
    await state.clear()

    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    if user.balance < amount:
        await message.answer("❌ অপর্যাপ্ত ব্যালেন্স।", reply_markup=get_main_menu_for(message.from_user.id))
        return

    await UserQueries.update_balance(session, user.id, -amount)
    details = f"পদ্ধতি: {method_name}, নম্বর: {message.text or 'N/A'}, নেট: {C}{net:,.0f}"

    tx = await TransactionQueries.create(
        session=session,
        user_id=user.id,
        type=TransactionType.WITHDRAWAL,
        amount=amount,
        details=details,
    )

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"🏧 <b>নতুন উত্তোলনের অনুরোধ</b>\n\n"
                f"👤 ব্যবহারকারী: {user.full_name} (<code>{user.telegram_id}</code>)\n"
                f"💵 পরিমাণ: <b>{C}{amount:,.0f}</b> (ফি: {C}{fee:,.0f}, নেট: {C}{net:,.0f})\n"
                f"💳 পদ্ধতি: {method_name}\n"
                f"📝 নম্বর: {message.text or 'N/A'}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        f"✅ <b>উত্তোলনের অনুরোধ জমা হয়েছে!</b>\n\n"
        f"উত্তোলন: <b>{C}{amount:,.0f}</b>\n"
        f"ফি: <b>{C}{fee:,.0f}</b>\n"
        f"আপনি পাবেন: <b>{C}{net:,.0f}</b>\n"
        f"পদ্ধতি: {method_name}\n"
        f"অবস্থা: ⏳ অপেক্ষমাণ\n\n"
        f"২৪ ঘণ্টার মধ্যে প্রক্রিয়া করা হবে।",
        reply_markup=get_main_menu_for(message.from_user.id),
        parse_mode="HTML",
    )
