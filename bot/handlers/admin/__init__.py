from aiogram import Router
from .main import router as main_router
from .channels import router as channels_router
from .users import router as users_router
from .tasks import router as tasks_router
from .withdrawals import router as withdrawals_router
from .tickets import router as tickets_router

admin_router = Router()
admin_router.include_router(main_router)
admin_router.include_router(channels_router)
admin_router.include_router(users_router)
admin_router.include_router(tasks_router)
admin_router.include_router(withdrawals_router)
admin_router.include_router(tickets_router)
