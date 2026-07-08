from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, TransactionQueries
from database.models import TransactionType
from bot.keyboards.inline import get_deposit_methods, get_cancel_keyboard
from bot.keyboards.main_menu import get_main_menu_for
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL

PAYMENT_NUMBER = "01710591301"
MIN_DEPOSIT    = 100.0

METHOD_NAMES = {
    "bkash": "বিকাশ (bKash)",
    "nagad": "নগদ (Nagad)",
}


class DepositStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    entering_proof  = State()


# ── Step 0 — Show methods ──────────────────────────────────────────────────────

@router.message(F.text == "💳 ডিপোজিট")
async def deposit_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(DepositStates.choosing_method)
    await message.answer(
        f"💳 <b>ব্যালেন্স জমা দিন</b>\n\n"
        f"📌 সর্বনিম্ন জমা: <b>{C}{MIN_DEPOSIT:,.0f}</b>\n\n"
        f"জমা দেওয়ার পদ্ধতি বেছে নিন:",
        reply_markup=get_deposit_methods(),
        parse_mode="HTML",
    )


# ── Step 1 — Method selected → show number + ask amount ───────────────────────

@router.callback_query(StateFilter(DepositStates.choosing_method), F.data.startswith("deposit:"))
async def deposit_method_selected(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[1]
    if method not in METHOD_NAMES:
        await callback.answer("অজানা পদ্ধতি।", show_alert=True)
        return

    method_name = METHOD_NAMES[method]
    await state.update_data(method=method)
    await state.set_state(DepositStates.entering_amount)

    await callback.message.edit_text(
        f"💳 <b>{method_name} — Personal Send Money</b>\n\n"
        f"📱 নম্বর: <code>{PAYMENT_NUMBER}</code>\n\n"
        f"⚠️ শুধুমাত্র <b>Send Money (পাঠান)</b> করুন।\n"
        f"Payment বা Add Money করবেন না।\n\n"
        f"কত টাকা পাঠাতে চান? (সর্বনিম্ন {C}{MIN_DEPOSIT:,.0f}):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 2 — Amount entered → ask proof ───────────────────────────────────────

@router.message(StateFilter(DepositStates.entering_amount))
async def deposit_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", "").strip())
        if amount < MIN_DEPOSIT:
            await message.answer(
                f"❌ সর্বনিম্ন জমার পরিমাণ <b>{C}{MIN_DEPOSIT:,.0f}</b>।\n"
                f"আবার লিখুন:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML",
            )
            return
    except ValueError:
        await message.answer(
            "❌ ভুল পরিমাণ। শুধু সংখ্যা লিখুন (যেমন: 200):",
            reply_markup=get_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    method_name = METHOD_NAMES.get(data.get("method", ""), "")
    await state.update_data(amount=amount)
    await state.set_state(DepositStates.entering_proof)

    await message.answer(
        f"✅ পরিমাণ: <b>{C}{amount:,.0f}</b>\n\n"
        f"এখন <b>{method_name}</b> অ্যাপ থেকে:\n"
        f"📱 নম্বরে পাঠান: <code>{PAYMENT_NUMBER}</code>\n"
        f"💵 পরিমাণ: <b>{C}{amount:,.0f}</b>\n\n"
        f"পাঠানো হলে ট্রানজেকশন ID বা স্ক্রিনশট পাঠান:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


# ── Step 3 — Proof received → save pending transaction ────────────────────────

@router.message(StateFilter(DepositStates.entering_proof))
async def deposit_proof(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    amount      = data.get("amount", 0)
    method      = data.get("method", "bkash")
    method_name = METHOD_NAMES.get(method, method)
    await state.clear()

    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    is_photo = bool(message.photo)
    if is_photo:
        best: PhotoSize = message.photo[-1]
        proof_text    = f"PHOTO:{best.file_id}"
        proof_display = "[📸 স্ক্রিনশট]"
        if message.caption:
            proof_text    += f"|CAPTION:{message.caption}"
            proof_display += f" — {message.caption}"
    else:
        raw           = message.text or message.caption or "[মিডিয়া]"
        proof_text    = raw
        proof_display = raw[:300]

    details = f"পদ্ধতি: {method_name} | প্রমাণ: {proof_display[:400]}"

    tx = await TransactionQueries.create(
        session=session,
        user_id=user.id,
        type=TransactionType.DEPOSIT,
        amount=amount,
        details=details,
    )

    # ── Notify admins ──────────────────────────────────────────────────────────
    from bot.keyboards.admin import get_deposit_actions
    admin_text = (
        f"💳 <b>নতুন জমার অনুরোধ #{tx.id}</b>\n\n"
        f"👤 {user.full_name} (<code>{user.telegram_id}</code>)\n"
        f"💵 পরিমাণ: <b>{C}{amount:,.0f}</b>\n"
        f"💳 পদ্ধতি: {method_name}\n"
        f"📝 প্রমাণ: {proof_display}"
    )
    for admin_id in settings.admin_ids:
        try:
            if is_photo:
                await message.bot.send_photo(
                    admin_id, photo=best.file_id,
                    caption=admin_text,
                    reply_markup=get_deposit_actions(tx.id),
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    admin_id, admin_text,
                    reply_markup=get_deposit_actions(tx.id),
                    parse_mode="HTML",
                )
        except Exception:
            pass

    await message.answer(
        f"✅ <b>জমার অনুরোধ সফলভাবে পাঠানো হয়েছে!</b>\n\n"
        f"💵 পরিমাণ: <b>{C}{amount:,.0f}</b>\n"
        f"💳 পদ্ধতি: {method_name}\n"
        f"⏳ অবস্থা: পর্যালোচনাধীন\n\n"
        f"⏰ <b>২ ঘন্টার মধ্যে</b> ব্যালেন্সে যোগ হয়ে যাবে।\n\n"
        f"সমস্যা হলে মেসেজ করুন: @smart_tech_Bangla\n"
        f"❌ <b>মনে রাখবেন:</b> ২ ঘন্টা অপেক্ষা করুন, তার আগে মেসেজ করবেন না।",
        reply_markup=get_main_menu_for(message.from_user.id),
        parse_mode="HTML",
    )


# ── Cancel ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("❌ বাতিল করা হয়েছে।")
    except Exception:
        pass
    await callback.message.answer("🏠 মূল মেনু", reply_markup=get_main_menu_for(callback.from_user.id))
    await callback.answer()
