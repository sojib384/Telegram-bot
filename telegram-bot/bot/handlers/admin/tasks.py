from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from database.queries import TaskQueries, UserQueries, TransactionQueries
from database.models import TransactionType, TransactionStatus, UserTask, TaskStatus, Task
from bot.filters import IsAdmin
from bot.keyboards.admin import (
    get_task_actions, get_user_task_review,
    get_task_delete_confirm, get_task_type_keyboard,
)
from config import settings

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
C = settings.CURRENCY_SYMBOL

TASK_TYPE_EMOJI = {"subscribe": "📢", "like": "❤️", "repost": "🔁", "custom": "⭐"}


class EditTaskPriceStates(StatesGroup):
    entering_price = State()


class CreateTaskStates(StatesGroup):
    title = State()
    description = State()
    reward = State()
    task_type = State()
    task_url = State()
    total_slots = State()
    deadline = State()


# ── Task List / Overview ──────────────────────────────────────────────────────

@router.message(F.text == "📋 Manage Tasks")
async def manage_tasks(message: Message, session: AsyncSession) -> None:
    tasks = await TaskQueries.get_all_tasks(session)
    pending_count = await TaskQueries.get_pending_submissions_count(session)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ নতুন কাজ তৈরি করুন", callback_data="admin_create_task"))
    builder.row(InlineKeyboardButton(text="⏳ পর্যালোচনাধীন জমা দেখুন", callback_data="admin_view_pending"))

    now = datetime.utcnow()
    header = (
        f"📋 <b>কাজ ব্যবস্থাপনা</b>\n\n"
        f"মোট: <b>{len(tasks)}</b> | পর্যালোচনাধীন জমা: <b>{pending_count}</b>"
    )
    await message.answer(header, reply_markup=builder.as_markup(), parse_mode="HTML")

    if not tasks:
        await message.answer("📋 এখনো কোনো কাজ নেই।")
        return

    for task in tasks[:20]:
        status_emoji = "✅" if task.is_active else "❌"
        slots_str = f"{task.completed_count}/{task.total_slots}" if task.total_slots > 0 else f"{task.completed_count}/∞"
        deadline_str = f"\n⏰ শেষ: {task.deadline.strftime('%d %b %Y')}" if task.deadline else ""
        expired_str = " 🕐 মেয়াদ শেষ" if (task.deadline and task.deadline < now) else ""
        type_emoji = TASK_TYPE_EMOJI.get(task.task_type.value, "📌")

        text = (
            f"{status_emoji} {type_emoji} <b>#{task.id} {task.title}</b>{expired_str}\n"
            f"💰 {C}{task.reward:,.0f} | 🎯 {slots_str} সম্পন্ন"
            f"{deadline_str}"
        )
        await message.answer(text, reply_markup=get_task_actions(task.id, task.is_active), parse_mode="HTML")


# ── View Pending Submissions ──────────────────────────────────────────────────

@router.callback_query(F.data == "admin_view_pending")
async def view_pending_submissions(callback: CallbackQuery, session: AsyncSession) -> None:
    pending = await TaskQueries.get_pending_tasks(session)

    if not pending:
        await callback.answer("কোনো পর্যালোচনাধীন জমা নেই।", show_alert=True)
        return

    await callback.message.answer(
        f"⏳ <b>পর্যালোচনাধীন জমা ({len(pending)})</b>",
        parse_mode="HTML",
    )

    for user_task in pending[:15]:
        is_photo_proof = user_task.proof_text and user_task.proof_text.startswith("PHOTO:")
        caption_text = ""

        if is_photo_proof:
            parts = user_task.proof_text.split("|CAPTION:")
            file_id = parts[0].replace("PHOTO:", "")
            caption_text = parts[1] if len(parts) > 1 else ""
            proof_display = f"[ছবি প্রমাণ]{f' — {caption_text}' if caption_text else ''}"
        else:
            proof_display = (user_task.proof_text or "কোনো প্রমাণ নেই")[:300]

        info_text = (
            f"🔍 <b>জমা #{user_task.id}</b>\n\n"
            f"👤 {user_task.user.full_name} (<code>{user_task.user.telegram_id}</code>)\n"
            f"📋 কাজ: <b>{user_task.task.title}</b>\n"
            f"💰 পুরস্কার: {C}{user_task.task.reward:,.0f}\n"
            f"📝 প্রমাণ: {proof_display}\n"
            f"📅 {user_task.created_at.strftime('%d %b %Y %H:%M')}"
        )

        if is_photo_proof:
            try:
                await callback.message.answer_photo(
                    photo=file_id,
                    caption=info_text,
                    reply_markup=get_user_task_review(user_task.id),
                    parse_mode="HTML",
                )
            except Exception:
                await callback.message.answer(
                    info_text + "\n⚠️ ছবি লোড হয়নি।",
                    reply_markup=get_user_task_review(user_task.id),
                    parse_mode="HTML",
                )
        else:
            await callback.message.answer(
                info_text,
                reply_markup=get_user_task_review(user_task.id),
                parse_mode="HTML",
            )

    await callback.answer()


