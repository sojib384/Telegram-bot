from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import uuid

from database.models import (
    User, Channel, Task, UserTask, Transaction, SupportTicket, BotSettings,
    TaskStatus, TransactionType, TransactionStatus, TicketStatus
)
from sqlalchemy.orm import aliased


class UserQueries:
    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_referral_code(session: AsyncSession, code: str) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        referred_by_id: Optional[int] = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            referred_by_id=referred_by_id,
            referral_code=uuid.uuid4().hex[:8],
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def update_last_active(session: AsyncSession, user_id: int) -> None:
        await session.execute(
            update(User).where(User.id == user_id).values(last_active=datetime.utcnow())
        )
        await session.commit()

    @staticmethod
    async def update_balance(session: AsyncSession, user_id: int, amount: float) -> None:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                balance=User.balance + amount,
                total_earned=User.total_earned + (amount if amount > 0 else 0),
                total_withdrawn=User.total_withdrawn + (-amount if amount < 0 else 0),
            )
        )
        await session.commit()

    @staticmethod
    async def get_referrals(session: AsyncSession, user_id: int) -> List[User]:
        result = await session.execute(
            select(User).where(User.referred_by_id == user_id)
        )
        return result.scalars().all()

    @staticmethod
    async def get_all(session: AsyncSession, limit: int = 50, offset: int = 0) -> List[User]:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all()

    @staticmethod
    async def get_total_count(session: AsyncSession) -> int:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar_one()

    @staticmethod
    async def block_user(session: AsyncSession, user_id: int, blocked: bool) -> None:
        await session.execute(
            update(User).where(User.id == user_id).values(is_blocked=blocked)
        )
        await session.commit()

    @staticmethod
    async def get_today_registrations(session: AsyncSession) -> int:
        today = datetime.utcnow().date()
        result = await session.execute(
            select(func.count()).select_from(User).where(
                func.date(User.created_at) == today
            )
        )
        return result.scalar_one()

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


class ChannelQueries:
    @staticmethod
    async def get_required_channels(session: AsyncSession) -> List[Channel]:
        result = await session.execute(
            select(Channel).where(Channel.is_required == True)
        )
        return result.scalars().all()

    @staticmethod
    async def get_by_channel_id(session: AsyncSession, channel_id: int) -> Optional[Channel]:
        result = await session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        channel_id: int,
        channel_name: str,
        channel_username: Optional[str] = None,
        invite_link: Optional[str] = None,
    ) -> Channel:
        channel = Channel(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_username=channel_username,
            invite_link=invite_link,
        )
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        return channel

    @staticmethod
    async def delete(session: AsyncSession, channel_id: int) -> None:
        await session.execute(
            delete(Channel).where(Channel.id == channel_id)
        )
        await session.commit()

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Channel]:
        result = await session.execute(select(Channel))
        return result.scalars().all()


