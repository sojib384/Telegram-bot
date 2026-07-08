from aiogram import Router
from .start import router as start_router
from .balance import router as balance_router
from .tasks import router as tasks_router
from .referral import router as referral_router
from .deposit import router as deposit_router
from .withdraw import router as withdraw_router
from .statistics import router as statistics_router
from .support import router as support_router
from .admin import admin_router

def get_all_routers() -> list[Router]:
    return [
        start_router,
        balance_router,
        tasks_router,
        referral_router,
        deposit_router,
        withdraw_router,
        statistics_router,
        support_router,
        admin_router,
    ]
