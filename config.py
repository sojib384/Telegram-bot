from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    BOT_ADMIN_IDS: str = ""
    DATABASE_URL: str
    BOT_USERNAME: str = ""
    SUPPORT_USERNAME: str = ""

    CURRENCY_SYMBOL: str = "৳"
    MIN_WITHDRAW: float = 100.0
    WITHDRAW_FEE: float = 10.0
    REFERRAL_SIGNUP_BONUS: float = 50.0
    REFERRAL_WITHDRAWAL_COMMISSION: float = 0.10

    @property
    def admin_ids(self) -> List[int]:
        ids = []
        for source in [self.ADMIN_IDS, self.BOT_ADMIN_IDS]:
            if not source:
                continue
            for x in source.split(","):
                x = x.strip().lstrip("@")
                try:
                    ids.append(int(x))
                except ValueError:
                    pass
        return ids

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=" in url:
            import re
            url = re.sub(r"[?&]sslmode=[^&]*", "", url)
            url = re.sub(r"\?$", "", url)
        return url

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
