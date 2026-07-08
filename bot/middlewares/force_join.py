from typing import Any, Awaitable, Callable, Dict, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import ChannelQueries, UserQueries
from config import settings


def _build_join_keyboard(not_joined) -> "InlineKeyboardMarkup":
    builder = InlineKeyboardBuilder()
    for ch in not_joined:
        if ch.invite_link:
            url = ch.invite_link
        elif ch.channel_username:
            url = f"https://t.me/{ch.channel_username.lstrip('@')}"
        else:
            url = "https://t.me/"
        builder.row(InlineKeyboardButton(text=f"📢 {ch.channel_name}", url=url))
    builder.row(InlineKeyboardButton(text="✅ যোগ দিয়েছি — যাচাই করুন", callback_data="check_join"))
    return builder.as_markup()


def _build_join_text(not_joined) -> str:
    channel_list = "\n".join(f"  ▪️ {ch.channel_name}" for ch in not_joined)
    return (
        "⚠️ <b>প্রবেশাধিকার সীমিত!</b>\n\n"
        "এই বট ব্যবহার করতে নিচের চ্যানেলে যোগ দিতে হবে:\n\n"
        f"{channel_list}\n\n"
        "চ্যানেলে যোগ দেওয়ার পর\n"
        "<b>✅ যোগ দিয়েছি — যাচাই করুন</b> বাটনে চাপুন।"
    )


async def _check_membership(bot, channel, user_id: int) -> bool:
    """Returns True if user is a member of the channel."""
    try:
        member = await bot.get_chat_member(channel.channel_id, user_id)
        return member.status not in ("left", "kicked", "banned")
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    except Exception:
        return False


class ForceJoinMiddleware(BaseMiddleware):
    """
    Registered on dp.message and dp.callback_query so event is
    already the inner Message / CallbackQuery — never an Update wrapper.
    """

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data.get("session")
        bot = data.get("bot")

        if not session or not bot:
            return await handler(event, data)

        user = event.from_user
        if not user:
            return await handler(event, data)

        # Admins always bypass
        if user.id in settings.admin_ids:
            return await handler(event, data)

        required_channels = await ChannelQueries.get_required_channels(session)
        if not required_channels:
            return await handler(event, data)

        # Check which channels the user hasn't joined
        not_joined = []
        for ch in required_channels:
            joined = await _check_membership(bot, ch, user.id)
            if not joined:
                not_joined.append(ch)

        # ── User has joined everything ──────────────────────────────────────
        if not not_joined:
            if isinstance(event, CallbackQuery) and event.data == "check_join":
                # Verification passed — greet and show menu
                await event.answer("✅ যাচাই সফল! স্বাগতম!", show_alert=True)
                db_user = await UserQueries.get_by_telegram_id(session, user.id)
                from bot.keyboards.main_menu import get_main_menu_for
                name = user.full_name or "বন্ধু"
                if db_user:
                    await event.message.answer(
                        f"🎉 স্বাগতম, <b>{name}</b>!\n\nমূল মেনু:",
                        reply_markup=get_main_menu_for(user.id),
                        parse_mode="HTML",
                    )
                else:
                    # Not registered yet — send /start to register
                    await event.message.answer(
                        f"🎉 যাচাই সফল!\n\n/start চাপুন রেজিস্ট্রেশন করতে।",
                        parse_mode="HTML",
                    )
                return  # Do NOT call the handler for check_join
            # Normal flow — let the handler run
            return await handler(event, data)

        # ── User has NOT joined all channels ────────────────────────────────
        keyboard = _build_join_keyboard(not_joined)
        text = _build_join_text(not_joined)

        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")

        elif isinstance(event, CallbackQuery):
            if event.data == "check_join":
                # They clicked verify but still haven't joined
                names = ", ".join(ch.channel_name for ch in not_joined)
                await event.answer(
                    f"❌ এখনো যোগ দেননি:\n{names}",
                    show_alert=True,
                )
                # Re-send the join prompt so buttons are visible
                try:
                    await event.message.edit_reply_markup(reply_markup=keyboard)
                except Exception:
                    await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await event.answer()
                await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

        # Block — do NOT call the actual handler
        return