# ── Create Task FSM ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create_task")
async def create_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateTaskStates.title)
    await callback.message.answer(
        "➕ <b>নতুন কাজ তৈরি</b>\n\n"
        "ধাপ ১/৭ — কাজের <b>শিরোনাম</b> লিখুন:\n"
        "(/cancel = বাতিল)",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateTaskStates.title)
async def ct_title(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❌ শিরোনাম কমপক্ষে ২ অক্ষরের হতে হবে:")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateTaskStates.description)
    await message.answer(
        "ধাপ ২/৭ — কাজের <b>নিয়ম/বিবরণ</b> লিখুন:\n\n"
        "📝 <i>শুধু লেখা পাঠালে — শুধু লেখা সেভ হবে</i>\n"
        "🖼 <i>ছবি + caption পাঠালে — ছবি সহ নিয়ম সেভ হবে</i>",
        parse_mode="HTML",
    )


@router.message(CreateTaskStates.description)
async def ct_description(message: Message, state: FSMContext) -> None:
    # Cancel check
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return

    # Accept photo with caption (photo + text together)
    if message.photo:
        photo_id = message.photo[-1].file_id
        caption = (message.caption or "").strip()
        if len(caption) < 10:
            await message.answer(
                "❌ ছবির সাথে নিয়মের বিবরণ লিখুন (caption-এ কমপক্ষে ১০ অক্ষর):"
            )
            return
        await state.update_data(description=caption, description_photo_id=photo_id)
    elif message.text:
        # Plain text only
        text = message.text.strip()
        await state.update_data(description=text, description_photo_id=None)
    else:
        await message.answer("❌ লেখা বা ছবি+লেখা পাঠান:")
        return

    await state.set_state(CreateTaskStates.reward)
    await message.answer(f"ধাপ ৩/৭ — <b>পুরস্কারের পরিমাণ</b> লিখুন ({C} তে):", parse_mode="HTML")


@router.message(CreateTaskStates.reward)
async def ct_reward(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return
    try:
        reward = float(message.text.replace(",", "").strip())
        if reward <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ ভুল পরিমাণ। ধনাত্মক সংখ্যা লিখুন (যেমন: 20):")
        return
    await state.update_data(reward=reward)
    await state.set_state(CreateTaskStates.task_type)
    await message.answer(
        "ধাপ ৪/৭ — কাজের <b>ধরন</b> বেছে নিন:",
        reply_markup=get_task_type_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("tasktype:"), CreateTaskStates.task_type)
async def ct_task_type(callback: CallbackQuery, state: FSMContext) -> None:
    task_type = callback.data.split(":")[1]
    await state.update_data(task_type=task_type)
    await state.set_state(CreateTaskStates.task_url)
    await callback.message.answer(
        "ধাপ ৫/৭ — কাজের <b>URL/লিংক</b> লিখুন\n"
        "(না থাকলে <code>none</code> লিখুন):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateTaskStates.task_url)
async def ct_url(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return
    url = None if message.text.lower().strip() == "none" else message.text.strip()
    await state.update_data(task_url=url)
    await state.set_state(CreateTaskStates.total_slots)
    await message.answer(
        "ধাপ ৬/৭ — মোট <b>স্লট সংখ্যা</b> লিখুন\n"
        "(0 = সীমাহীন):",
        parse_mode="HTML",
    )


@router.message(CreateTaskStates.total_slots)
async def ct_slots(message: Message, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return
    try:
        slots = int(message.text.strip())
        if slots < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ 0 বা ধনাত্মক সংখ্যা লিখুন:")
        return
    await state.update_data(total_slots=slots)
    await state.set_state(CreateTaskStates.deadline)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="৭ দিন", callback_data="deadline:7"),
        InlineKeyboardButton(text="১৪ দিন", callback_data="deadline:14"),
        InlineKeyboardButton(text="৩০ দিন", callback_data="deadline:30"),
    )
    builder.row(InlineKeyboardButton(text="⏳ মেয়াদহীন", callback_data="deadline:0"))
    await message.answer(
        "ধাপ ৭/৭ — <b>মেয়াদ</b> বেছে নিন বা YYYY-MM-DD ফরম্যাটে লিখুন:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("deadline:"), CreateTaskStates.deadline)
async def ct_deadline_button(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    days = int(callback.data.split(":")[1])
    deadline = datetime.utcnow() + timedelta(days=days) if days > 0 else None
    await _finish_create_task(callback.message, session, state, deadline)
    await callback.answer()


@router.message(CreateTaskStates.deadline)
async def ct_deadline_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ বাতিল।")
        return
    text = message.text.strip()
    if text.lower() in ("none", "0", "no", "নেই"):
        deadline = None
    else:
        try:
            deadline = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await message.answer("❌ ভুল ফরম্যাট। YYYY-MM-DD ব্যবহার করুন (যেমন: 2026-07-31) বা উপরের বাটন চাপুন:")
            return
    await _finish_create_task(message, session, state, deadline)


async def _finish_create_task(message, session, state, deadline):
    data = await state.get_data()
    await state.clear()

    # message.chat.id == admin telegram_id for both plain Message and callback.message
    admin_tg_id = message.chat.id
    admin_user = await UserQueries.get_by_telegram_id(session, admin_tg_id)

    task = await TaskQueries.create(
        session=session,
        title=data["title"],
        description=data["description"],
        reward=data["reward"],
        task_type=data.get("task_type", "custom"),
        created_by=admin_user.id if admin_user else 1,
        task_url=data.get("task_url"),
        total_slots=data.get("total_slots", 0),
        deadline=deadline,
        description_photo_id=data.get("description_photo_id"),
    )

    type_emoji = TASK_TYPE_EMOJI.get(data.get("task_type", "custom"), "⭐")
    slots = data.get("total_slots", 0)
    deadline_str = deadline.strftime("%d %b %Y") if deadline else "মেয়াদহীন"

    await message.answer(
        f"✅ <b>কাজ তৈরি হয়েছে!</b>\n\n"
        f"{type_emoji} <b>#{task.id} {task.title}</b>\n"
        f"📝 {task.description[:100]}\n"
        f"💰 পুরস্কার: {C}{task.reward:,.0f}\n"
        f"🎯 স্লট: {'সীমাহীন' if slots == 0 else slots}\n"
        f"⏰ মেয়াদ: {deadline_str}\n"
        f"🔗 URL: {task.task_url or '—'}",
        parse_mode="HTML",
    )


# ── Toggle Enable/Disable ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_toggle_task:"))
async def toggle_task(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    task_id = int(parts[1])
    new_state = bool(int(parts[2]))
    await TaskQueries.toggle_task(session, task_id, new_state)
    status = "চালু" if new_state else "বন্ধ"
    await callback.answer(f"কাজ {status} করা হয়েছে!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=get_task_actions(task_id, new_state))


# ── Edit Price ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_edit_price:"))
async def edit_price_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])
    await state.set_state(EditTaskPriceStates.entering_price)
    await state.update_data(task_id=task_id)
    await callback.message.answer(
        f"✏️ <b>কাজ #{task_id} এর দাম পরিবর্তন</b>\n\nনতুন পুরস্কার লিখুন ({C} তে):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditTaskPriceStates.entering_price)
async def receive_new_price(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    task_id = data.get("task_id")
    await state.clear()
    try:
        new_price = float(message.text.replace(",", "").strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ ভুল পরিমাণ।")
        return
    task = await TaskQueries.get_by_id(session, task_id)
    if not task:
        await message.answer("❌ কাজ পাওয়া যায়নি।")
        return
    old_price = task.reward
    await session.execute(
        update(Task).where(Task.id == task_id).values(reward=new_price)
    )
    await session.commit()
    await message.answer(
        f"✅ <b>দাম আপডেট!</b>\n\n"
        f"📋 <b>{task.title}</b>\n"
        f"{C}{old_price:,.0f} → <b>{C}{new_price:,.0f}</b>",
        parse_mode="HTML",
    )


# ── Delete Task ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_delete_task:"))
async def delete_task_confirm(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        f"⚠️ <b>কাজ #{task_id} মুছে ফেলবেন?</b>\n\nসব জমা ডেটাও মুছে যাবে!",
        reply_markup=get_task_delete_confirm(task_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete:"))
async def delete_task_execute(callback: CallbackQuery, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])
    task = await TaskQueries.get_by_id(session, task_id)
    if not task:
        await callback.answer("কাজ পাওয়া যায়নি।", show_alert=True)
        return
    title = task.title
    await TaskQueries.delete_task(session, task_id)
    await callback.message.edit_text(f"🗑 <b>মুছে ফেলা হয়েছে:</b> {title}", parse_mode="HTML")
    await callback.answer("মুছে ফেলা হয়েছে!")


@router.callback_query(F.data == "admin_cancel_delete")
async def cancel_delete(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ মুছে ফেলা বাতিল।")
    await callback.answer()


# ── Approve / Reject Submissions ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve_task:"))
async def approve_task(callback: CallbackQuery, session: AsyncSession) -> None:
    user_task_id = int(callback.data.split(":")[1])
    user_task = await TaskQueries.get_user_task_by_id(session, user_task_id)

    if not user_task:
        await callback.answer("জমা পাওয়া যায়নি।", show_alert=True)
        return
    if user_task.status != TaskStatus.PENDING:
        await callback.answer("এই জমা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    # Mark completed + increment task count
    await TaskQueries.complete_task(session, user_task_id)
    # Credit balance
    await UserQueries.update_balance(session, user_task.user_id, user_task.task.reward)
    # Create reward transaction (completed immediately)
    tx = await TransactionQueries.create(
        session=session,
        user_id=user_task.user_id,
        type=TransactionType.REWARD,
        amount=user_task.task.reward,
        details=f"কাজের পুরস্কার: {user_task.task.title}",
    )
    tx.status = TransactionStatus.COMPLETED
    await session.commit()

    # Notify user
    try:
        await callback.bot.send_message(
            user_task.user.telegram_id,
            f"🎉 <b>কাজ অনুমোদিত!</b>\n\n"
            f"📌 <b>{user_task.task.title}</b>\n"
            f"💰 <b>{C}{user_task.task.reward:,.0f}</b> আপনার ব্যালেন্সে যোগ হয়েছে!\n\n"
            f"আরো কাজের জন্য 📋 Available Tasks চাপুন।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Update admin message
    try:
        original = callback.message.text or callback.message.caption or ""
        new_text = original + f"\n\n✅ <b>অনুমোদিত</b> — {C}{user_task.task.reward:,.0f} যোগ হয়েছে"
        if callback.message.photo:
            await callback.message.edit_caption(caption=new_text, parse_mode="HTML")
        else:
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass

    await callback.answer(f"✅ অনুমোদিত! {C}{user_task.task.reward:,.0f} ক্রেডিট।")


@router.callback_query(F.data.startswith("reject_task:"))
async def reject_task(callback: CallbackQuery, session: AsyncSession) -> None:
    user_task_id = int(callback.data.split(":")[1])
    user_task = await TaskQueries.get_user_task_by_id(session, user_task_id)

    if not user_task:
        await callback.answer("জমা পাওয়া যায়নি।", show_alert=True)
        return
    if user_task.status != TaskStatus.PENDING:
        await callback.answer("এই জমা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    await TaskQueries.reject_task(session, user_task_id)

    # Notify user
    try:
        await callback.bot.send_message(
            user_task.user.telegram_id,
            f"❌ <b>কাজ বাতিল হয়েছে</b>\n\n"
            f"📌 <b>{user_task.task.title}</b>\n\n"
            f"প্রমাণ যথেষ্ট ছিল না। সঠিক প্রমাণ দিয়ে আবার চেষ্টা করুন।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Update admin message
    try:
        original = callback.message.text or callback.message.caption or ""
        new_text = original + "\n\n❌ <b>বাতিল</b>"
        if callback.message.photo:
            await callback.message.edit_caption(caption=new_text, parse_mode="HTML")
        else:
            await callback.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass

    await callback.answer("❌ বাতিল করা হয়েছে।")
