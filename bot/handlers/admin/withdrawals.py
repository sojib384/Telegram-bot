from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import TransactionQueries, UserQueries, BotSettingsQueries
from database.models import TransactionStatus, TransactionType
from bot.filters import IsAdmin
from bot.keyboards.admin import get_withdrawal_actions, get_deposit_actions
from config import settings

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
C = settings.CURRENCY_SYMBOL


# ── Withdrawals ───────────────────────────────────────────────────────────────

@router.message(F.text == "💸 Withdrawals")
async def pending_withdrawals(message: Message, session: AsyncSession) -> None:
    withdrawals = await TransactionQueries.get_pending_withdrawals(session)

    if not withdrawals:
        await message.answer("💸 কোনো অপেক্ষমাণ উত্তোলনের অনুরোধ নেই।")
        return

    await message.answer(
        f"💸 <b>অপেক্ষমাণ উত্তোলন</b> ({len(withdrawals)}টি)\n\nঅনুরোধগুলো পর্যালোচনা করুন:",
        parse_mode="HTML",
    )

    fee = settings.WITHDRAW_FEE
    commission_rate_val = await BotSettingsQueries.get_float(session, "referral_withdrawal_commission")
    commission_pct = int(commission_rate_val * 100)

    for tx in withdrawals[:20]:
        net = tx.amount - fee
        text = (
            f"💸 <b>উত্তোলন #{tx.id}</b>\n\n"
            f"👤 {tx.user.full_name} (<code>{tx.user.telegram_id}</code>)\n"
            f"💵 পরিমাণ: <b>{C}{tx.amount:,.0f}</b> | ফি: {C}{fee:,.0f} | নেট: <b>{C}{net:,.0f}</b>\n"
            f"📝 {tx.details or '—'}\n"
            f"📅 {tx.created_at.strftime('%d %b %Y %H:%M')}\n"
            f"ℹ️ রেফারার কমিশন: {commission_pct}%"
        )
        await message.answer(text, reply_markup=get_withdrawal_actions(tx.id), parse_mode="HTML")


@router.callback_query(F.data.startswith("approve_withdrawal:"))
async def approve_withdrawal(callback: CallbackQuery, session: AsyncSession) -> None:
    tx_id = int(callback.data.split(":")[1])
    withdrawals = await TransactionQueries.get_pending_withdrawals(session)
    tx = next((t for t in withdrawals if t.id == tx_id), None)

    if not tx:
        await callback.answer("লেনদেন পাওয়া যায়নি।", show_alert=True)
        return

    await TransactionQueries.update_status(session, tx_id, TransactionStatus.COMPLETED)

    commission_rate = await BotSettingsQueries.get_float(session, "referral_withdrawal_commission")
    fee = settings.WITHDRAW_FEE
    net = tx.amount - fee

    withdrawing_user = tx.user
    if withdrawing_user.referred_by_id:
        commission = round(tx.amount * commission_rate, 0)
        await UserQueries.update_balance(session, withdrawing_user.referred_by_id, commission)
        from database.models import Transaction
        from database.queries import TransactionQueries as TQ
        referral_tx = await TQ.create(
            session=session,
            user_id=withdrawing_user.referred_by_id,
            type=TransactionType.REFERRAL,
            amount=commission,
            details=f"উত্তোলন কমিশন ({int(commission_rate*100)}%): {withdrawing_user.full_name}",
        )
        referral_tx.status = TransactionStatus.COMPLETED
        await session.commit()

        try:
            referrer = await UserQueries.get_by_id(session, withdrawing_user.referred_by_id)
            if referrer:
                await callback.bot.send_message(
                    referrer.telegram_id,
                    f"💸 <b>রেফারেল কমিশন!</b>\n\n"
                    f"<b>{withdrawing_user.full_name}</b> {C}{tx.amount:,.0f} উত্তোলন করেছেন।\n"
                    f"আপনি পেয়েছেন: <b>{C}{commission:,.0f}</b>",
                    parse_mode="HTML",
                )
        except Exception:
            pass

    try:
        await callback.bot.send_message(
            tx.user.telegram_id,
            f"✅ <b>উত্তোলন অনুমোদিত!</b>\n\n"
            f"পরিমাণ: {C}{tx.amount:,.0f} | ফি: {C}{fee:,.0f}\n"
            f"আপনি পাবেন: <b>{C}{net:,.0f}</b>\n"
            f"২৪ ঘণ্টার মধ্যে পৌঁছে যাবে।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>অনুমোদিত</b>",
        parse_mode="HTML",
    )
    await callback.answer("উত্তোলন অনুমোদিত!")


