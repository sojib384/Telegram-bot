from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import SupportQueries
from bot.filters import IsAdmin
from bot.keyboards.admin import get_ticket_actions

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class TicketReplyStates(StatesGroup):
    replying = State()


@router.message(F.text == "🎫 Support Tickets")
async def list_tickets(message: Message, session: AsyncSession) -> None:
    tickets = await SupportQueries.get_open_tickets(session)

    if not tickets:
        await message.answer("🎫 কোনো খোলা সাপোর্ট টিকেট নেই।")
        return

    await message.answer(
        f"🎫 <b>খোলা সাপোর্ট টিকেট</b> ({len(tickets)})\n\nটিকেটগুলো পর্যালোচনা করুন:",
        parse_mode="HTML",
    )

    for ticket in tickets[:15]:
        text = (
            f"🎫 <b>টিকেট #{ticket.id}</b>\n\n"
            f"👤 ব্যবহারকারী: {ticket.user.full_name} (<code>{ticket.user.telegram_id}</code>)\n"
            f"📝 বার্তা:\n{ticket.message[:500]}\n"
            f"📅 জমা: {ticket.created_at.strftime('%d %b %Y %H:%M')}"
        )
        await message.answer(
            text,
            reply_markup=get_ticket_actions(ticket.id),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("reply_ticket:"))
async def reply_ticket_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = int(callback.data.split(":")[1])
    await state.set_state(TicketReplyStates.replying)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer(
        f"💬 <b>টিকেট #{ticket_id} এর উত্তর</b>\n\nআপনার উত্তর লিখুন:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TicketReplyStates.replying)
async def send_reply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    await state.clear()

    ticket = await SupportQueries.get_by_id(session, ticket_id)
    if not ticket:
        await message.answer("❌ টিকেট পাওয়া যায়নি।")
        return

    reply = message.text
    await SupportQueries.close_ticket(session, ticket_id, reply)

    try:
        await message.bot.send_message(
            ticket.user.telegram_id,
            f"🎫 <b>সাপোর্ট উত্তর — টিকেট #{ticket_id}</b>\n\n"
            f"📝 আপনার প্রশ্ন:\n<i>{ticket.message[:300]}</i>\n\n"
            f"💬 অ্যাডমিনের উত্তর:\n{reply}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(
        f"✅ উত্তর পাঠানো হয়েছে {ticket.user.full_name} কে এবং টিকেট #{ticket_id} বন্ধ করা হয়েছে।"
    )


@router.callback_query(F.data.startswith("close_ticket:"))
async def close_ticket(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = await SupportQueries.get_by_id(session, ticket_id)

    if not ticket:
        await callback.answer("টিকেট পাওয়া যায়নি।", show_alert=True)
        return

    await SupportQueries.close_ticket(session, ticket_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n🔒 <b>বন্ধ</b>",
        parse_mode="HTML",
    )
    await callback.answer("টিকেট বন্ধ করা হয়েছে।")
