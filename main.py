import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.engine import engine, Base, async_session_maker
from bot.handlers import get_all_routers
from bot.middlewares import DatabaseMiddleware, ForceJoinMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Health-check HTTP server (required for Replit deployment) ──────────────────

async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "bot": "@SmartMicroTaskbot"})

async def start_health_server() -> None:
    port = int(os.environ.get("PORT", 9090))
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server running on port {port}")


async def keepalive_ping() -> None:
    """Ping the local API server every 4 minutes to prevent Replit hibernation."""
    await asyncio.sleep(30)
    ping_url = "http://localhost:8080/api/healthz"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info("Keepalive ping OK")
        except Exception as e:
            logger.warning(f"Keepalive ping failed: {e}")
        await asyncio.sleep(240)  # every 4 minutes


# ── Auto-approve background scheduler ─────────────────────────────────────────

async def auto_approve_scheduler(bot: Bot) -> None:
    """Check every hour; auto-approve PENDING submissions older than 24 hours."""
    from database.queries import TaskQueries, UserQueries, TransactionQueries
    from database.models import TransactionType, TransactionStatus

    await asyncio.sleep(60)  # Small initial delay so DB is ready

    while True:
        try:
            async with async_session_maker() as session:
                old_pending = await TaskQueries.get_old_pending_submissions(session, hours=24)
                if old_pending:
                    logger.info(f"Auto-approving {len(old_pending)} stale submissions…")

                for ut in old_pending:
                    try:
                        await TaskQueries.complete_task(session, ut.id)
                        await UserQueries.update_balance(session, ut.user_id, ut.task.reward)
                        tx = await TransactionQueries.create(
                            session=session,
                            user_id=ut.user_id,
                            type=TransactionType.REWARD,
                            amount=ut.task.reward,
                            details=f"স্বয়ংক্রিয় অনুমোদন: {ut.task.title}",
                        )
                        tx.status = TransactionStatus.COMPLETED
                        await session.commit()

                        try:
                            await bot.send_message(
                                ut.user.telegram_id,
                                f"🎉 <b>কাজ স্বয়ংক্রিয়ভাবে অনুমোদিত!</b>\n\n"
                                f"📌 <b>{ut.task.title}</b>\n"
                                f"💰 <b>{settings.CURRENCY_SYMBOL}{ut.task.reward:,.0f}</b> "
                                f"আপনার ব্যালেন্সে যোগ হয়েছে!\n\n"
                                f"(২৪ ঘন্টার মধ্যে পর্যালোচনা না হওয়ায় স্বয়ংক্রিয়ভাবে অনুমোদিত হয়েছে।)",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Auto-approve failed for UserTask {ut.id}: {e}")

        except Exception as e:
            logger.error(f"Auto-approve scheduler error: {e}")

        await asyncio.sleep(3600)  # Run every hour


# ── Startup / Shutdown ─────────────────────────────────────────────────────────

async def on_startup(bot: Bot) -> None:
    logger.info("Bot starting up...")
    from sqlalchemy import text as sa_text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(sa_text(
                "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS "
                "description_photo_id VARCHAR(512)"
            ))
        except Exception:
            pass
        if os.environ.get("RESET_BALANCES") == "1":
            try:
                await conn.execute(sa_text(
                    "UPDATE users SET balance=0, total_earned=0, total_withdrawn=0"
                ))
                logger.info("✅ All balances reset to 0 (RESET_BALANCES=1)")
            except Exception as e:
                logger.error(f"Balance reset failed: {e}")
        if os.environ.get("RESET_TASK_PRICES") == "1":
            try:
                await conn.execute(sa_text(
                    "UPDATE tasks SET reward=1 WHERE title LIKE '🔵 Facebook%' OR title LIKE '🔴 YouTube%'"
                ))
                logger.info("✅ Facebook+YouTube task rewards reset to 1 (RESET_TASK_PRICES=1)")
            except Exception as e:
                logger.error(f"Task price reset failed: {e}")
    logger.info("Database ready. v4")

    me = await bot.get_me()
    logger.info(f"Running as @{me.username} (ID: {me.id})")

    asyncio.create_task(auto_approve_scheduler(bot))
    logger.info("Auto-approve scheduler started.")

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"🤖 <b>বট চালু হয়েছে</b>\n\n@{me.username} হিসেবে চলছে",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def on_shutdown(bot: Bot) -> None:
    logger.info("Bot shutting down...")
    await engine.dispose()


async def main() -> None:
    # Start health server + keepalive ping
    await start_health_server()
    asyncio.create_task(keepalive_ping())

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.update.middleware(DatabaseMiddleware())

    force_join = ForceJoinMiddleware()
    dp.message.middleware(force_join)
    dp.callback_query.middleware(force_join)

    for router in get_all_routers():
        dp.include_router(router)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
