from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import UserQueries, TaskQueries, TransactionQueries
from database.models import TransactionStatus, TaskStatus, TransactionType
from bot.keyboards.inline import (
    get_task_keyboard, get_cancel_keyboard,
    get_category_keyboard, get_subcategory_keyboard,
    get_task_summary_keyboard,
    get_advertiser_review_keyboard,
    TASK_CATEGORIES, get_task_min_reward,
)
from bot.keyboards.main_menu import get_main_menu_for
from config import settings

router = Router()
C = settings.CURRENCY_SYMBOL

STATUS_LABELS = {
    TaskStatus.PENDING:   "⏳ অপেক্ষমাণ",
    TaskStatus.COMPLETED: "✅ সম্পন্ন",
    TaskStatus.REJECTED:  "❌ বাতিল",
}
PLATFORM_FEE_PCT = 0.20


# ── FSM States ─────────────────────────────────────────────────────────────────

class CreateTaskStates(StatesGroup):
    choosing_category    = State()
    choosing_subcategory = State()
    entering_description = State()   # Advertiser writes task rules
    entering_proof1      = State()   # Screenshot proof 1 requirement
    entering_proof2      = State()   # Screenshot proof 2 requirement
    entering_proof3      = State()   # Text proof requirement
    entering_link        = State()
    entering_workers     = State()
    entering_reward      = State()
    confirming           = State()


