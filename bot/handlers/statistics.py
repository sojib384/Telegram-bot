from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from database.queries import UserQueries, TaskQueries, TransactionQueries
from database.models import UserTask, TaskStatus, Transaction, TransactionType, TransactionStatus
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL


@router.message(F.text == "📊 Statistics")
async def statistics_handler(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    referrals = await UserQueries.get_referrals(session, user.id)
    transactions = await TransactionQueries.get_user_transactions(session, user.id, 100)

    completed_tasks_result = await session.execute(
        select(func.count()).select_from(UserTask).where(
            and_(UserTask.user_id == user.id, UserTask.status == TaskStatus.COMPLETED)
        )
    )
    completed_tasks = completed_tasks_result.scalar_one()

    pending_tasks_result = await session.execute(
        select(func.count()).select_from(UserTask).where(
            and_(UserTask.user_id == user.id, UserTask.status == TaskStatus.PENDING)
        )
    )
    pending_tasks = pending_tasks_result.scalar_one()

    total_deposited = sum(
        tx.amount for tx in transactions
        if tx.type == TransactionType.DEPOSIT and tx.status == TransactionStatus.COMPLETED
    )
    total_withdrawn = sum(
        tx.amount for tx in transactions
        if tx.type == TransactionType.WITHDRAWAL and tx.status == TransactionStatus.COMPLETED
    )
    referral_earnings = sum(
        tx.amount for tx in transactions
        if tx.type == TransactionType.REFERRAL and tx.status == TransactionStatus.COMPLETED
    )
    task_earnings = sum(
        tx.amount for tx in transactions
        if tx.type == TransactionType.REWARD and tx.status == TransactionStatus.COMPLETED
    )

    joined_str = user.created_at.strftime("%d %b %Y")
    last_active_str = user.last_active.strftime("%d %b %Y %H:%M")

    text = (
        f"📊 <b>আপনার পরিসংখ্যান</b>\n\n"
        f"👤 <b>অ্যাকাউন্ট</b>\n"
        f"   📅 যোগদান: {joined_str}\n"
        f"   🕐 শেষ সক্রিয়: {last_active_str}\n\n"
        f"💼 <b>কাজ</b>\n"
        f"   ✅ সম্পন্ন: {completed_tasks}\n"
        f"   ⏳ পর্যালোচনাধীন: {pending_tasks}\n\n"
        f"👥 <b>রেফারেল</b>\n"
        f"   মোট: {len(referrals)}\n"
        f"   আয়: {C}{referral_earnings:,.0f}\n\n"
        f"💰 <b>আর্থিক সারাংশ</b>\n"
        f"   💵 ব্যালেন্স: {C}{user.balance:,.0f}\n"
        f"   📈 মোট আয়: {C}{user.total_earned:,.0f}\n"
        f"   🏆 কাজের পুরস্কার: {C}{task_earnings:,.0f}\n"
        f"   💳 মোট জমা: {C}{total_deposited:,.0f}\n"
        f"   🏧 মোট উত্তোলন: {C}{user.total_withdrawn:,.0f}"
    )

    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("profile_stats:"))
async def profile_stats_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("ব্যবহারকারী পাওয়া যায়নি।", show_alert=True)
        return

    referrals = await UserQueries.get_referrals(session, user.id)

    completed_result = await session.execute(
        select(func.count()).select_from(UserTask).where(
            and_(UserTask.user_id == user.id, UserTask.status == TaskStatus.COMPLETED)
        )
    )
    completed = completed_result.scalar_one()

    text = (
        f"📊 <b>দ্রুত পরিসংখ্যান</b>\n\n"
        f"✅ সম্পন্ন কাজ: {completed}\n"
        f"👥 রেফারেল: {len(referrals)}\n"
        f"💰 ব্যালেন্স: {C}{user.balance:,.0f}\n"
        f"📈 মোট আয়: {C}{user.total_earned:,.0f}"
    )

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
