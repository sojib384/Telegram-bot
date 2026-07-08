from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, TransactionQueries, ChannelQueries, BotSettingsQueries
from database.models import TransactionType, TransactionStatus
from bot.keyboards.main_menu import get_main_menu, get_main_menu_for, get_profile_inline
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)

    referral_code = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        referral_code = args[1].strip()

    if not user:
        referred_by_id = None
        if referral_code:
            referrer = await UserQueries.get_by_referral_code(session, referral_code)
            if referrer and referrer.telegram_id != message.from_user.id:
                referred_by_id = referrer.id

        user = await UserQueries.create(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            referred_by_id=referred_by_id,
        )

        if referred_by_id:
            # No signup bonus — commission is only paid when the referred user withdraws
            try:
                referrer_obj = await session.get(type(user), referred_by_id)
                if referrer_obj:
                    await message.bot.send_message(
                        referrer_obj.telegram_id,
                        f"👋 <b>{user.full_name}</b> আপনার লিংক দিয়ে যোগ দিয়েছেন!\n\n"
                        f"তিনি উত্তোলন করলে আপনি ১০% কমিশন পাবেন।",
                        parse_mode="HTML",
                    )
            except Exception:
                pass

        welcome = (
            f"👋 <b>স্বাগতম, {user.full_name}!</b>\n\n"
            f"আপনার অ্যাকাউন্ট তৈরি হয়েছে।\n"
            f"আপনার রেফারেল কোড: <code>{user.referral_code}</code>\n\n"
            f"নিচের মেনু থেকে শুরু করুন।"
        )
    else:
        await UserQueries.update_last_active(session, user.id)
        welcome = (
            f"👋 <b>ফিরে এসেছেন, {user.full_name}!</b>\n\n"
            f"ব্যালেন্স: <b>{C}{user.balance:,.0f}</b>\n"
            f"নিচের মেনু ব্যবহার করুন।"
        )

    await message.answer(welcome, reply_markup=get_main_menu_for(message.from_user.id), parse_mode="HTML")


@router.message(F.text == "🔙 Back to Menu")
async def back_to_menu(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।", reply_markup=get_main_menu_for(message.from_user.id))
        return
    await message.answer("🏠 মূল মেনু", reply_markup=get_main_menu_for(message.from_user.id))


@router.callback_query(F.data == "check_join")
async def verify_channel_join(callback: CallbackQuery, session: AsyncSession) -> None:
    """
    Fallback handler for check_join — runs when the middleware lets it through
    (e.g. for admin users, or when user has already joined all channels).
    Re-checks membership and shows main menu or re-shows join buttons.
    """
    bot = callback.bot
    user = callback.from_user

    required_channels = await ChannelQueries.get_required_channels(session)

    # No channels configured — just show main menu
    if not required_channels:
        await callback.answer("✅ স্বাগতম!", show_alert=False)
        db_user = await UserQueries.get_by_telegram_id(session, user.id)
        if db_user:
            await callback.message.answer("🏠 মূল মেনু:", reply_markup=get_main_menu_for(callback.from_user.id))
        return

    # Check each channel
    not_joined = []
    for ch in required_channels:
        try:
            member = await bot.get_chat_member(ch.channel_id, user.id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append(ch)
        except (TelegramForbiddenError, TelegramBadRequest):
            not_joined.append(ch)
        except Exception:
            not_joined.append(ch)

    if not_joined:
        # Still not joined — show alert + rebuild join buttons
        names = "\n".join(f"▪️ {ch.channel_name}" for ch in not_joined)
        await callback.answer(
            f"❌ এখনো যোগ দেননি:\n{names}",
            show_alert=True,
        )
        builder = InlineKeyboardBuilder()
        for ch in not_joined:
            url = ch.invite_link or (
                f"https://t.me/{ch.channel_username.lstrip('@')}"
                if ch.channel_username else "https://t.me/"
            )
            builder.row(InlineKeyboardButton(text=f"📢 {ch.channel_name}", url=url))
        builder.row(InlineKeyboardButton(
            text="✅ যোগ দিয়েছি — যাচাই করুন",
            callback_data="check_join",
        ))
        try:
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        except Exception:
            text = (
                "⚠️ <b>প্রবেশাধিকার সীমিত!</b>\n\n"
                "এই বট ব্যবহার করতে নিচের চ্যানেলে যোগ দিতে হবে:\n\n"
                + "\n".join(f"  ▪️ {ch.channel_name}" for ch in not_joined)
                + "\n\nযোগ দেওয়ার পর <b>✅ যোগ দিয়েছি — যাচাই করুন</b> চাপুন।"
            )
            await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return

    # All joined — welcome!
    await callback.answer("✅ যাচাই সফল! স্বাগতম!", show_alert=True)
    db_user = await UserQueries.get_by_telegram_id(session, user.id)
    name = user.full_name or "বন্ধু"
    if db_user:
        await callback.message.answer(
            f"🎉 স্বাগতম, <b>{name}</b>!\n\nমূল মেনু:",
            reply_markup=get_main_menu_for(callback.from_user.id),
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            f"🎉 যাচাই সফল! /start পাঠান।",
            parse_mode="HTML",
        )


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    """Anyone can use this to find their Telegram numeric ID."""
    await message.answer(
        f"🆔 <b>আপনার Telegram ID:</b>\n\n"
        f"<code>{message.from_user.id}</code>\n\n"
        f"এই নম্বরটি কপি করে ADMIN_IDS সিক্রেটে দিন।",
        parse_mode="HTML",
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 প্রোফাইল")
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("প্রথমে /start করুন।")
        return

    referrals = await UserQueries.get_referrals(session, user.id)
    username_str = f"@{user.username}" if user.username else "—"
    joined_str = user.created_at.strftime("%d %b %Y")

    text = (
        f"👤 <b>আপনার প্রোফাইল</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📛 নাম: <b>{user.full_name}</b>\n"
        f"🔗 ইউজারনেম: {username_str}\n"
        f"📅 যোগদান: {joined_str}\n\n"
        f"💰 ব্যালেন্স: <b>{C}{user.balance:,.0f}</b>\n"
        f"📈 মোট আয়: <b>{C}{user.total_earned:,.0f}</b>\n"
        f"🏧 মোট উত্তোলন: <b>{C}{user.total_withdrawn:,.0f}</b>\n"
        f"👥 রেফারেল: <b>{len(referrals)}</b>\n\n"
        f"🔑 রেফারেল কোড: <code>{user.referral_code}</code>"
    )

    await message.answer(text, reply_markup=get_profile_inline(user.id), parse_mode="HTML")
