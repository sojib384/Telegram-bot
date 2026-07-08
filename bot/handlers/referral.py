from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, ReferralQueries, BotSettingsQueries
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _referral_inline(user_id: int) -> object:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏆 Leaderboard", callback_data="referral:leaderboard"),
        InlineKeyboardButton(text="📊 আমার আয়", callback_data=f"referral:earnings:{user_id}"),
    )
    return builder.as_markup()


@router.message(F.text == "🤝 রেফারেল")
async def referral_handler(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    referral_count = await ReferralQueries.get_referral_count(session, user.id)
    referral_earnings = await ReferralQueries.get_referral_earnings(session, user.id)
    commission_pct = int(
        await BotSettingsQueries.get_float(session, "referral_withdrawal_commission") * 100
    )

    me = await message.bot.get_me()
    bot_username = me.username
    referral_link = f"https://t.me/{bot_username}?start={user.referral_code}"

    text = (
        f"👥 <b>রেফারেল প্রোগ্রাম</b>\n\n"
        f"💸 <b>উত্তোলন কমিশন:</b> {commission_pct}%\n"
        f"   আপনার রেফার করা ব্যক্তি যখন উত্তোলন করবেন,\n"
        f"   সেই পরিমাণের {commission_pct}% আপনি পাবেন।\n\n"
        f"❌ যোগদানে কোনো বোনাস নেই\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>আপনার পরিসংখ্যান</b>\n"
        f"👤 মোট রেফারেল: <b>{referral_count}</b> জন\n"
        f"💰 মোট কমিশন আয়: <b>{C}{referral_earnings:,.0f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 <b>আপনার রেফারেল লিংক:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"🎫 কোড: <code>{user.referral_code}</code>\n\n"
        f"📌 বন্ধুকে লিংকটি পাঠান। তিনি ৳১০০ তুললেই আপনি {commission_pct}% পাবেন!"
    )

    await message.answer(text, reply_markup=_referral_inline(user.id), parse_mode="HTML")


# ── Leaderboard ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "referral:leaderboard")
async def referral_leaderboard(callback: CallbackQuery, session: AsyncSession) -> None:
    rows = await ReferralQueries.get_leaderboard(session, limit=10)

    if not rows:
        await callback.answer("এখনো কোনো রেফারেল নেই।", show_alert=True)
        return

    lines = ["🏆 <b>রেফারেল লিডারবোর্ড (শীর্ষ ১০)</b>\n"]
    for i, (user, count) in enumerate(rows):
        medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
        name = user.full_name[:20]
        lines.append(f"{medal} <b>{name}</b> — {count} জন রেফারেল")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── My referral earnings breakdown ────────────────────────────────────────────

@router.callback_query(F.data.startswith("referral:earnings:"))
async def referral_earnings(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("ব্যবহারকারী পাওয়া যায়নি।", show_alert=True)
        return

    referrals = await UserQueries.get_referrals(session, user.id)
    total_earned = await ReferralQueries.get_referral_earnings(session, user.id)
    count = len(referrals)

    lines = [f"📊 <b>রেফারেল আয়ের বিবরণ</b>\n\n"
             f"👤 মোট রেফারেল: <b>{count}</b> জন\n"
             f"💰 মোট আয়: <b>{C}{total_earned:,.0f}</b>\n"]

    if referrals:
        lines.append("\n📋 <b>রেফার করা সদস্য:</b>")
        for i, ref in enumerate(referrals[:15], 1):
            joined = ref.created_at.strftime("%d %b %Y")
            lines.append(f"{i}. {ref.full_name[:20]} — {joined}")
        if count > 15:
            lines.append(f"... এবং আরো {count - 15} জন")
    else:
        lines.append("\nএখনো কেউ আপনার লিংক দিয়ে যোগ দেননি।")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()