class TaskQueries:
    @staticmethod
    async def get_active_tasks(session: AsyncSession, user_id: int) -> List[Task]:
        """Return tasks that are active, not expired, and the user hasn't completed."""
        now = datetime.utcnow()

        # Tasks already done (any status) by this user
        done_ids_result = await session.execute(
            select(UserTask.task_id).where(UserTask.user_id == user_id)
        )
        done_ids = [r[0] for r in done_ids_result.fetchall()]

        query = select(Task).where(
            Task.is_active == True,
            or_(Task.deadline == None, Task.deadline > now),
        )
        if done_ids:
            query = query.where(Task.id.not_in(done_ids))

        result = await session.execute(query.order_by(Task.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, task_id: int) -> Optional[Task]:
        result = await session.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        title: str,
        description: str,
        reward: float,
        task_type: str,
        created_by: int,
        task_url: Optional[str] = None,
        total_slots: int = 0,
        deadline: Optional[datetime] = None,
        description_photo_id: Optional[str] = None,
    ) -> Task:
        from database.models import TaskType
        task = Task(
            title=title,
            description=description,
            description_photo_id=description_photo_id,
            reward=reward,
            task_type=TaskType(task_type),
            task_url=task_url,
            created_by=created_by,
            total_slots=total_slots,
            deadline=deadline,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

    @staticmethod
    async def get_user_task(session: AsyncSession, user_id: int, task_id: int) -> Optional[UserTask]:
        result = await session.execute(
            select(UserTask).where(
                and_(UserTask.user_id == user_id, UserTask.task_id == task_id)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_task_by_id(session: AsyncSession, user_task_id: int) -> Optional[UserTask]:
        """Load a single UserTask with its user and task eagerly."""
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.user), selectinload(UserTask.task))
            .where(UserTask.id == user_task_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def submit_task(session: AsyncSession, user_id: int, task_id: int, proof: Optional[str] = None) -> UserTask:
        user_task = UserTask(
            user_id=user_id,
            task_id=task_id,
            status=TaskStatus.PENDING,
            proof_text=proof,
        )
        session.add(user_task)
        await session.commit()
        await session.refresh(user_task)
        return user_task

    @staticmethod
    async def complete_task(session: AsyncSession, user_task_id: int) -> None:
        """Mark submission as COMPLETED and increment the task's completed_count."""
        # Get task_id first
        result = await session.execute(
            select(UserTask.task_id).where(UserTask.id == user_task_id)
        )
        task_id = result.scalar_one_or_none()

        await session.execute(
            update(UserTask)
            .where(UserTask.id == user_task_id)
            .values(status=TaskStatus.COMPLETED, completed_at=datetime.utcnow())
        )
        if task_id:
            await session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(completed_count=Task.completed_count + 1)
            )
        await session.commit()

    @staticmethod
    async def reject_task(session: AsyncSession, user_task_id: int) -> None:
        await session.execute(
            update(UserTask)
            .where(UserTask.id == user_task_id)
            .values(status=TaskStatus.REJECTED)
        )
        await session.commit()

    @staticmethod
    async def get_pending_tasks(session: AsyncSession) -> List[UserTask]:
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.user), selectinload(UserTask.task))
            .where(UserTask.status == TaskStatus.PENDING)
            .order_by(UserTask.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_all_tasks(session: AsyncSession) -> List[Task]:
        result = await session.execute(select(Task).order_by(Task.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def toggle_task(session: AsyncSession, task_id: int, is_active: bool) -> None:
        await session.execute(
            update(Task).where(Task.id == task_id).values(is_active=is_active)
        )
        await session.commit()

    @staticmethod
    async def delete_task(session: AsyncSession, task_id: int) -> None:
        await session.execute(delete(UserTask).where(UserTask.task_id == task_id))
        await session.execute(delete(Task).where(Task.id == task_id))
        await session.commit()

    @staticmethod
    async def get_pending_submissions_count(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(UserTask).where(UserTask.status == TaskStatus.PENDING)
        )
        return result.scalar_one()

    @staticmethod
    async def get_total_tasks_count(session: AsyncSession) -> int:
        result = await session.execute(select(func.count()).select_from(Task))
        return result.scalar_one()

    @staticmethod
    async def get_active_tasks_count(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(Task).where(Task.is_active == True)
        )
        return result.scalar_one()

    @staticmethod
    async def get_user_task_history(
        session: AsyncSession, user_id: int, limit: int = 20
    ) -> List[UserTask]:
        """All task submissions by a user, newest first."""
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.task))
            .where(UserTask.user_id == user_id)
            .order_by(UserTask.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_task_submissions(session: AsyncSession, task_id: int) -> List[UserTask]:
        """All submissions for a specific task."""
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.user))
            .where(UserTask.task_id == task_id)
            .order_by(UserTask.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_tasks_by_creator(session: AsyncSession, user_id: int) -> List[Task]:
        """All tasks created by a specific user (advertiser)."""
        result = await session.execute(
            select(Task)
            .where(Task.created_by == user_id)
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_pending_submissions_for_task(session: AsyncSession, task_id: int) -> List[UserTask]:
        """PENDING submissions for a specific task, with worker eagerly loaded."""
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.user))
            .where(UserTask.task_id == task_id, UserTask.status == TaskStatus.PENDING)
            .order_by(UserTask.created_at)
        )
        return result.scalars().all()

    @staticmethod
    async def get_old_pending_submissions(session: AsyncSession, hours: int = 24) -> List[UserTask]:
        """Return PENDING submissions older than `hours` hours (for auto-approve)."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await session.execute(
            select(UserTask)
            .options(selectinload(UserTask.user), selectinload(UserTask.task))
            .where(
                UserTask.status == TaskStatus.PENDING,
                UserTask.created_at < cutoff,
            )
        )
        return result.scalars().all()


class TransactionQueries:
    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
        type: TransactionType,
        amount: float,
        details: Optional[str] = None,
    ) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            type=type,
            amount=amount,
            details=details,
        )
        session.add(tx)
        await session.commit()
        await session.refresh(tx)
        return tx

    @staticmethod
    async def get_user_transactions(session: AsyncSession, user_id: int, limit: int = 10) -> List[Transaction]:
        result = await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_pending_withdrawals(session: AsyncSession) -> List[Transaction]:
        result = await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(
                and_(
                    Transaction.type == TransactionType.WITHDRAWAL,
                    Transaction.status == TransactionStatus.PENDING,
                )
            )
            .order_by(Transaction.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_pending_deposits(session: AsyncSession) -> List[Transaction]:
        result = await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(
                and_(
                    Transaction.type == TransactionType.DEPOSIT,
                    Transaction.status == TransactionStatus.PENDING,
                )
            )
            .order_by(Transaction.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_recent_deposits(session: AsyncSession, limit: int = 20) -> List[Transaction]:
        result = await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(Transaction.type == TransactionType.DEPOSIT)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def update_status(
        session: AsyncSession,
        tx_id: int,
        status: TransactionStatus,
    ) -> None:
        await session.execute(
            update(Transaction)
            .where(Transaction.id == tx_id)
            .values(status=status, processed_at=datetime.utcnow())
        )
        await session.commit()

    @staticmethod
    async def get_by_id(session: AsyncSession, tx_id: int) -> Optional[Transaction]:
        result = await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(Transaction.id == tx_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_total_deposited(session: AsyncSession) -> float:
        result = await session.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.type == TransactionType.DEPOSIT,
                    Transaction.status == TransactionStatus.COMPLETED,
                )
            )
        )
        return result.scalar_one() or 0.0

    @staticmethod
    async def get_total_withdrawn(session: AsyncSession) -> float:
        result = await session.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.type == TransactionType.WITHDRAWAL,
                    Transaction.status == TransactionStatus.COMPLETED,
                )
            )
        )
        return result.scalar_one() or 0.0

    @staticmethod
    async def get_pending_withdrawals_count(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(Transaction).where(
                and_(
                    Transaction.type == TransactionType.WITHDRAWAL,
                    Transaction.status == TransactionStatus.PENDING,
                )
            )
        )
        return result.scalar_one()

    @staticmethod
    async def get_pending_deposits_count(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(Transaction).where(
                and_(
                    Transaction.type == TransactionType.DEPOSIT,
                    Transaction.status == TransactionStatus.PENDING,
                )
            )
        )
        return result.scalar_one()


class BotSettingsQueries:
    """Admin-configurable runtime settings stored in DB."""

    DEFAULTS: dict = {
        "referral_signup_bonus": "50.0",
        "referral_withdrawal_commission": "0.10",
    }

    @staticmethod
    async def get(session: AsyncSession, key: str) -> str:
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        row = result.scalar_one_or_none()
        return row.value if row else BotSettingsQueries.DEFAULTS.get(key, "")

    @staticmethod
    async def get_float(session: AsyncSession, key: str) -> float:
        raw = await BotSettingsQueries.get(session, key)
        try:
            return float(raw)
        except (ValueError, TypeError):
            return float(BotSettingsQueries.DEFAULTS.get(key, 0))

    @staticmethod
    async def set(session: AsyncSession, key: str, value: str) -> None:
        result = await session.execute(
            select(BotSettings).where(BotSettings.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(BotSettings(key=key, value=value))
        await session.commit()

    @staticmethod
    async def get_all(session: AsyncSession) -> dict:
        result = await session.execute(select(BotSettings))
        rows = result.scalars().all()
        out = dict(BotSettingsQueries.DEFAULTS)
        for r in rows:
            out[r.key] = r.value
        return out


class ReferralQueries:
    @staticmethod
    async def get_leaderboard(session: AsyncSession, limit: int = 10):
        """Return (User, referral_count) tuples, ordered by count desc."""
        ref = aliased(User, name="ref")
        result = await session.execute(
            select(User, func.count(ref.id).label("ref_count"))
            .join(ref, ref.referred_by_id == User.id, isouter=True)
            .group_by(User.id)
            .having(func.count(ref.id) > 0)
            .order_by(func.count(ref.id).desc())
            .limit(limit)
        )
        return result.all()

    @staticmethod
    async def get_referral_earnings(session: AsyncSession, user_id: int) -> float:
        """Total completed referral transaction earnings for a user."""
        result = await session.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type == TransactionType.REFERRAL,
                    Transaction.status == TransactionStatus.COMPLETED,
                )
            )
        )
        return result.scalar_one() or 0.0

    @staticmethod
    async def get_referral_count(session: AsyncSession, user_id: int) -> int:
        result = await session.execute(
            select(func.count()).select_from(User).where(User.referred_by_id == user_id)
        )
        return result.scalar_one()


class SupportQueries:
    @staticmethod
    async def create_ticket(session: AsyncSession, user_id: int, message: str) -> SupportTicket:
        ticket = SupportTicket(user_id=user_id, message=message)
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket

    @staticmethod
    async def get_open_tickets(session: AsyncSession) -> List[SupportTicket]:
        result = await session.execute(
            select(SupportTicket)
            .options(selectinload(SupportTicket.user))
            .where(SupportTicket.status == TicketStatus.OPEN)
            .order_by(SupportTicket.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def close_ticket(session: AsyncSession, ticket_id: int, reply: Optional[str] = None) -> None:
        await session.execute(
            update(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .values(
                status=TicketStatus.CLOSED,
                admin_reply=reply,
                closed_at=datetime.utcnow(),
            )
        )
        await session.commit()

    @staticmethod
    async def get_by_id(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
        result = await session.execute(
            select(SupportTicket)
            .options(selectinload(SupportTicket.user))
            .where(SupportTicket.id == ticket_id)
        )
        return result.scalar_one_or_none()
