from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, SupportQueries
from bot.keyboards.inline import get_cancel_keyboard
from bot.keyboards.main_menu import get_main_menu_for
from config import settings

router = Router()


class SupportStates(StatesGroup):
    typing_message = State()


@router.message(F.text == "🆘 সাপোর্ট")
async def support_handler(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    support_link = f"@{settings.SUPPORT_USERNAME}" if settings.SUPPORT_USERNAME else "আমাদের সাপোর্ট টিম"

    await state.set_state(SupportStates.typing_message)
    await message.answer(
        f"🎫 <b>সাপোর্ট</b>\n\n"
        f"আপনার সমস্যা বা প্রশ্ন লিখুন, আমরা যত দ্রুত সম্ভব উত্তর দেব।\n\n"
        f"সরাসরি যোগাযোগ: {support_link}\n\n"
        f"নিচে আপনার বার্তা লিখুন:",
        reply_markup=get_cancel_keyboard("cancel_support"),
        parse_mode="HTML",
    )


@router.message(SupportStates.typing_message)
async def receive_support_message(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    ticket_message = message.text or "[মিডিয়া বার্তা]"
    ticket = await SupportQueries.create_ticket(session, user.id, ticket_message)

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"🎫 <b>নতুন সাপোর্ট টিকেট #{ticket.id}</b>\n\n"
                f"👤 ব্যবহারকারী: {user.full_name} (<code>{user.telegram_id}</code>)\n"
                f"📝 বার্তা:\n{ticket_message[:1000]}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        f"✅ <b>সাপোর্ট অনুরোধ #{ticket.id} জমা হয়েছে!</b>\n\n"
        f"আমাদের টিম ২৪ ঘণ্টার মধ্যে উত্তর দেবে।\n"
        f"ধৈর্য ধরার জন্য ধন্যবাদ!",
        reply_markup=get_main_menu_for(message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel_support")
async def cancel_support(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ বাতিল করা হয়েছে।")
    await callback.message.answer("🏠 মূল মেনু", reply_markup=get_main_menu_for(callback.from_user.id))
    await callback.answer()
