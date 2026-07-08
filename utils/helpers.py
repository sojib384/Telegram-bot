from typing import TypeVar, List

T = TypeVar("T")


def format_currency(amount: float, symbol: str = "৳") -> str:
    return f"{symbol}{amount:,.0f}"


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def paginate(items: List[T], page: int, per_page: int = 10) -> tuple[List[T], int]:
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return items[start : start + per_page], total_pages


def get_referral_link(bot_username: str, referral_code: str) -> str:
    return f"https://t.me/{bot_username}?start={referral_code}"


def mask_card_number(card: str) -> str:
    digits = card.replace(" ", "")
    if len(digits) < 8:
        return card
    return f"{digits[:4]} **** **** {digits[-4:]}"