@router.callback_query(F.data.startswith("reject_withdrawal:"))
async def reject_withdrawal(callback: CallbackQuery, session: AsyncSession) -> None:
    tx_id = int(callback.data.split(":")[1])
    withdrawals = await TransactionQueries.get_pending_withdrawals(session)
    tx = next((t for t in withdrawals if t.id == tx_id), None)

    if not tx:
        await callback.answer("লেনদেন পাওয়া যায়নি।", show_alert=True)
        return

    await TransactionQueries.update_status(session, tx_id, TransactionStatus.REJECTED)
    await UserQueries.update_balance(session, tx.user_id, tx.amount)

    try:
        await callback.bot.send_message(
            tx.user.telegram_id,
            f"❌ <b>উত্তোলন বাতিল হয়েছে</b>\n\n"
            f"{C}{tx.amount:,.0f} আপনার ব্যালেন্সে ফেরত দেওয়া হয়েছে।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>বাতিল — টাকা ফেরত</b>",
        parse_mode="HTML",
    )
    await callback.answer("বাতিল এবং টাকা ফেরত।")


# ── Deposits ──────────────────────────────────────────────────────────────────

@router.message(F.text == "💳 Deposits")
async def pending_deposits(message: Message, session: AsyncSession) -> None:
    deposits = await TransactionQueries.get_pending_deposits(session)

    if not deposits:
        recent = await TransactionQueries.get_recent_deposits(session, limit=10)
        if not recent:
            await message.answer("💳 কোনো জমার ইতিহাস নেই।")
            return
        lines = [f"💳 <b>সাম্প্রতিক জমা</b> (অনুমোদিত)\n"]
        for tx in recent:
            status_emoji = "✅" if tx.status == TransactionStatus.COMPLETED else "❌"
            lines.append(
                f"{status_emoji} #{tx.id} | {tx.user.full_name} | {C}{tx.amount:,.0f} | {tx.created_at.strftime('%d %b %Y')}"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    await message.answer(
        f"💳 <b>অপেক্ষমাণ জমার অনুরোধ</b> ({len(deposits)}টি)",
        parse_mode="HTML",
    )

    for tx in deposits[:20]:
        text = (
            f"💳 <b>জমা #{tx.id}</b>\n\n"
            f"👤 {tx.user.full_name} (<code>{tx.user.telegram_id}</code>)\n"
            f"💵 পরিমাণ: <b>{C}{tx.amount:,.0f}</b>\n"
            f"📝 {tx.details or '—'}\n"
            f"📅 {tx.created_at.strftime('%d %b %Y %H:%M')}"
        )
        await message.answer(text, reply_markup=get_deposit_actions(tx.id), parse_mode="HTML")


@router.callback_query(F.data.startswith("approve_deposit:"))
async def approve_deposit(callback: CallbackQuery, session: AsyncSession) -> None:
    tx_id = int(callback.data.split(":")[1])
    tx = await TransactionQueries.get_by_id(session, tx_id)

    if not tx or tx.status != TransactionStatus.PENDING:
        await callback.answer("লেনদেন পাওয়া যায়নি বা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    await TransactionQueries.update_status(session, tx_id, TransactionStatus.COMPLETED)
    await UserQueries.update_balance(session, tx.user_id, tx.amount)

    try:
        await callback.bot.send_message(
            tx.user.telegram_id,
            f"✅ <b>জমা অনুমোদিত!</b>\n\n"
            f"<b>{C}{tx.amount:,.0f}</b> আপনার ব্যালেন্সে যোগ হয়েছে।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>অনুমোদিত — ব্যালেন্সে যোগ হয়েছে</b>",
        parse_mode="HTML",
    )
    await callback.answer("জমা অনুমোদিত!")


@router.callback_query(F.data.startswith("reject_deposit:"))
async def reject_deposit(callback: CallbackQuery, session: AsyncSession) -> None:
    tx_id = int(callback.data.split(":")[1])
    tx = await TransactionQueries.get_by_id(session, tx_id)

    if not tx or tx.status != TransactionStatus.PENDING:
        await callback.answer("লেনদেন পাওয়া যায়নি বা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    await TransactionQueries.update_status(session, tx_id, TransactionStatus.REJECTED)

    try:
        await callback.bot.send_message(
            tx.user.telegram_id,
            f"❌ <b>জমার অনুরোধ বাতিল হয়েছে</b>\n\n"
            f"{C}{tx.amount:,.0f} জমা অনুমোদন হয়নি।\n"
            f"সঠিক প্রমাণ দিয়ে আবার চেষ্টা করুন।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>বাতিল</b>",
        parse_mode="HTML",
    )
    await callback.answer("জমার অনুরোধ বাতিল।")
