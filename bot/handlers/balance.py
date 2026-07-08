from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, TransactionQueries
from bot.keyboards.main_menu import get_main_menu, get_profile_inline
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL


@router.message(F.text == "💰 ব্যালেন্স")
async def balance_handler(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    transactions = await TransactionQueries.get_user_transactions(session, user.id, 5)

    tx_lines = ""
    if transactions:
        tx_lines = "\n\n📜 <b>সাম্প্রতিক লেনদেন:</b>\n"
        for tx in transactions:
            sign = "+" if tx.amount > 0 else ""
            emoji = {"deposit": "💳", "withdrawal": "🏧", "reward": "🏆", "referral": "👥"}.get(tx.type.value, "💸")
            status_emoji = {"completed": "✅", "pending": "⏳", "rejected": "❌"}.get(tx.status.value, "❓")
            tx_lines += f"{emoji} {sign}{C}{tx.amount:,.0f} — {tx.type.value.capitalize()} {status_emoji}\n"
    else:
        tx_lines = "\n\n📜 এখনো কোনো লেনদেন নেই।"

    text = (
        f"💰 <b>আপনার ব্যালেন্স</b>\n\n"
        f"💵 পাওয়া যাবে: <b>{C}{user.balance:,.0f}</b>\n"
        f"📈 মোট আয়: <b>{C}{user.total_earned:,.0f}</b>\n"
        f"📤 মোট উত্তোলন: <b>{C}{user.total_withdrawn:,.0f}</b>"
        f"{tx_lines}"
    )

    await message.answer(text, reply_markup=get_profile_inline(user.id), parse_mode="HTML")


@router.message(F.text == "📜 ইতিহাস")
async def history_handler(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    transactions = await TransactionQueries.get_user_transactions(session, user.id, 30)

    # Filter only deposits and withdrawals
    filtered = [tx for tx in transactions if tx.type.value in ("deposit", "withdrawal")]

    if not filtered:
        await message.answer("📜 এখনো কোনো ডিপোসিট বা উইথড্রয়াল নেই।")
        return

    STATUS = {"completed": "✅ সম্পন্ন", "pending": "⏳ অপেক্ষমাণ", "rejected": "❌ বাতিল"}
    TYPE   = {"deposit": "💳 ডিপোসিট", "withdrawal": "🏧 উইথড্রয়াল"}

    lines = ["📜 <b>ডিপোসিট ও উইথড্রয়াল ইতিহাস</b>\n"]
    for tx in filtered:
        date_str   = tx.created_at.strftime("%d %b %H:%M")
        type_label = TYPE.get(tx.type.value, tx.type.value)
        status     = STATUS.get(tx.status.value, tx.status.value)
        lines.append(f"{type_label} — <b>{C}{tx.amount:,.0f}</b>\n   {status} | {date_str}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("tx_history:"))
async def tx_history_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("ব্যবহারকারী পাওয়া যায়নি।", show_alert=True)
        return

    transactions = await TransactionQueries.get_user_transactions(session, user.id, 20)

    if not transactions:
        await callback.answer("কোনো লেনদেন পাওয়া যায়নি।", show_alert=True)
        return

    lines = ["📜 <b>লেনদেনের ইতিহাস</b>\n"]
    for tx in transactions:
        sign = "+" if tx.amount > 0 else ""
        emoji = {"deposit": "💳", "withdrawal": "🏧", "reward": "🏆", "referral": "👥"}.get(tx.type.value, "💸")
        status_emoji = {"completed": "✅", "pending": "⏳", "rejected": "❌"}.get(tx.status.value, "❓")
        date_str = tx.created_at.strftime("%d %b %Y %H:%M")
        lines.append(f"{emoji} {sign}{C}{tx.amount:,.0f} — {tx.type.value.capitalize()} {status_emoji}\n   📅 {date_str}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()
