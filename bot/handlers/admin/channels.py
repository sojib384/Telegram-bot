from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
import re

from database.queries import ChannelQueries
from bot.filters import IsAdmin
from bot.keyboards.admin import get_channel_remove_keyboard
from bot.keyboards.inline import get_cancel_keyboard

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AddChannelStates(StatesGroup):
    waiting_for_channel = State()


def _extract_username(text: str) -> str | None:
    """Extract @username from t.me links, @username strings, or plain usernames."""
    text = text.strip()
    # https://t.me/username or t.me/username
    match = re.search(r"t\.me/([A-Za-z0-9_]{5,})", text)
    if match:
        return match.group(1)
    # @username
    if text.startswith("@"):
        return text.lstrip("@")
    return None


@router.message(F.text == "📢 Channels")
async def list_channels(message: Message, session: AsyncSession) -> None:
    channels = await ChannelQueries.get_all(session)
    if not channels:
        await message.answer(
            "📢 <b>ফোর্স জয়েন চ্যানেল</b>\n\nকোনো চ্যানেল যোগ করা হয়নি।\n\n"
            "চ্যানেল যোগ করতে: /add_channel",
            parse_mode="HTML",
        )
        return

    lines = ["📢 <b>ফোর্স জয়েন চ্যানেলসমূহ</b>\n"]
    for i, ch in enumerate(channels, 1):
        username_str = f"@{ch.channel_username}" if ch.channel_username else "—"
        lines.append(
            f"{i}. <b>{ch.channel_name}</b>\n"
            f"   ID: <code>{ch.channel_id}</code>\n"
            f"   ইউজারনেম: {username_str}"
        )

    await message.answer(
        "\n\n".join(lines) + "\n\nমুছতে চাইলে নিচের বাটনে চাপুন:",
        reply_markup=get_channel_remove_keyboard(channels),
        parse_mode="HTML",
    )


@router.message(Command("add_channel"))
async def add_channel_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelStates.waiting_for_channel)
    await message.answer(
        "📢 <b>ফোর্স জয়েন চ্যানেল যোগ করুন</b>\n\n"
        "✅ প্রথমে বটকে চ্যানেলের অ্যাডমিন করুন\n\n"
        "তারপর নিচের যেকোনো একটি পাঠান:\n"
        "• চ্যানেলের t.me লিংক (যেমন: <code>https://t.me/smart_techbangla</code>)\n"
        "• চ্যানেলের @ইউজারনেম (যেমন: <code>@smart_techbangla</code>)\n"
        "• চ্যানেলের নিউমেরিক ID (যেমন: <code>-1001234567890</code>)\n"
        "• চ্যানেল থেকে যেকোনো মেসেজ ফরওয়ার্ড করুন",
        reply_markup=get_cancel_keyboard("cancel_add_channel"),
        parse_mode="HTML",
    )


@router.message(AddChannelStates.waiting_for_channel)
async def receive_channel(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()

    channel_id = None
    channel_name = None
    channel_username = None

    # Case 1: Forwarded message from a channel
    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
        channel_name = message.forward_from_chat.title
        channel_username = message.forward_from_chat.username

    # Case 2: Text input — URL, @username, or numeric ID
    elif message.text:
        text = message.text.strip()

        # Try t.me link or @username first
        username = _extract_username(text)
        if username:
            try:
                chat = await message.bot.get_chat(f"@{username}")
                channel_id = chat.id
                channel_name = chat.title
                channel_username = chat.username or username
            except Exception as e:
                await message.answer(
                    f"❌ চ্যানেল পাওয়া যায়নি: <code>@{username}</code>\n\n"
                    f"নিশ্চিত করুন বটটি চ্যানেলের অ্যাডমিন কিনা।\n"
                    f"ত্রুটি: {e}",
                    parse_mode="HTML",
                )
                return
        else:
            # Try numeric ID
            try:
                channel_id = int(text)
                try:
                    chat = await message.bot.get_chat(channel_id)
                    channel_name = chat.title
                    channel_username = chat.username
                except Exception as e:
                    await message.answer(
                        f"❌ চ্যানেল পাওয়া যায়নি (ID: <code>{channel_id}</code>)\n\n"
                        f"নিশ্চিত করুন বটটি চ্যানেলের অ্যাডমিন কিনা।\n"
                        f"ত্রুটি: {e}",
                        parse_mode="HTML",
                    )
                    return
            except ValueError:
                await message.answer(
                    "❌ ভুল ইনপুট।\n\n"
                    "একটি t.me লিংক, @ইউজারনেম, নিউমেরিক ID পাঠান,\n"
                    "অথবা চ্যানেল থেকে একটি মেসেজ ফরওয়ার্ড করুন।",
                )
                return

    if not channel_id:
        await message.answer("❌ চ্যানেল নির্ধারণ করা যায়নি। /add_channel দিয়ে আবার চেষ্টা করুন।")
        return

    # Check for duplicates
    existing = await ChannelQueries.get_by_channel_id(session, channel_id)
    if existing:
        await message.answer(
            f"❌ <b>{existing.channel_name}</b> ইতিমধ্যে তালিকায় আছে।",
            parse_mode="HTML",
        )
        return

    # Try to create an invite link (bot must be admin)
    invite_link = None
    try:
        link = await message.bot.create_chat_invite_link(channel_id)
        invite_link = link.invite_link
    except Exception:
        # Use public link if bot can't create invite link
        if channel_username:
            invite_link = f"https://t.me/{channel_username.lstrip('@')}"

    channel = await ChannelQueries.create(
        session=session,
        channel_id=channel_id,
        channel_name=channel_name,
        channel_username=channel_username,
        invite_link=invite_link,
    )

    await message.answer(
        f"✅ <b>চ্যানেল যোগ করা হয়েছে!</b>\n\n"
        f"নাম: <b>{channel.channel_name}</b>\n"
        f"ID: <code>{channel.channel_id}</code>\n"
        f"ইউজারনেম: @{channel.channel_username or '—'}\n"
        f"লিংক: {invite_link or '—'}\n\n"
        f"এখন থেকে ব্যবহারকারীদের এই চ্যানেলে যোগ দিতে হবে।",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("remove_channel:"))
async def remove_channel_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    channel_db_id = int(callback.data.split(":")[1])
    channels = await ChannelQueries.get_all(session)
    channel = next((c for c in channels if c.id == channel_db_id), None)

    if not channel:
        await callback.answer("চ্যানেল পাওয়া যায়নি।", show_alert=True)
        return

    await ChannelQueries.delete(session, channel_db_id)
    await callback.message.edit_text(
        f"✅ <b>{channel.channel_name}</b> চ্যানেলটি ফোর্স জয়েন তালিকা থেকে সরানো হয়েছে।",
        parse_mode="HTML",
    )
    await callback.answer("চ্যানেল মুছা হয়েছে!")


@router.callback_query(F.data == "cancel_add_channel")
async def cancel_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ বাতিল করা হয়েছে।")
    await callback.answer()