class SubmitProofState(StatesGroup):
    waiting_proof1 = State()   # Screenshot 1
    waiting_proof2 = State()   # Screenshot 2
    waiting_proof3 = State()   # Text proof


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER — Available Tasks
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 কাজ দেখুন")
async def available_tasks(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user or user.is_blocked:
        await message.answer("🚫 অ্যাক্সেস নেই।")
        return

    tasks = await TaskQueries.get_active_tasks(session, user.id)
    if not tasks:
        await message.answer("📋 এখন কোনো কাজ নেই। নতুন কাজ এলে জানানো হবে।")
        return

    await message.answer(f"📋 <b>{len(tasks)}টি কাজ পাওয়া গেছে:</b>", parse_mode="HTML")
    for task in tasks[:10]:
        slots_info = f" | 🎯 {task.completed_count}/{task.total_slots}" if task.total_slots > 0 else ""
        await message.answer(
            f"📌 <b>{task.title}</b>{slots_info}\n"
            f"💰 পুরস্কার: <b>{C}{task.reward:,.0f}</b>\n"
            f"📝 {task.description[:200]}",
            reply_markup=get_task_keyboard(task.id),
            parse_mode="HTML",
        )


# ── My Work ────────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 আমার কাজ")
async def my_work_message(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        return
    history = await TaskQueries.get_user_task_history(session, user.id, limit=50)
    completed = [h for h in history if h.status == TaskStatus.COMPLETED]
    pending   = [h for h in history if h.status == TaskStatus.PENDING]
    rejected  = [h for h in history if h.status == TaskStatus.REJECTED]
    earned    = sum(h.task.reward for h in completed)

    lines = [
        "📊 <b>My Work</b>\n",
        f"✅ সম্পন্ন: {len(completed)}  ⏳ অপেক্ষমাণ: {len(pending)}  ❌ বাতিল: {len(rejected)}",
        f"💰 মোট আয়: <b>{C}{earned:,.0f}</b>",
    ]
    if pending:
        lines.append("\n⏳ <b>অপেক্ষমাণ:</b>")
        for ut in pending[:5]:
            lines.append(f"  • {ut.task.title} — {C}{ut.task.reward:,.0f}")
    if completed:
        lines.append("\n✅ <b>সাম্প্রতিক সম্পন্ন:</b>")
        for ut in completed[:5]:
            lines.append(f"  • {ut.task.title} — +{C}{ut.task.reward:,.0f}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  ADVERTISER — My Order
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📦 আমার অর্ডার")
async def my_order(message: Message, session: AsyncSession) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user:
        return
    tasks = await TaskQueries.get_tasks_by_creator(session, user.id)
    if not tasks:
        await message.answer("📦 আপনি এখনো কোনো কাজ তৈরি করেননি।\n➕ Create Task থেকে কাজ দিন।")
        return

    b = InlineKeyboardBuilder()
    lines = ["📦 <b>My Order — আমার কাজ সমূহ</b>\n"]
    for i, task in enumerate(tasks[:10], 1):
        status = "✅" if task.is_active else "🔴"
        lines.append(
            f"{i}. {status} <b>{task.title}</b>\n"
            f"   👥 {task.completed_count}/{task.total_slots} সম্পন্ন | {C}{task.reward:,.0f}/জন"
        )
        b.row(InlineKeyboardButton(
            text=f"📋 {task.title[:30]} দেখুন",
            callback_data=f"my_order_task:{task.id}",
        ))

    await message.answer("\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("my_order_task:"))
async def my_order_task_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    task_id = int(callback.data.split(":")[1])
    task = await TaskQueries.get_by_id(session, task_id)
    if not task:
        await callback.answer("কাজ পাওয়া যায়নি।", show_alert=True)
        return

    # Verify ownership
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user or task.created_by != user.id:
        await callback.answer("আপনি এই কাজের মালিক নন।", show_alert=True)
        return

    pending = await TaskQueries.get_pending_submissions_for_task(session, task_id)

    header = (
        f"📌 <b>{task.title}</b>\n"
        f"👥 {task.completed_count}/{task.total_slots} সম্পন্ন\n"
        f"⏳ অপেক্ষমাণ: {len(pending)} টি জমা\n"
    )
    await callback.message.answer(header, parse_mode="HTML")

    if not pending:
        await callback.message.answer("এখন কোনো পর্যালোচনার কাজ নেই।")
    else:
        for ut in pending[:5]:
            await _send_submission_for_review(callback.message, ut)

    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER — Submit Proof
# ══════════════════════════════════════════════════════════════════════════════

async def _send_submission_for_review(message, ut) -> None:
    """Parse combined proof and send photos + text properly for review."""
    proof = ut.proof_text or ""
    worker_name = ut.user.full_name
    date_str = ut.created_at.strftime("%d %b %H:%M")

    # New combined format: PHOTO1:{id}||PHOTO2:{id}||TEXT3:{text}
    if proof.startswith("PHOTO1:"):
        parts = {}
        for segment in proof.split("||"):
            if segment.startswith("PHOTO1:"):
                parts["p1"] = segment[7:]
            elif segment.startswith("PHOTO2:"):
                parts["p2"] = segment[7:]
            elif segment.startswith("TEXT3:"):
                parts["t3"] = segment[6:]

        p1 = parts.get("p1", "")
        p2 = parts.get("p2", "")
        t3 = parts.get("t3", "")

        header = f"👤 <b>{worker_name}</b> | 🕐 {date_str}"

        if p1:
            try:
                await message.answer_photo(p1, caption=f"📸 স্ক্রিনশট ১\n{header}", parse_mode="HTML")
            except Exception:
                pass
        if p2:
            try:
                await message.answer_photo(p2, caption=f"📸 স্ক্রিনশট ২", parse_mode="HTML")
            except Exception:
                pass

        await message.answer(
            f"📝 টেক্সট: {t3 or '—'}\n{header}",
            reply_markup=get_advertiser_review_keyboard(ut.id),
            parse_mode="HTML",
        )

    # Legacy single-photo format: PHOTO:{id}|CAPTION:{text}
    elif proof.startswith("PHOTO:"):
        file_id = proof.split("|")[0][6:]
        caption_part = ""
        if "|CAPTION:" in proof:
            caption_part = "\n📝 " + proof.split("|CAPTION:")[1]
        try:
            await message.answer_photo(
                file_id,
                caption=f"👤 <b>{worker_name}</b>{caption_part}\n🕐 {date_str}",
                reply_markup=get_advertiser_review_keyboard(ut.id),
                parse_mode="HTML",
            )
        except Exception:
            await message.answer(
                f"👤 <b>{worker_name}</b>\n📝 {proof[:200]}\n🕐 {date_str}",
                reply_markup=get_advertiser_review_keyboard(ut.id),
                parse_mode="HTML",
            )

    # Plain text proof
    else:
        await message.answer(
            f"👤 <b>{worker_name}</b>\n📝 {proof[:300] or '—'}\n🕐 {date_str}",
            reply_markup=get_advertiser_review_keyboard(ut.id),
            parse_mode="HTML",
        )


def _parse_proof_labels(description: str):
    """Extract (proof1_label, proof2_label, proof3_label) from task description."""
    p1 = p2 = p3 = ""
    for line in description.split("\n"):
        line = line.strip()
        if line.startswith("📸 স্ক্রিনশট ১:"):
            p1 = line.replace("📸 স্ক্রিনশট ১:", "").strip()
        elif line.startswith("📸 স্ক্রিনশট ২:"):
            p2 = line.replace("📸 স্ক্রিনশট ২:", "").strip()
        elif line.startswith("📝 টেক্সট:"):
            p3 = line.replace("📝 টেক্সট:", "").strip()
    return p1, p2, p3


@router.callback_query(F.data.startswith("submit_task:"))
async def submit_task_callback(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user or user.is_blocked:
        await callback.answer("অ্যাক্সেস নেই।", show_alert=True)
        return

    task = await TaskQueries.get_by_id(session, task_id)
    if not task or not task.is_active:
        await callback.answer("এই কাজটি আর পাওয়া যাচ্ছে না।", show_alert=True)
        return
    if task.deadline and task.deadline < datetime.utcnow():
        await callback.answer("⏰ কাজের মেয়াদ শেষ।", show_alert=True)
        return
    if task.total_slots > 0 and task.completed_count >= task.total_slots:
        await callback.answer("সব স্লট পূর্ণ।", show_alert=True)
        return
    if await TaskQueries.get_user_task(session, user.id, task_id):
        await callback.answer("আপনি ইতিমধ্যে এই কাজ জমা দিয়েছেন।", show_alert=True)
        return

    p1, p2, p3 = _parse_proof_labels(task.description or "")

    await state.set_state(SubmitProofState.waiting_proof1)
    await state.update_data(
        task_id=task_id,
        task_title=task.title,
        task_reward=task.reward,
        task_created_by=task.created_by,
        proof1_label=p1,
        proof2_label=p2,
        proof3_label=p3,
    )

    await callback.message.answer(
        f"📋 <b>কাজ জমা — ধাপ ১/৩</b>\n\n"
        f"📌 <b>{task.title}</b>\n"
        + (f"🔗 {task.task_url}\n" if task.task_url else "")
        + f"\n📸 <b>স্ক্রিনশট ১ পাঠান:</b>\n"
        + (f"<i>{p1}</i>" if p1 else "<i>প্রথম স্ক্রিনশট পাঠান</i>"),
        reply_markup=get_cancel_keyboard("cancel_submit"),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 1 — Screenshot 1 ──────────────────────────────────────────────────

@router.message(StateFilter(SubmitProofState.waiting_proof1))
async def receive_proof1(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer(
            "❌ ছবি পাঠান (স্ক্রিনশট)। টেক্সট গ্রহণ করা হবে না।",
            reply_markup=get_cancel_keyboard("cancel_submit"),
        )
        return

    best: PhotoSize = message.photo[-1]
    data = await state.get_data()
    p2 = data.get("proof2_label", "")

    await state.update_data(proof1_file_id=best.file_id)
    await state.set_state(SubmitProofState.waiting_proof2)

    await message.answer(
        f"✅ স্ক্রিনশট ১ পেয়েছি!\n\n"
        f"📋 <b>ধাপ ২/৩ — স্ক্রিনশট ২ পাঠান:</b>\n"
        + (f"<i>{p2}</i>" if p2 else "<i>দ্বিতীয় স্ক্রিনশট পাঠান</i>"),
        reply_markup=get_cancel_keyboard("cancel_submit"),
        parse_mode="HTML",
    )


# ── Step 2 — Screenshot 2 ──────────────────────────────────────────────────

@router.message(StateFilter(SubmitProofState.waiting_proof2))
async def receive_proof2(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer(
            "❌ ছবি পাঠান (স্ক্রিনশট)। টেক্সট গ্রহণ করা হবে না।",
            reply_markup=get_cancel_keyboard("cancel_submit"),
        )
        return

    best: PhotoSize = message.photo[-1]
    data = await state.get_data()
    p3 = data.get("proof3_label", "")

    await state.update_data(proof2_file_id=best.file_id)
    await state.set_state(SubmitProofState.waiting_proof3)

    await message.answer(
        f"✅ স্ক্রিনশট ২ পেয়েছি!\n\n"
        f"📋 <b>ধাপ ৩/৩ — টেক্সট প্রমাণ পাঠান:</b>\n"
        + (f"<i>{p3}</i>" if p3 else "<i>টেক্সট প্রমাণ পাঠান</i>"),
        reply_markup=get_cancel_keyboard("cancel_submit"),
        parse_mode="HTML",
    )


# ── Step 3 — Text proof → submit all ──────────────────────────────────────

@router.message(StateFilter(SubmitProofState.waiting_proof3))
async def receive_proof3(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not (message.text or message.caption):
        await message.answer(
            "❌ টেক্সট লিখে পাঠান:",
            reply_markup=get_cancel_keyboard("cancel_submit"),
        )
        return

    data = await state.get_data()
    task_id         = data.get("task_id")
    task_title      = data.get("task_title", "কাজ")
    task_reward     = data.get("task_reward", 0)
    task_created_by = data.get("task_created_by")
    proof1_file_id  = data.get("proof1_file_id", "")
    proof2_file_id  = data.get("proof2_file_id", "")
    text_proof      = (message.text or message.caption or "").strip()
    await state.clear()

    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user or not task_id:
        return

    task = await TaskQueries.get_by_id(session, task_id)
    if not task or not task.is_active:
        await message.answer("❌ কাজটি আর সক্রিয় নেই।", reply_markup=get_main_menu_for(message.from_user.id))
        return
    if await TaskQueries.get_user_task(session, user.id, task_id):
        await message.answer("❌ আপনি ইতিমধ্যে এই কাজ জমা দিয়েছেন।", reply_markup=get_main_menu_for(message.from_user.id))
        return

    # Store all 3 proofs together
    combined_proof = f"PHOTO1:{proof1_file_id}||PHOTO2:{proof2_file_id}||TEXT3:{text_proof}"
    user_task = await TaskQueries.submit_task(session, user.id, task_id, combined_proof)

    # ── Notify Admins ──────────────────────────────────────────────────────────
    from bot.keyboards.admin import get_user_task_review
    admin_text = (
        f"📋 <b>নতুন জমা #{user_task.id}</b>\n"
        f"👤 {user.full_name} (<code>{user.telegram_id}</code>)\n"
        f"📌 {task_title} | 💰 {C}{task_reward:,.0f}\n"
        f"📝 টেক্সট: {text_proof[:150]}"
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_photo(admin_id, photo=proof1_file_id,
                caption=f"📸 স্ক্রিনশট ১\n{admin_text}",
                reply_markup=get_user_task_review(user_task.id), parse_mode="HTML")
        except Exception:
            pass
        try:
            await message.bot.send_photo(admin_id, photo=proof2_file_id,
                caption=f"📸 স্ক্রিনশট ২ (#{user_task.id})", parse_mode="HTML")
        except Exception:
            pass

    # ── Notify Advertiser (simple — review via My Order) ──────────────────────
    if task_created_by:
        advertiser = await UserQueries.get_by_id(session, task_created_by)
        if advertiser and advertiser.telegram_id not in settings.admin_ids:
            try:
                await message.bot.send_message(
                    advertiser.telegram_id,
                    f"📬 <b>নতুন জমা এসেছে!</b>\n"
                    f"📌 {task_title} | 👤 {user.full_name}\n\n"
                    f"📦 <b>My Order</b> বাটনে গিয়ে পর্যালোচনা করুন।",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    await message.answer(
        f"✅ <b>৩টি প্রমাণ জমা হয়েছে!</b>\n\n"
        f"📌 <b>{task_title}</b>\n"
        f"💰 পুরস্কার: <b>{C}{task_reward:,.0f}</b>\n\n"
        f"সঠিক কাজ হলে <b>২৪ ঘন্টার মধ্যে</b> ব্যালেন্সে জমা হবে।",
        reply_markup=get_main_menu_for(message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel_submit")
async def cancel_submit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("❌ বাতিল।", reply_markup=get_main_menu_for(callback.from_user.id))
    await callback.answer()


# ── Advertiser Approve ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adv_approve:"))
async def advertiser_approve(callback: CallbackQuery, session: AsyncSession) -> None:
    user_task_id = int(callback.data.split(":")[1])
    user_task = await TaskQueries.get_user_task_by_id(session, user_task_id)

    if not user_task:
        await callback.answer("জমা পাওয়া যায়নি।", show_alert=True)
        return
    if user_task.status != TaskStatus.PENDING:
        await callback.answer("ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    advertiser = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not advertiser or advertiser.id != user_task.task.created_by:
        await callback.answer("আপনি এই কাজের মালিক নন।", show_alert=True)
        return

    await TaskQueries.complete_task(session, user_task_id)
    await UserQueries.update_balance(session, user_task.user_id, user_task.task.reward)
    tx = await TransactionQueries.create(session=session, user_id=user_task.user_id,
        type=TransactionType.REWARD, amount=user_task.task.reward,
        details=f"কাজের পুরস্কার: {user_task.task.title}")
    tx.status = TransactionStatus.COMPLETED
    await session.commit()

    try:
        await callback.bot.send_message(
            user_task.user.telegram_id,
            f"🎉 <b>কাজ অনুমোদিত!</b>\n"
            f"📌 {user_task.task.title}\n"
            f"💰 <b>{C}{user_task.task.reward:,.0f}</b> ব্যালেন্সে যোগ হয়েছে!",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + "\n\n✅ <b>অনুমোদিত</b>",
                parse_mode="HTML")
        else:
            await callback.message.edit_text(
                (callback.message.text or "") + "\n\n✅ <b>অনুমোদিত</b>",
                parse_mode="HTML")
    except Exception:
        pass

    await callback.answer(f"✅ অনুমোদিত! {C}{user_task.task.reward:,.0f} পাঠানো হয়েছে।")


# ── Advertiser Reject (2-step) ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("adv_reject:"))
async def advertiser_reject_warn(callback: CallbackQuery, session: AsyncSession) -> None:
    user_task_id = int(callback.data.split(":")[1])
    user_task = await TaskQueries.get_user_task_by_id(session, user_task_id)

    if not user_task or user_task.status != TaskStatus.PENDING:
        await callback.answer("পাওয়া যায়নি বা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    advertiser = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not advertiser or advertiser.id != user_task.task.created_by:
        await callback.answer("আপনি এই কাজের মালিক নন।", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="⚠️ হ্যাঁ, বাতিল করুন", callback_data=f"adv_reject_confirm:{user_task_id}"),
        InlineKeyboardButton(text="↩️ ফিরে যান",           callback_data=f"adv_reject_back:{user_task_id}"),
    )
    await callback.message.reply(
        "⚠️ <b>সতর্কতা!</b>\n\n"
        "সঠিক কাজ বাতিল করলে এডমিনের কাছে রিপোর্ট যাবে।\n"
        "কাজ সঠিক প্রমাণিত হলে <b>আপনার অ্যাকাউন্ট ব্যান করা হবে।</b>❌\n\n"
        "নিশ্চিতভাবে বাতিল করতে চান?",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adv_reject_confirm:"))
async def advertiser_reject_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    user_task_id = int(callback.data.split(":")[1])
    user_task = await TaskQueries.get_user_task_by_id(session, user_task_id)

    if not user_task or user_task.status != TaskStatus.PENDING:
        await callback.answer("পাওয়া যায়নি বা ইতিমধ্যে প্রক্রিয়া হয়েছে।", show_alert=True)
        return

    advertiser = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not advertiser or advertiser.id != user_task.task.created_by:
        await callback.answer("আপনি এই কাজের মালিক নন।", show_alert=True)
        return

    await TaskQueries.reject_task(session, user_task_id)

    try:
        await callback.bot.send_message(
            user_task.user.telegram_id,
            f"❌ <b>কাজ বাতিল হয়েছে</b>\n"
            f"📌 {user_task.task.title}\n"
            f"প্রমাণ গ্রহণযোগ্য হয়নি।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    for admin_id in settings.admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"⚠️ <b>কাজ বাতিল রিপোর্ট</b>\n"
                f"📌 {user_task.task.title}\n"
                f"👤 কর্মী: {user_task.user.full_name}\n"
                f"👤 বিজ্ঞাপনদাতা: <code>{callback.from_user.id}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    try:
        await callback.message.edit_text(
            "❌ বাতিল করা হয়েছে।\n"
            "⚠️ এডমিন কাজটি যাচাই করবেন।",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("❌ বাতিল করা হয়েছে।")


@router.callback_query(F.data.startswith("adv_reject_back:"))
async def advertiser_reject_back(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("↩️ বাতিল করা হয়নি।")


# ══════════════════════════════════════════════════════════════════════════════
#  ADVERTISER — Create Task  (multi-step FSM)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "✏️ কাজ তৈরি করুন")
async def create_task_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    if not user or user.is_blocked:
        await message.answer("🚫 অ্যাক্সেস নেই।")
        return
    await state.clear()
    await state.set_state(CreateTaskStates.choosing_category)
    await message.answer(
        "➕ <b>নতুন কাজ তৈরি করুন</b>\n\nধাপ ১ — প্ল্যাটফর্ম বেছে নিন:",
        reply_markup=get_category_keyboard(),
        parse_mode="HTML",
    )


# Step 1 → Category
@router.callback_query(StateFilter(CreateTaskStates.choosing_category), F.data.startswith("cat:"))
async def on_category_selected(callback: CallbackQuery, state: FSMContext) -> None:
    cat_key = callback.data.split(":")[1]
    if cat_key not in TASK_CATEGORIES:
        await callback.answer("অজানা ক্যাটাগরি।", show_alert=True)
        return
    cat_data = TASK_CATEGORIES[cat_key]
    await state.update_data(category_key=cat_key, category_name=cat_data["name"])
    await state.set_state(CreateTaskStates.choosing_subcategory)
    await callback.message.edit_text(
        f"➕ <b>{cat_data['name']}</b>\n\nধাপ ২ — কাজের ধরন বেছে নিন:",
        reply_markup=get_subcategory_keyboard(cat_key),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(StateFilter(CreateTaskStates.choosing_subcategory), F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateTaskStates.choosing_category)
    await callback.message.edit_text(
        "➕ <b>নতুন কাজ তৈরি করুন</b>\n\nধাপ ১ — প্ল্যাটফর্ম বেছে নিন:",
        reply_markup=get_category_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# Step 2 → Subcategory → ask for task description
@router.callback_query(StateFilter(CreateTaskStates.choosing_subcategory), F.data.startswith("sub:"))
async def on_subcategory_selected(callback: CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    cat_key = data.get("category_key", "")
    tasks_list = TASK_CATEGORIES.get(cat_key, {}).get("tasks", [])

    if idx >= len(tasks_list):
        await callback.answer("অজানা ধরন।", show_alert=True)
        return

    subcategory, min_reward = tasks_list[idx]
    await state.update_data(subcategory=subcategory, subcategory_index=idx, min_reward=min_reward)
    await state.set_state(CreateTaskStates.entering_description)

    cat_name = data.get("category_name", "")
    await callback.message.edit_text(
        f"➕ <b>{cat_name} — {subcategory}</b>\n\n"
        f"ধাপ ৩ — <b>কাজের নিয়ম লিখুন</b> এবং পাঠান ✅\n\n"
        f"<i>উদাহরণ: আমার পেজে লাইক দিন এবং একটি কমেন্ট করুন। "
        f"কাজ শেষে স্ক্রিনশট পাঠান।</i>",
        parse_mode="HTML",
    )
    await callback.message.answer("নিয়ম লিখুন:", reply_markup=_cancel_inline())
    await callback.answer()


# Step 3 → Description entered → ask proof 1
@router.message(StateFilter(CreateTaskStates.entering_description))
async def on_description_entered(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 10:
        await message.answer("❌ অন্তত ১০ অক্ষরের নিয়ম লিখুন:", reply_markup=_cancel_inline())
        return
    await state.update_data(task_description=text)
    await state.set_state(CreateTaskStates.entering_proof1)
    await message.answer(
        "ধাপ ৪ — <b>প্রমাণ ১ (📸 স্ক্রিনশট)</b>\n\n"
        "কর্মীরা কী স্ক্রিনশট পাঠাবে? লিখুন:\n"
        "<i>উদাহরণ: লাইক দেওয়ার পর পেজের স্ক্রিনশট</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )


# Step 4 → Proof 1 → ask proof 2
@router.message(StateFilter(CreateTaskStates.entering_proof1))
async def on_proof1_entered(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ খালি রাখা যাবে না:", reply_markup=_cancel_inline())
        return
    await state.update_data(proof1_label=text)
    await state.set_state(CreateTaskStates.entering_proof2)
    await message.answer(
        "ধাপ ৫ — <b>প্রমাণ ২ (📸 স্ক্রিনশট)</b>\n\n"
        "২য় স্ক্রিনশটে কী দেখাতে হবে? লিখুন:\n"
        "<i>উদাহরণ: কমেন্টের স্ক্রিনশট</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )


# Step 5 → Proof 2 → ask proof 3
@router.message(StateFilter(CreateTaskStates.entering_proof2))
async def on_proof2_entered(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ খালি রাখা যাবে না:", reply_markup=_cancel_inline())
        return
    await state.update_data(proof2_label=text)
    await state.set_state(CreateTaskStates.entering_proof3)
    await message.answer(
        "ধাপ ৬ — <b>প্রমাণ ৩ (📝 টেক্সট)</b>\n\n"
        "টেক্সট প্রমাণে কী লিখতে হবে? লিখুন:\n"
        "<i>উদাহরণ: আপনার ফেসবুক প্রোফাইল লিংক</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )


# Step 6 → Proof 3 → ask link
@router.message(StateFilter(CreateTaskStates.entering_proof3))
async def on_proof3_entered(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ খালি রাখা যাবে না:", reply_markup=_cancel_inline())
        return
    await state.update_data(proof3_label=text)
    await state.set_state(CreateTaskStates.entering_link)
    await message.answer(
        "ধাপ ৭ — <b>কাজটি কীভাবে পাওয়া যাবে?</b>\n\n"
        "📌 দুইভাবে দিতে পারেন:\n\n"
        "১️⃣ <b>সরাসরি লিংক দিন</b>\n"
        "   যেমন: <code>https://youtube.com/watch?v=...</code>\n\n"
        "২️⃣ <b>খোঁজার নির্দেশনা লিখুন</b>\n"
        "   যেমন: <i>YouTube এ সার্চ করুন: Smart Tech Bangla</i>\n"
        "   যেমন: <i>Google এ সার্চ করুন: XYZ প্রোডাক্ট এবং প্রথম লিংকে যান</i>\n"
        "   যেমন: <i>Facebook এ Smart Tech Bangla পেজে যান</i>\n\n"
        "অথবা এড়িয়ে যেতে নিচের বাটন চাপুন ⏭️",
        reply_markup=_link_step_keyboard(),
        parse_mode="HTML",
    )


# Step 7 → Link or instruction
@router.callback_query(StateFilter(CreateTaskStates.entering_link), F.data == "task_link_skip")
async def on_link_skipped(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(task_link="")
    await state.set_state(CreateTaskStates.entering_workers)
    await callback.message.answer(
        "ধাপ ৮ — কতজন কর্মী দরকার? <b>সংখ্যা</b> লিখুন:\n<i>(১ — ১০,০০০)</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(CreateTaskStates.entering_link))
async def on_link_entered(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ খালি রাখা যাবে না। লিংক বা নির্দেশনা লিখুন:", reply_markup=_link_step_keyboard())
        return
    await state.update_data(task_link=text)
    await state.set_state(CreateTaskStates.entering_workers)
    await message.answer(
        "ধাপ ৮ — কতজন কর্মী দরকার? <b>সংখ্যা</b> লিখুন:\n<i>(১ — ১০,০০০)</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )


# Step 8 → Workers
@router.message(StateFilter(CreateTaskStates.entering_workers))
async def on_workers_entered(message: Message, state: FSMContext) -> None:
    try:
        workers = int((message.text or "").strip().replace(",", ""))
        if workers < 1 or workers > 10_000:
            raise ValueError
    except ValueError:
        await message.answer("❌ ১ থেকে ১০,০০০ এর মধ্যে সংখ্যা লিখুন:", reply_markup=_cancel_inline())
        return
    await state.update_data(num_workers=workers)
    await state.set_state(CreateTaskStates.entering_reward)
    data = await state.get_data()
    min_r = data.get("min_reward", 1)
    await message.answer(
        f"ধাপ ৯ — প্রতি কর্মীর <b>পুরস্কার</b> ({C}):\n<i>সর্বনিম্ন: {C}{min_r}</i>",
        reply_markup=_cancel_inline(),
        parse_mode="HTML",
    )


# Step 9 → Reward → Summary
@router.message(StateFilter(CreateTaskStates.entering_reward))
async def on_reward_entered(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    min_r = data.get("min_reward", 1)
    try:
        reward = float((message.text or "").strip().replace(",", ""))
        if reward < min_r:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ সর্বনিম্ন {C}{min_r} হতে হবে:", reply_markup=_cancel_inline())
        return

    await state.update_data(reward_per_worker=reward)
    await state.set_state(CreateTaskStates.confirming)

    data = await state.get_data()
    user = await UserQueries.get_by_telegram_id(session, message.from_user.id)
    await _show_summary(message.answer, data, user_balance=user.balance if user else 0)


# Step 10 → Confirm
@router.callback_query(StateFilter(CreateTaskStates.confirming), F.data == "task_confirm")
async def on_task_confirmed(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    user = await UserQueries.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("ব্যবহারকারী পাওয়া যায়নি।", show_alert=True)
        return

    num_workers  = data["num_workers"]
    reward       = data["reward_per_worker"]
    cat_name     = data["category_name"]
    subcategory  = data["subcategory"]
    task_link    = data.get("task_link", "")
    description  = data.get("task_description", "")
    proof1       = data.get("proof1_label", "")
    proof2       = data.get("proof2_label", "")
    proof3       = data.get("proof3_label", "")

    worker_cost  = num_workers * reward
    platform_fee = worker_cost * PLATFORM_FEE_PCT
    total_cost   = worker_cost + platform_fee

    if user.balance < total_cost:
        shortage = total_cost - user.balance
        await callback.answer(
            f"❌ অপর্যাপ্ত ব্যালেন্স!\nপ্রয়োজন: {C}{total_cost:,.0f} | আরো জমা করুন: {C}{shortage:,.0f}",
            show_alert=True,
        )
        return

    await state.clear()

    # Deduct cost
    await UserQueries.update_balance(session, user.id, -total_cost)
    tx = await TransactionQueries.create(session=session, user_id=user.id,
        type=TransactionType.WITHDRAWAL, amount=total_cost,
        details=f"কাজ তৈরি: {cat_name} — {subcategory}")
    tx.status = TransactionStatus.COMPLETED
    await session.commit()

    # Build full description with proof requirements
    full_description = (
        f"{description}\n\n"
        f"📋 প্রমাণের নির্দেশনা:\n"
        f"📸 স্ক্রিনশট ১: {proof1}\n"
        f"📸 স্ক্রিনশট ২: {proof2}\n"
        f"📝 টেক্সট: {proof3}"
    )

    title = f"{cat_name} — {subcategory}"
    task = await TaskQueries.create(session=session, title=title,
        description=full_description, reward=reward, task_type="custom",
        created_by=user.id, task_url=task_link, total_slots=num_workers)

    new_balance = user.balance - total_cost

    for admin_id in settings.admin_ids:
        try:
            await callback.bot.send_message(admin_id,
                f"🆕 <b>নতুন কাজ #{task.id}</b>\n"
                f"👤 {user.full_name} | 📌 {title}\n"
                + (f"🔗 {task_link} | " if task_link else "")
                + f"👥 {num_workers} | {C}{reward:,.0f}/জন",
                parse_mode="HTML")
        except Exception:
            pass

    await callback.message.edit_text(
        f"✅ <b>কাজ তৈরি হয়েছে!</b>\n\n"
        f"📌 {title}\n👥 {num_workers} কর্মী | {C}{reward:,.0f}/জন\n"
        f"💳 কাটা: {C}{total_cost:,.0f} | 💼 বাকি: {C}{new_balance:,.0f}",
        parse_mode="HTML",
    )
    await callback.answer("✅ কাজ তৈরি হয়েছে!")


# Cancel any Create Task state
@router.callback_query(
    StateFilter(
        CreateTaskStates.choosing_category, CreateTaskStates.choosing_subcategory,
        CreateTaskStates.entering_description, CreateTaskStates.entering_proof1,
        CreateTaskStates.entering_proof2, CreateTaskStates.entering_proof3,
        CreateTaskStates.entering_link, CreateTaskStates.entering_workers,
        CreateTaskStates.entering_reward, CreateTaskStates.confirming,
    ),
    F.data == "task_cancel",
)
async def on_task_cancelled(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("❌ কাজ তৈরি বাতিল।")
    except Exception:
        await callback.message.answer("❌ বাতিল।", reply_markup=get_main_menu_for(callback.from_user.id))
    await callback.answer("বাতিল।")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cancel_inline():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ বাতিল", callback_data="task_cancel"))
    return b.as_markup()


def _link_step_keyboard():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏭️ এড়িয়ে যান (Skip)", callback_data="task_link_skip"))
    b.row(InlineKeyboardButton(text="❌ বাতিল", callback_data="task_cancel"))
    return b.as_markup()


async def _show_summary(send_fn, data: dict, user_balance: float = 0.0) -> None:
    num_workers  = data.get("num_workers", 0)
    reward       = data.get("reward_per_worker", 0)
    cat_name     = data.get("category_name", "")
    subcategory  = data.get("subcategory", "")
    task_link    = data.get("task_link", "")
    description  = data.get("task_description", "")
    proof1       = data.get("proof1_label", "")
    proof2       = data.get("proof2_label", "")
    proof3       = data.get("proof3_label", "")

    worker_cost  = num_workers * reward
    platform_fee = worker_cost * PLATFORM_FEE_PCT
    total_cost   = worker_cost + platform_fee
    can_afford   = user_balance >= total_cost

    balance_line = (
        f"💼 ব্যালেন্স: {C}{user_balance:,.0f} ✅"
        if can_afford else
        f"💼 ব্যালেন্স: {C}{user_balance:,.0f} ❌ (কম: {C}{total_cost - user_balance:,.0f})"
    )

    text = (
        f"📋 <b>কাজের সারসংক্ষেপ</b>\n"
        f"🏷 {cat_name} — {subcategory}\n"
        + (f"🔗 {task_link}\n" if task_link else "")
        + f"📝 নিয়ম: {description[:100]}{'…' if len(description) > 100 else ''}\n"
        f"📸১: {proof1[:60]} | 📸২: {proof2[:60]}\n"
        f"📝৩: {proof3[:60]}\n"
        f"{'─'*24}\n"
        f"👥 কর্মী: {num_workers} | {C}{reward:,.0f}/জন\n"
        f"💵 খরচ: {C}{worker_cost:,.0f} + ফি: {C}{platform_fee:,.0f}\n"
        f"💳 মোট: <b>{C}{total_cost:,.0f}</b>\n"
        f"{'─'*24}\n"
        f"{balance_line}\n\n"
        + ("নিশ্চিত করতে ✅ চাপুন:" if can_afford else "⚠️ পর্যাপ্ত ব্যালেন্স নেই। Deposit করুন।")
    )

    if can_afford:
        kb = get_task_summary_keyboard()
    else:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="❌ বাতিল", callback_data="task_cancel"))
        kb = b.as_markup()

    await send_fn(text, reply_markup=kb, parse_mode="HTML")
